"""Keeps a DuckDB database in sync with the Trakora holiday calendar.

The first run loads everything, later runs only the releases published since. Any
pipeline can follow the same steps: read the manifest, load the change files of each new
release in order, upsert or delete rows by primary key, remember the last release.

    pip install duckdb
    python sync_duckdb.py holidays.duckdb
"""

import argparse
import json
import urllib.request

import duckdb

BASE_URL = "https://data.trakora.com/holiday-calendar/v1"


def sync(database: str, base_url: str = BASE_URL) -> list[str]:
    """Applies every release not yet in the database and returns their versions."""
    with urllib.request.urlopen(f"{base_url}/manifest.json", timeout=60) as response:
        manifest = json.load(response)
    keys = {table["name"]: table["primary_key"] for table in manifest["tables"]}
    applied = []

    with duckdb.connect(database) as con:
        con.execute("CREATE TABLE IF NOT EXISTS holiday_calendar_sync (release_seq INTEGER, version VARCHAR, synced_at TIMESTAMP)")
        done = con.execute("SELECT coalesce(max(release_seq), 0) FROM holiday_calendar_sync").fetchone()[0]

        for release in manifest["releases"]:
            if release["release_seq"] <= done:
                continue
            con.begin()
            for change in release["changes"]:
                table = change["table"]
                con.execute("CREATE OR REPLACE TEMP TABLE incoming AS SELECT * FROM read_parquet(?)",
                            [f"{base_url}/{change['parquet']['path']}"])
                con.execute(f"CREATE TABLE IF NOT EXISTS {table} AS SELECT * EXCLUDE (_op, _release_seq) FROM incoming LIMIT 0")
                _add_new_columns(con, table)
                match = " AND ".join(f"{table}.{key} = incoming.{key}" for key in keys[table])
                con.execute(f"DELETE FROM {table} USING incoming WHERE {match}")
                con.execute(f"INSERT INTO {table} BY NAME SELECT * EXCLUDE (_op, _release_seq) FROM incoming WHERE _op = 'upsert'")
            con.execute("INSERT INTO holiday_calendar_sync VALUES (?, ?, now())", [release["release_seq"], release["version"]])
            con.commit()
            # With DuckDB 2.0.0 the next release's DELETE missed rows of large tables written
            # earlier on the same connection. A checkpoint between releases avoids that.
            con.execute("CHECKPOINT")
            applied.append(release["version"])

    return applied


def _add_new_columns(con, table: str) -> None:
    """Adds columns that a later release introduced."""
    existing = {row[0] for row in con.execute(f"DESCRIBE {table}").fetchall()}
    for name, dtype, *_ in con.execute("DESCRIBE incoming").fetchall():
        if name not in existing and name not in ("_op", "_release_seq"):
            con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {dtype}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync the Trakora holiday calendar into a DuckDB database.")
    parser.add_argument("database", help="DuckDB file, created if missing")
    parser.add_argument("--url", default=BASE_URL, help=f"base URL (default: {BASE_URL})")
    args = parser.parse_args()
    versions = sync(args.database, args.url)
    print(f"Applied {len(versions)} release(s): {', '.join(versions)}" if versions else "Already up to date")
