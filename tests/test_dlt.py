import sys
from pathlib import Path

import dlt
import duckdb

from conftest import FIXTURE

sys.path.insert(0, str(Path(__file__).parents[1] / "dlt"))
from holiday_calendar import holiday_calendar  # noqa: E402

V1 = FIXTURE / "holiday-calendar" / "v1"
TABLES = ["dim_date", "dim_region", "bridge_region_profile", "fact_calendar_day", "agg_population_day"]


def run(base_url: str, tmp_path: Path):
    pipeline = dlt.pipeline(
        pipeline_name="holiday_calendar",
        pipelines_dir=str(tmp_path / "pipelines"),
        destination=dlt.destinations.duckdb(str(tmp_path / "warehouse.duckdb")),
        dataset_name="holiday_calendar",
    )
    pipeline.run(holiday_calendar(base_url, tables=TABLES))


def differences(tmp_path: Path, snapshot: Path) -> dict[str, int]:
    with duckdb.connect(str(tmp_path / "warehouse.duckdb")) as con:
        result = {}
        for table in TABLES:
            expected = f"read_parquet('{snapshot / table}.parquet')"
            columns = ", ".join(row[0] for row in con.execute(f"DESCRIBE SELECT * FROM {expected}").fetchall())
            loaded = f"(SELECT {columns} FROM holiday_calendar.{table})"
            result[table] = con.execute(f"""
                SELECT count(*) FROM (
                    (SELECT * FROM {loaded} EXCEPT SELECT * FROM {expected})
                    UNION ALL
                    (SELECT * FROM {expected} EXCEPT SELECT * FROM {loaded})
                )
            """).fetchone()[0]
        return result


def test_initial_load_then_only_changes(serve, first_release_only, tmp_path):
    run(serve(first_release_only), tmp_path)
    assert set(differences(tmp_path, V1 / "releases" / "2026.01.15").values()) == {0}

    # The second run sees the second release: 2026 rows are deleted, 2027 rows added.
    run(serve(FIXTURE), tmp_path)
    assert set(differences(tmp_path, V1 / "latest").values()) == {0}


def test_load_everything_at_once(base_url, tmp_path):
    run(base_url, tmp_path)
    assert set(differences(tmp_path, V1 / "latest").values()) == {0}
