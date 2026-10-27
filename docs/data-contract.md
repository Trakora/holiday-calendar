# Data contract

Base URL: `https://data.trakora.com/holiday-calendar/v1/`. All paths below are relative to it. No sign-up, no key.

## Files

```text
manifest.json                            current release and all releases
latest/holiday_calendar.duckdb           all tables in one DuckDB file
latest/{table}.parquet, latest/{table}.csv   current state of every table
releases/{version}/{table}.parquet       state of every table per release, never changes
changes/{table}/{version}.parquet|.csv   changes per release, never change
```

CSV is UTF-8, comma-separated, with a header row. Dates are ISO 8601, booleans `true`/`false`, NULL is an empty field.

`releases/` and `changes/` are immutable and can be cached forever. `manifest.json` and `latest/` are replaced on every release.

## Manifest

```json
{
  "dataset": "Trakora Holiday Calendar",
  "schema_version": 1,
  "license": { "name": "CC BY 4.0", "url": "https://creativecommons.org/licenses/by/4.0/" },
  "attribution": "Trakora Holiday Calendar, CC BY 4.0. Contains data from: …",
  "version": "2026.10.26",
  "release_seq": 1,
  "released_at": "2026-10-26T18:00:00+00:00",
  "first_date": "2010-01-01",
  "last_date": "2035-12-31",
  "database": { "path": "latest/holiday_calendar.duckdb", "sha256": "…", "bytes": 5517312 },
  "tables": [
    {
      "name": "fact_calendar_day",
      "description": "…",
      "primary_key": ["calendar_profile_id", "date"],
      "rows": 170928,
      "columns": [{ "name": "date", "type": "DATE", "description": "…" }],
      "snapshot": {
        "parquet": { "path": "releases/2026.10.26/fact_calendar_day.parquet", "sha256": "…", "bytes": 889220 },
        "csv": { "path": "latest/fact_calendar_day.csv", "sha256": "…", "bytes": 19547226 }
      }
    }
  ],
  "releases": [
    {
      "version": "2026.10.26",
      "release_seq": 1,
      "released_at": "2026-10-26T18:00:00+00:00",
      "changes": [
        {
          "table": "fact_calendar_day",
          "upserts": 170928,
          "deletes": 0,
          "parquet": { "path": "changes/fact_calendar_day/2026.10.26.parquet", "sha256": "…", "bytes": 890083 },
          "csv": { "path": "changes/fact_calendar_day/2026.10.26.csv", "sha256": "…", "bytes": 21085595 }
        }
      ]
    }
  ]
}
```

Shortened to one table and one column. Column types are DuckDB types: `VARCHAR`, `BOOLEAN`, `INTEGER`, `BIGINT`, `DOUBLE`, `DATE`. The same descriptions are stored as comments in the DuckDB file.

## Columns

Names and descriptions are English. Columns without a suffix hold English text, the same column with `_local` holds the language of the country (`dim_country.language`): `holiday_name` is "All Saints' Day", `holiday_name_local` is "Allerheiligen". `dim_date` also has German weekday and month names in `_de` columns. Region and district names are the official names.

Every table has `country_code` or a key that starts with it, so new countries are new rows, not new tables. Regions are identified by `region_id`, the country and the official code (`DE-09564000`); `region_code` is the official code alone, in Germany the AGS.

`holiday_id` is a stable English identifier such as `assumption-day` or `summer`. Filter on it, not on names. `holiday_level` is `national`, `subdivision` or `municipal`. On days with two public holidays, IDs are comma-separated and names joined with ` / `.

`is_school_holiday` is empty (NULL) outside the school years with data, see `school_holidays_from` and `school_holidays_until` in `dim_calendar_profile`. Within them, false means a school day.

## Incremental loads

1. Read `manifest.json`. `releases` is sorted by `release_seq`.
2. Take every release with a `release_seq` above the last one you loaded and load its `changes` in order.
3. Each row has two extra columns. `_op` is `upsert` (insert, or replace the row with the same primary key) or `delete` (remove it). `_release_seq` is the release it belongs to.
4. Store the highest `release_seq` you applied.

The first release contains every row as `upsert`. Applying all change files from the start gives exactly the state in `latest/`. Within one change file, each primary key appears at most once.

## Versioning

Releases are named by date (`2026.10.26`). Within `v1`, rows and columns can be added and values corrected. A new column appears in the change files and should be added to the target table, the clients in this repository do that. Removing or renaming a column or changing its type means a new `v2` path, `v1` stays as it is.
