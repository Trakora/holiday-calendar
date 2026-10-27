"""Installs the dbt package into a throwaway project and runs it on DuckDB."""

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import duckdb

from test_python import sync_duckdb

PACKAGE = Path(__file__).parents[1] / "dbt"
DBT = Path(sys.executable).parent / "dbt"

PROJECT = """
name: example
version: "1.0.0"
config-version: 2
profile: example
vars:
  holiday_calendar_schema: main
"""

PROFILES = """
example:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: {database}
"""

# An order on Wednesday, May 26, 2027: the next day is Corpus Christi in Baden-Württemberg,
# not in Berlin.
DELIVERY = """
with orders as (
    select * from (values (1, date '2027-05-26', 'DE-BE'), (2, date '2027-05-26', 'DE-BW'))
        as t(order_id, order_date, calendar_profile_id)
)
select o.order_id, w.date as delivery_date
from orders as o
join {{ source('holiday_calendar', 'fact_calendar_day') }} as ordered
    on ordered.calendar_profile_id = o.calendar_profile_id and ordered.date = o.order_date
join {{ ref('holiday_calendar__workday') }} as w
    on w.calendar_profile_id = o.calendar_profile_id and w.workday_index = ordered.workday_index + 1
"""


def test_package_builds_and_adds_workdays(base_url, tmp_path):
    database = tmp_path / "warehouse.duckdb"
    sync_duckdb.sync(str(database), base_url)

    project = tmp_path / "example"
    (project / "models").mkdir(parents=True)
    (project / "dbt_project.yml").write_text(PROJECT)
    (project / "packages.yml").write_text(f"packages:\n  - local: {PACKAGE}\n")
    (project / "profiles.yml").write_text(PROFILES.format(database=database))
    (project / "models" / "delivery.sql").write_text(DELIVERY)

    env = {**os.environ, "DBT_PROFILES_DIR": str(project), "DBT_SEND_ANONYMOUS_USAGE_STATS": "false"}
    for command in (["deps"], ["build"]):
        result = subprocess.run([DBT, *command], cwd=project, env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr

    with duckdb.connect(str(database)) as con:
        rows = con.execute("SELECT order_id, delivery_date FROM main.delivery ORDER BY order_id").fetchall()
        assert rows == [(1, date(2027, 5, 27)), (2, date(2027, 5, 28))]
        nuremberg = con.execute(
            "SELECT holiday_name FROM main.holiday_calendar__region_day WHERE region_id = 'DE-09564000' AND date = '2027-11-01'"
        ).fetchone()
        assert nuremberg == ("All Saints' Day",)
