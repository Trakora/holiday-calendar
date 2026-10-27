"""Loads the holiday calendar into a dlt destination, DuckDB unless another is given.

    pip install -r requirements.txt
    python pipeline.py                 # local DuckDB file
    python pipeline.py postgres        # credentials in .dlt/secrets.toml or environment
"""

import sys

import dlt

from holiday_calendar import holiday_calendar

if __name__ == "__main__":
    pipeline = dlt.pipeline(
        pipeline_name="holiday_calendar",
        destination=sys.argv[1] if len(sys.argv) > 1 else "duckdb",
        dataset_name="holiday_calendar",
    )
    print(pipeline.run(holiday_calendar()))
