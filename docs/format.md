# Data format

Every country is a folder in `rules/`, named by its ISO 3166-1 code. The same format works for every country: holidays are rules, school holidays are periods, and where holidays differ below the subdivision level, regions point to their own calendar profile.

```text
rules/DE/
├── country.yaml            name, time zone, weekend, subdivisions, profiles
├── public-holidays.yaml    public holidays as rules
├── school-holidays/        one file per school year, e.g. 2026-27.yaml
├── regions.csv             municipalities (optional)
├── region-profiles.csv     municipalities with their own profile (optional)
├── expected.yaml           known dates, checked on every pull request
└── README.md               sources
```

Only `country.yaml` and `public-holidays.yaml` are required. `python tools/check.py` reads everything and reports the first mistake with file and entry.

## Codes and profiles

A calendar profile is a set of regions with the same holidays. Every subdivision is a profile with its own ISO 3166-2 code (`DE-HH`). Where holidays differ inside a subdivision, more profiles split it. Their codes start with the subdivision code: `DE-BY-MH` is Bavaria with Assumption Day, `DE-BY-AU` is Augsburg. A country without subdivisions has one profile, the country code.

Wherever a rule says where it applies, a code means that profile and every profile below it:

| Code | Matches |
| --- | --- |
| `DE` | every profile in Germany |
| `DE-BY` | `DE-BY`, `DE-BY-MH`, `DE-BY-AU` |
| `DE-BY-MH` | only `DE-BY-MH` |

IDs of holidays are lowercase English words with hyphens: `assumption-day`, `summer`. They stay stable, names can change.

## country.yaml

```yaml
country: DE
name: Germany
name_local: Deutschland
language: de
timezone: Europe/Berlin
weekend: [saturday, sunday]
school_year_starts: "08-01"
attribution: Federal Statistical Office of Germany (Destatis), municipality register and Census 2022

subdivisions:
  DE-BY: { name: Bavaria, name_local: Bayern }

profiles:
  DE-BY-MH:
    name: Bavaria, municipalities with Assumption Day
    name_local: Bayern, Gemeinden mit Mariä Himmelfahrt

regions:
  type: municipality
  code: AGS

school_holidays:
  summer: { name: Summer holidays, name_local: Sommerferien }
```

| Field | |
| --- | --- |
| `country` | ISO 3166-1 alpha-2, same as the folder |
| `name`, `name_local` | English and in the main language of the country. Every name in the format comes as such a pair |
| `language` | ISO 639-1 code of `name_local` |
| `timezone` | IANA time zone, for the length of days with a daylight saving switch |
| `weekend` | days that are not working days, default `[saturday, sunday]` |
| `school_year_starts` | first day of a school year, default `"08-01"`. Use `"01-01"` where the school year is the calendar year |
| `attribution` | sources that must be credited when the data is passed on, if any |
| `subdivisions` | ISO 3166-2 codes with names |
| `profiles` | additional profiles, or a different name for a subdivision's profile |
| `regions` | only with `regions.csv`: what a region is and the name of its official code |
| `school_holidays` | IDs and names of the school holidays used in `school-holidays/` |

## public-holidays.yaml

```yaml
holidays:
  - id: assumption-day
    name: Assumption Day
    name_local: Mariä Himmelfahrt
    date: "08-15"
    in: [DE-BY-MH, DE-BY-AU]
    level: municipal
    legal_basis: Art. 1 Abs. 1 Nr. 2 BayFTG
    source: https://www.gesetze-bayern.de/Content/Document/BayFTG-1
    note: Only in municipalities with more Catholic than Protestant residents
```

Each entry is one rule. A holiday whose regions or validity changed over time has one rule per period, all with the same `id` and names.

| Field | |
| --- | --- |
| `id`, `name`, `name_local` | required |
| one date rule | required, see below |
| `in` | required, codes as above |
| `level` | `national`, `subdivision` or `municipal`. Default: `national` for the country code, `subdivision` otherwise |
| `from`, `until` | first and last day the rule applies, both inclusive |
| `legal_basis`, `source`, `note` | where the rule comes from. Please always give a source |

