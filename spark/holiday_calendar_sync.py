# Databricks notebook source
"""Keeps Delta tables in sync with the Trakora holiday calendar.

Runs as a notebook in Microsoft Fabric (attached to a lakehouse), on Databricks or on any
Spark with Delta Lake. The first run loads everything, later runs only the releases
published since. Rows are merged by primary key, rows deleted in a release are deleted.

In a notebook: paste this file into a cell (Databricks imports it directly) and call
sync(spark). Schedule the notebook weekly to stay current.
"""

import hashlib
import io
import json
import urllib.request

import pyarrow.parquet as pq
from delta.tables import DeltaTable
from pyspark.sql import types as T

BASE_URL = "https://data.trakora.com/holiday-calendar/v1"

# Column types in the manifest are DuckDB types.
SPARK_TYPES = {
    "VARCHAR": T.StringType(),
    "BOOLEAN": T.BooleanType(),
    "INTEGER": T.IntegerType(),
    "BIGINT": T.LongType(),
    "DOUBLE": T.DoubleType(),
    "DATE": T.DateType(),
}


def sync(spark, schema: str = "holiday_calendar", base_url: str = BASE_URL) -> list[str]:
    """Applies all releases that are not in the schema yet and returns their versions.
    In a Fabric lakehouse without schemas, pass schema=""."""
    manifest = json.loads(_get(f"{base_url}/manifest.json"))
    prefix = f"{schema}." if schema else ""
    if schema:
        spark.sql(f"CREATE SCHEMA IF NOT EXISTS {schema}")

    state = f"{prefix}holiday_calendar_sync"
    spark.sql(f"CREATE TABLE IF NOT EXISTS {state} (release_seq INT, version STRING, synced_at TIMESTAMP) USING DELTA")
    done = spark.sql(f"SELECT coalesce(max(release_seq), 0) FROM {state}").first()[0]

    tables = {table["name"]: table for table in manifest["tables"]}
    applied = []
    for release in manifest["releases"]:
        if release["release_seq"] <= done:
            continue
        for change in release["changes"]:
            name, table = prefix + change["table"], tables[change["table"]]
            _apply(spark, name, table, _read(spark, base_url, change, tables))
            _describe(spark, name, table)
        spark.sql(f"INSERT INTO {state} VALUES ({release['release_seq']}, '{release['version']}', current_timestamp())")
        applied.append(release["version"])
    return applied


def _read(spark, base_url: str, change: dict, tables: dict):
    content = _get(f"{base_url}/{change['parquet']['path']}")
    if hashlib.sha256(content).hexdigest() != change["parquet"]["sha256"]:
        raise ValueError(f"Checksum mismatch for {change['parquet']['path']}")
    schema = T.StructType(
        [T.StructField(c["name"], SPARK_TYPES[c["type"]]) for c in tables[change["table"]]["columns"]]
        + [T.StructField("_op", T.StringType()), T.StructField("_release_seq", T.IntegerType())]
    )
    rows = pq.read_table(io.BytesIO(content)).select(schema.fieldNames()).to_pylist()
    return spark.createDataFrame(rows, schema)


def _apply(spark, name: str, table: dict, changes) -> None:
    columns = [c["name"] for c in table["columns"]]
    if not spark.catalog.tableExists(name):
        changes.filter("_op = 'upsert'").select(columns).write.format("delta").saveAsTable(name)
        return
    _add_new_columns(spark, name, changes, columns)
    match = " AND ".join(f"t.{k} = s.{k}" for k in table["primary_key"])
    values = {c: f"s.{c}" for c in columns}
    (
        DeltaTable.forName(spark, name).alias("t")
        .merge(changes.alias("s"), match)
        .whenMatchedDelete(condition="s._op = 'delete'")
        .whenMatchedUpdate(condition="s._op = 'upsert'", set=values)
        .whenNotMatchedInsert(condition="s._op = 'upsert'", values=values)
        .execute()
    )


def _add_new_columns(spark, name: str, changes, columns: list[str]) -> None:
    """Columns added by a later release are added to the Delta table before the merge."""
    existing = set(spark.table(name).columns)
    for field in changes.schema.fields:
        if field.name in columns and field.name not in existing:
            spark.sql(f"ALTER TABLE {name} ADD COLUMNS ({field.name} {field.dataType.simpleString()})")


def _describe(spark, name: str, table: dict) -> None:
    """Descriptions from the manifest as table and column comments (shown in Unity Catalog)."""
    def quote(text: str) -> str:
        return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"
    if table.get("description"):
        spark.sql(f"COMMENT ON TABLE {name} IS {quote(table['description'])}")
    for column in table["columns"]:
        if column.get("description"):
            spark.sql(f"ALTER TABLE {name} ALTER COLUMN {column['name']} COMMENT {quote(column['description'])}")


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


# COMMAND ----------

if "spark" in globals():
    try:
        target = dbutils.widgets.get("schema")  # noqa: F821  (Databricks job parameter)
    except Exception:
        target = "holiday_calendar"  # Fabric lakehouse without schemas: ""
    print(sync(spark, target))  # noqa: F821
