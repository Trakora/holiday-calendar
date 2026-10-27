# Trakora holiday calendar

Public and school holidays for every municipality in Germany, with working days and bridge days, as tables for data warehouses and BI tools. The tables are published at `https://data.trakora.com/holiday-calendar/v1/` and documented at [trakora.com/holiday-calendar](https://trakora.com/holiday-calendar) ([German](https://trakora.de/feiertagskalender)).

Why municipalities: Assumption Day is a public holiday in 1,708 of Bavaria's 2,056 municipalities. Munich has it, Nuremberg doesn't.

This repository holds the source data and its format, and loaders for dlt, dbt, Spark, Snowflake, Power BI, Python, Go and Java. Trakora builds the tables from the data and publishes them; that build is not part of the repository.

## Quick start

DuckDB attaches the database over HTTPS and only fetches what a query needs:

```sql
ATTACH 'https://data.trakora.com/holiday-calendar/v1/latest/holiday_calendar.duckdb' (READ_ONLY);

SELECT date, holiday_name, school_holiday_name
FROM holiday_calendar.region_day
WHERE region_name = 'Nürnberg' AND year(date) = 2027
  AND (is_public_holiday OR is_school_holiday);
```

Every table is also available as Parquet and CSV under `latest/`, e.g. `latest/fact_calendar_day.parquet`.

## Rules

[`rules/`](rules) holds what the tables are built from: holidays as rules, school holidays as periods, municipalities and the municipalities with holidays of their own, one folder per country. The format is the same for every country and described in [docs/format.md](docs/format.md). The finished tables are on data.trakora.com.

```sh
pip install pyyaml
python tools/check.py DE 2027 DE-HH    # checks the rules, then lists 2027 for Hamburg
```

A date is wrong, missing, or you want to add a country? See [CONTRIBUTING.md](CONTRIBUTING.md). Every change needs a source and a test in `expected.yaml`, and CI checks it.

## Pipelines

| Target | Folder | Loads | Tested in CI |
| --- | --- | --- | --- |
| Postgres, Snowflake, BigQuery, Databricks, Redshift, MS SQL, Fabric, ClickHouse, DuckDB and other dlt destinations | [`dlt/`](dlt) | incremental | DuckDB |
| dbt, on top of the loaded tables | [`dbt/`](dbt) | models and tests | DuckDB |
| Databricks | [`databricks/`](databricks) | incremental, Delta MERGE | notebook yes, bundle not deployed |
| Microsoft Fabric, any Spark with Delta Lake | [`spark/`](spark) | incremental, Delta MERGE | Spark 4, Delta 4 |
| Snowflake without dlt | [`snowflake/`](snowflake) | full refresh | no |
| Power BI, Excel | [`powerbi/`](powerbi) | full refresh | no |
| DuckDB | [`python/`](python) | incremental | yes |
| Go | [`go/`](go) | change files into a folder | yes |
| Java | [`java/`](java) | working-day lookups | yes |

CI runs everything marked as tested against two small releases in `tests/fixture`.

Incremental means: the first run loads everything, later runs load only releases published since, and rows deleted in a release are deleted in the target. How that works is in [docs/data-contract.md](docs/data-contract.md).

### dlt

```sh
cd dlt
pip install -r requirements.txt
python pipeline.py postgres    # destination name: snowflake, bigquery, databricks, mssql, duckdb, ...
```

Credentials go into `.dlt/secrets.toml` or environment variables, see [dlt credentials](https://dlthub.com/docs/general-usage/credentials/setup). The last loaded release is kept in the pipeline state.

### dbt

```yaml
# packages.yml
packages:
  - git: https://github.com/Trakora/holiday-calendar.git
    subdirectory: dbt
    revision: main
```

Load the tables first, e.g. with dlt. If they are not in the schema `holiday_calendar`, set the var `holiday_calendar_schema`. The package adds source definitions with key tests and two models: `holiday_calendar__region_day` (every region on every day) and `holiday_calendar__workday` (for adding working days, see below).

### Databricks

```sh
cd databricks
databricks bundle deploy --var catalog=main
databricks bundle run holiday_calendar_sync
```

Deploys a job that runs [`spark/holiday_calendar_sync.py`](spark/holiday_calendar_sync.py) on serverless compute every Monday at 06:00 Europe/Berlin and writes Delta tables to `main.holiday_calendar`.

### Microsoft Fabric

Create a notebook attached to a lakehouse, paste [`spark/holiday_calendar_sync.py`](spark/holiday_calendar_sync.py) and run it. For a lakehouse without schemas call `sync(spark, "")`. Schedule the notebook to stay current.

### Snowflake

Run [`snowflake/holiday_calendar.sql`](snowflake/holiday_calendar.sql) with a role that can create integrations. It creates an external access integration for `data.trakora.com`, a procedure that replaces all tables with the current release, and a weekly task.

### Power BI and Excel

Create a blank query named `HolidayCalendar` with the code from [`powerbi/HolidayCalendar.pq`](powerbi/HolidayCalendar.pq), then one query per table:

```
= HolidayCalendar("fact_calendar_day")
```

Column types are taken from the manifest.

### Python and DuckDB

```sh
pip install duckdb
python python/sync_duckdb.py holidays.duckdb
```

### Go

```sh
cd go
go run . -dir holiday-calendar
```

Downloads the change files of new releases into a folder, checks their SHA-256 and records the last release in `state.json`. Use `-format parquet` for Parquet instead of CSV.

### Java

```java
try (WorkingDays days = new WorkingDays()) {
    LocalDate delivery = days.addWorkdays("DE-09564000", LocalDate.of(2027, 5, 26), 3);
}
```

Copy the class or build the module with `mvn package`. It uses the DuckDB JDBC driver and reads two tables into memory, a few megabytes.

### Other tools

Airbyte, Azure Data Factory, Fivetran or anything else with an HTTP source: read `manifest.json`, load the files listed under `changes` in order, merge on `primary_key`. See [docs/data-contract.md](docs/data-contract.md).

## Working days

`fact_calendar_day.workday_index` numbers the working days of a calendar profile. Days off carry the number of the working day before them. So n working days after a date is the working day with that date's index plus n, and the working days between two dates are the difference of their indexes:

```sql
SELECT target.date
FROM fact_calendar_day AS start
JOIN fact_calendar_day AS target
  ON target.calendar_profile_id = start.calendar_profile_id
 AND target.is_workday
 AND target.workday_index = start.workday_index + 3
WHERE start.calendar_profile_id = 'DE-BY' AND start.date = DATE '2027-05-26';
```

A municipality's calendar profile is in `bridge_region_profile`, by `region_id` (country and AGS, e.g. `DE-09564000`) and validity period. School holidays don't change working days: they are a column of their own.

## Development

```sh
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python tools/check.py  # the data
.venv/bin/pytest                 # format and clients; the Spark test needs Java 17 or later
(cd go && go test ./...)
(cd java && mvn test)
```

## License

The code is MIT licensed ([LICENSE](LICENSE)). The rules in `rules/` and the tables on data.trakora.com are licensed under [CC BY 4.0](rules/LICENSE). When you pass it on, credit: "Trakora Holiday Calendar, CC BY 4.0. Contains data from: Federal Statistical Office of Germany (Destatis), municipality register and Census 2022". The manifest has the current attribution under `attribution`.