Date rules:

| Rule | Example | Meaning |
| --- | --- | --- |
| `date: "MM-DD"` | `date: "12-25"` | every year. `"02-29"` only in leap years |
| `date: YYYY-MM-DD` | `date: 2020-05-08` | once |
| `dates: [...]` | `dates: [2026-03-20, 2027-03-10]` | a list of dates, for holidays that follow a lunar calendar or are announced each year |
| `easter: N` | `easter: -2` | N days after Easter Sunday (Gregorian), negative for before |
| `orthodox_easter: N` | `orthodox_easter: 1` | N days after Orthodox Easter Sunday |
| weekday before a date | `date: { weekday: wednesday, before: "11-23" }` | the last such weekday strictly before the date |
| nth weekday of a month | `date: { weekday: thursday, nth: 4, month: 11 }` | `nth` 1 to 5, or -1 for the last |

Not supported yet: substitute days when a holiday falls on a weekend, half days, and holidays that only apply to some groups of people. If a country needs one of these, open an issue first.

## school-holidays/

One file per school year, named like the school year with a hyphen: `2026-27.yaml`, or `2026.yaml` where the school year is the calendar year.

```yaml
# Source: KMK, Ferien im Schuljahr 2026/27
school_year: 2026/27
source: https://www.kmk.org/fileadmin/Dateien/pdf/Ferienkalender/FER2026_27.pdf
periods:
  DE-BW:
    autumn: [2026-10-26/2026-10-30, 2026-10-31]
    christmas: 2026-12-23/2027-01-09
    summer: 2027-07-29/2027-09-11
  DE-BY:
    ...
```

Under `periods`, each code (as above) lists its school holidays. A value is a single date, an interval `first/last` (both inclusive, as the authority publishes it), or a list of both. Holidays belong to the school year they end in, so summer holidays are in the file of the school year before them.

A file must cover the whole school year for every code it lists. Inside the school years with a file, a day without school holidays counts as a school day. Outside, school holidays are unknown and the built tables leave them empty.

## regions.csv

Regions below the subdivision level, in Germany the municipalities. Only needed where holidays differ between them or where people want to look up a place.

| Column | |
| --- | --- |
| `code` | official code in the country, required (AGS in Germany) |
| `name` | official name, required |
| `subdivision_code` | ISO 3166-2, required |
| `district_code`, `district_name` | level in between, if there is one |
| `population` | number of residents |
| `postcode` | postcode of the administrative seat |
| `latitude`, `longitude` | centre, decimal degrees |
| `urbanisation` | EU degree of urbanisation: `densely populated`, `intermediate density` or `thinly populated` |

## region-profiles.csv

Regions whose profile is not their subdivision's, with validity periods. Every region not listed, and every day outside a listed period, uses the subdivision's profile.

```csv
code,calendar_profile_id,valid_from,valid_until
09572115,DE-BY-MH,,2013-12-31
09572115,DE-BY-MH,2025-01-01,
```

Empty `valid_from` means from the start of the data, empty `valid_until` means open-ended. Periods of one region must not overlap, and the profile must belong to the region's subdivision.

## expected.yaml

Known dates that must hold. They are the tests for the data: add one for every rule or period you add or change.

```yaml
- { date: 2026-08-15, region: "09162000", holiday: assumption-day }  # Munich
- { date: 2026-08-15, profile: DE-BY, holiday: null }
- { date: 2026-10-26, profile: DE-BW, school_holiday: autumn }
```

Each entry has a `date`, either a `profile` or a `region` code, and `holiday` and/or `school_holiday`: the expected ID, or `null` for none.

## Checks

`python tools/check.py` stops at the first of these and names file and entry:

- required fields, valid codes, dates and IDs
- every `in` and every code in `school-holidays/` matches at least one profile
- rules with the same `id` have the same names, and no ID is both a public and a school holiday
- school holidays start inside their school year and do not overlap within a profile
- every region has a known subdivision, codes are unique, numbers are numbers
- region profiles belong to the region's subdivision and do not overlap
- every entry of `expected.yaml` holds
