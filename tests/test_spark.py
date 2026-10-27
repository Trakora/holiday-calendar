"""Runs spark/holiday_calendar_sync.py on a local Spark with Delta Lake (needs Java 17+)."""

import os
import shutil
import sys
from pathlib import Path

import pytest

from conftest import FIXTURE

pytest.importorskip("delta")
if not shutil.which("java"):
    pytest.skip("Spark needs Java", allow_module_level=True)

from delta import configure_spark_with_delta_pip  # noqa: E402
from pyspark.sql import SparkSession  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1] / "spark"))
from holiday_calendar_sync import sync  # noqa: E402

LATEST = FIXTURE / "holiday-calendar" / "v1" / "latest"
TABLES = ["dim_date", "dim_region", "bridge_region_profile", "fact_calendar_day", "agg_population_day"]


@pytest.fixture(scope="module")
def spark(tmp_path_factory):
    os.environ["PYSPARK_PYTHON"] = sys.executable  # workers must use the same Python as the driver
    warehouse = tmp_path_factory.mktemp("warehouse")
    builder = (
        SparkSession.builder.master("local[2]")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .config("spark.sql.warehouse.dir", str(warehouse))
        .config("spark.ui.enabled", "false")
    )
    session = configure_spark_with_delta_pip(builder).getOrCreate()
    yield session
    session.stop()


def test_initial_load_then_only_changes(spark, serve, first_release_only):
    assert sync(spark, "holidays", serve(first_release_only)) == ["2026.01.15"]
    assert sync(spark, "holidays", serve(FIXTURE)) == ["2026.02.01"]
    assert sync(spark, "holidays", serve(FIXTURE)) == []

    for table in TABLES:
        loaded = spark.table(f"holidays.{table}")
        expected = spark.read.parquet(str(LATEST / f"{table}.parquet")).select(loaded.columns)
        assert loaded.exceptAll(expected).count() == 0, table
        assert expected.exceptAll(loaded).count() == 0, table

    comments = {f.name: f.metadata.get("comment") for f in spark.table("holidays.dim_holiday").schema.fields}
    assert comments["name_local"] == "Name in the language of the country"
