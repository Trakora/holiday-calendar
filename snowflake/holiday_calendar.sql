-- Loads the current release of the holiday calendar into Snowflake and refreshes it weekly.
-- Replaces the tables completely on each run. For incremental loads use the dlt source
-- in this repo with the Snowflake destination.
--
-- Needs a role that may create network rules and external access integrations. The task
-- runs on serverless compute, which needs EXECUTE MANAGED TASK; add WAREHOUSE = ... to the
-- task to use a warehouse instead.

CREATE OR REPLACE NETWORK RULE holiday_calendar_egress
  MODE = EGRESS TYPE = HOST_PORT VALUE_LIST = ('data.trakora.com');

CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION holiday_calendar_access
  ALLOWED_NETWORK_RULES = (holiday_calendar_egress) ENABLED = TRUE;

CREATE OR REPLACE PROCEDURE load_holiday_calendar()
  RETURNS STRING
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.12'
  PACKAGES = ('snowflake-snowpark-python', 'pandas', 'pyarrow', 'requests')
  HANDLER = 'run'
  EXTERNAL_ACCESS_INTEGRATIONS = (holiday_calendar_access)
AS $$
import io

import pyarrow.parquet as pq
import requests

BASE_URL = "https://data.trakora.com/holiday-calendar/v1"


def run(session):
    manifest = requests.get(f"{BASE_URL}/manifest.json", timeout=60).json()
    loaded = []
    for table in manifest["tables"]:
        content = requests.get(f"{BASE_URL}/latest/{table['name']}.parquet", timeout=120).content
        frame = pq.read_table(io.BytesIO(content)).to_pandas()
        session.write_pandas(frame, table["name"].upper(), auto_create_table=True, overwrite=True,
                             quote_identifiers=False, use_logical_type=True)
        loaded.append(f"{table['name']} ({len(frame)})")
    return f"Release {manifest['version']}: " + ", ".join(loaded)
$$;

CALL load_holiday_calendar();

CREATE OR REPLACE TASK refresh_holiday_calendar
  SCHEDULE = 'USING CRON 0 6 * * 1 Europe/Berlin'
AS CALL load_holiday_calendar();

ALTER TASK refresh_holiday_calendar RESUME;
