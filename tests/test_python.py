import importlib.util
import json
from pathlib import Path

import duckdb

from conftest import FIXTURE

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("sync_duckdb", ROOT / "python" / "sync_duckdb.py")
sync_duckdb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_duckdb)

LATEST = FIXTURE / "holiday-calendar" / "v1" / "latest"
MANIFEST = json.loads((FIXTURE / "holiday-calendar" / "v1" / "manifest.json").read_text(encoding="utf-8"))
TABLES = [table["name"] for table in MANIFEST["tables"]]


def assert_matches_latest(con):
    for table in TABLES:
        difference = con.execute(f"""
            SELECT count(*) FROM (
                (SELECT * FROM {table} EXCEPT SELECT * FROM read_parquet('{LATEST / table}.parquet'))
                UNION ALL
                (SELECT * FROM read_parquet('{LATEST / table}.parquet') EXCEPT SELECT * FROM {table})
            )
        """).fetchone()[0]
        assert difference == 0, table


def test_first_sync_loads_every_release(base_url, tmp_path):
    database = str(tmp_path / "holidays.duckdb")
    assert sync_duckdb.sync(database, base_url) == ["2026.01.15", "2026.02.01"]
    with duckdb.connect(database) as con:
        assert_matches_latest(con)


def test_second_sync_only_applies_new_releases(base_url, tmp_path):
    database = str(tmp_path / "holidays.duckdb")
    sync_duckdb.sync(database, base_url)
    assert sync_duckdb.sync(database, base_url) == []


def test_query_parquet_by_url(base_url):
    rows = duckdb.sql(f"""
        SELECT count(*) FROM '{base_url}/latest/fact_calendar_day.parquet'
        WHERE calendar_profile_id = 'DE-BY-MH' AND is_public_holiday
    """).fetchall()
    assert rows == [(13,)]  # Bavarian municipalities with Assumption Day, 2027


def test_readme_quick_start(base_url):
    """Runs the first SQL block of the README against the fixture instead of data.trakora.com."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    query = readme.split("```sql\n", 1)[1].split("```", 1)[0]
    with duckdb.connect() as con:
        rows = con.execute(query.replace("https://data.trakora.com/holiday-calendar/v1", base_url)).fetchall()
    assert ("All Saints' Day", None) in [(holiday, school) for _, holiday, school in rows]
    assert any(school == "Summer holidays" for _, _, school in rows)
