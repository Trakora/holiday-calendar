"""dlt source for the Trakora holiday calendar.

The first run loads everything, later runs only the releases published since; the last
release is kept in the pipeline state. Rows are merged by primary key, and rows deleted in
a release are deleted in the destination.
"""

import hashlib
import io

import dlt
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from dlt.sources.helpers import requests

BASE_URL = "https://data.trakora.com/holiday-calendar/v1"


@dlt.source(name="holiday_calendar")
def holiday_calendar(base_url: str = BASE_URL, tables: list[str] | None = None):
    """One resource per table. `tables` limits the load, e.g. ["dim_date", "fact_calendar_day"]."""
    manifest = requests.get(f"{base_url}/manifest.json").json()
    for table in manifest["tables"]:
        if tables is None or table["name"] in tables:
            yield _table(base_url, manifest, table)


def _table(base_url: str, manifest: dict, table: dict):
    @dlt.resource(
        name=table["name"],
        primary_key=table["primary_key"],
        write_disposition={"disposition": "merge", "strategy": "delete-insert"},
        columns={
            # the latest release decides when one load contains a row more than once
            "_release_seq": {"data_type": "bigint", "dedup_sort": "desc"},
            "_deleted": {"data_type": "bool", "hard_delete": True},
        },
    )
    def changes():
        state = dlt.current.resource_state()
        for release in manifest["releases"]:
            if release["release_seq"] <= state.get("release_seq", 0):
                continue
            for change in release["changes"]:
                if change["table"] == table["name"]:
                    yield _read(base_url, change["parquet"])
            state["release_seq"] = release["release_seq"]

    return changes


def _read(base_url: str, file: dict) -> pa.Table:
    content = requests.get(f"{base_url}/{file['path']}").content
    if hashlib.sha256(content).hexdigest() != file["sha256"]:
        raise ValueError(f"Checksum mismatch for {file['path']}")
    rows = pq.read_table(io.BytesIO(content))
    deleted = pc.equal(rows["_op"], "delete")
    return rows.drop_columns(["_op"]).append_column("_deleted", deleted)
