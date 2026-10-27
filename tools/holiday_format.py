"""Reads, checks and evaluates the holiday rules in rules/<COUNTRY>/.

Reference implementation of docs/format.md. Needs only PyYAML.

    from holiday_format import load_country
    germany = load_country("rules/DE")
    germany.public_holidays(2027, 2027)
"""

import csv
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import yaml

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
LEVELS = ("national", "subdivision", "municipal")
OPEN_END = date(9999, 12, 31)

ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
COUNTRY = re.compile(r"^[A-Z]{2}$")
SUBDIVISION = re.compile(r"^[A-Z]{2}-[A-Z0-9]{1,3}$")
PROFILE = re.compile(r"^[A-Z]{2}(-[A-Z0-9]+)+$")
MONTH_DAY = re.compile(r"^\d{2}-\d{2}$")


class FormatError(ValueError):
    """A mistake in the data. The message names the file and the entry."""


@dataclass(frozen=True, slots=True)
class Profile:
    id: str
    subdivision: str
    name: str
    name_local: str


@dataclass(frozen=True, slots=True)
class Rule:
    holiday_id: str
    name: str
    name_local: str
    kind: str  # fixed, dates, easter, orthodox_easter, weekday_before, nth_weekday
    value: tuple
    applies_to: tuple[str, ...]
    profiles: tuple[str, ...]
    level: str
    valid_from: date | None
    valid_until: date | None
    legal_basis: str | None
    source: str | None
    note: str | None

    def dates_in(self, year: int) -> list[date]:
        """The rule's dates in a year, empty if it does not apply that year."""
        match self.kind, self.value:
            case "fixed", (month_day,):
                try:
                    days = [date.fromisoformat(f"{year}-{month_day}")]
                except ValueError:  # 02-29 outside leap years
                    days = []
            case "dates", dates:
                days = [d for d in dates if d.year == year]
            case "easter", (offset,):
                days = [easter_sunday(year) + timedelta(days=offset)]
            case "orthodox_easter", (offset,):
                days = [orthodox_easter_sunday(year) + timedelta(days=offset)]
            case "weekday_before", (weekday, before):
                limit = date.fromisoformat(f"{year}-{before}")
                days = [limit - timedelta(days=(limit.weekday() - weekday - 1) % 7 + 1)]
            case "nth_weekday", (weekday, nth, month):
                days = [_nth_weekday(year, month, weekday, nth)]
        return [d for d in days if _within(d, self.valid_from, self.valid_until)]

    def describe(self) -> str:
        match self.kind, self.value:
            case "fixed", (month_day,):
                return month_day
            case "dates", dates:
                return ", ".join(d.isoformat() for d in dates)
            case "easter" | "orthodox_easter", (offset,):
                label = "Easter Sunday" if self.kind == "easter" else "Orthodox Easter Sunday"
                return f"{label} {offset:+d}" if offset else label
            case "weekday_before", (weekday, before):
                return f"{WEEKDAYS[weekday]} before {before}"
            case "nth_weekday", (weekday, nth, month):
                position = "last" if nth == -1 else {1: "1st", 2: "2nd", 3: "3rd"}.get(nth, f"{nth}th")
                return f"{position} {WEEKDAYS[weekday]} of month {month}"
        raise ValueError(self.kind)


@dataclass(frozen=True, slots=True)
class SchoolPeriod:
    school_year: str
    holiday_id: str
    applies_to: str
    profiles: tuple[str, ...]
    start: date
    end: date
    source: str | None


@dataclass(frozen=True, slots=True)
class Region:
    code: str
    name: str
    subdivision: str
    row: dict  # every column of regions.csv as text


@dataclass(frozen=True, slots=True)
class RegionProfile:
    code: str
    profile: str
    valid_from: date | None
    valid_until: date | None


@dataclass(slots=True)
class Country:
    code: str
    name: str
    name_local: str
    language: str
    timezone: str
    weekend: tuple[int, ...]  # ISO weekdays, Monday = 1
    school_year_starts: str
    subdivisions: dict[str, tuple[str, str]]
    profiles: dict[str, Profile]
    rules: list[Rule]
    school_holidays: dict[str, tuple[str, str]] = field(default_factory=dict)
    school_periods: list[SchoolPeriod] = field(default_factory=list)
    attribution: str | None = None
    region_type: str | None = None
    region_code_name: str | None = None
    regions: dict[str, Region] = field(default_factory=dict)
    region_profiles: list[RegionProfile] = field(default_factory=list)
    expectations: list[dict] = field(default_factory=list)

    def public_holidays(self, first_year: int, last_year: int) -> list[tuple[date, str, Rule]]:
        """(date, profile, rule) for every public holiday in the years."""
        return [(day, profile, rule)
                for year in range(first_year, last_year + 1)
                for rule in self.rules
                for day in rule.dates_in(year)
                for profile in rule.profiles]

    def school_days(self) -> list[tuple[date, str, SchoolPeriod]]:
        """(date, profile, period) for every day of school holidays."""
        return [(period.start + timedelta(days=i), profile, period)
                for period in self.school_periods
                for i in range((period.end - period.start).days + 1)
                for profile in period.profiles]

    def school_coverage(self, profile: str) -> tuple[date, date] | None:
        """First and last day of the school years with data for a profile. Within them a day
        without school holidays is a school day; outside them it is unknown."""
        years = sorted({p.school_year for p in self.school_periods if profile in p.profiles})
        if not years:
            return None
        first, _ = self._school_year_span(years[0])
        _, last = self._school_year_span(years[-1])
        return first, last

    def profile_of(self, code: str, day: date) -> str:
        """Calendar profile of a region on a day."""
        for assignment in self.region_profiles:
            if assignment.code == code and _within(day, assignment.valid_from, assignment.valid_until):
                return assignment.profile
        return self.regions[code].subdivision

    def holidays_on(self, profile: str, day: date) -> list[str]:
        return [rule.holiday_id for rule in self.rules if profile in rule.profiles and day in rule.dates_in(day.year)]

    def school_holidays_on(self, profile: str, day: date) -> list[str]:
        return [p.holiday_id for p in self.school_periods if profile in p.profiles and p.start <= day <= p.end]

    def failed_expectations(self) -> list[str]:
        """Every entry of expected.yaml that does not hold, as a readable line."""
        failures = []
        for entry in self.expectations:
            day = entry["date"]
            profile = entry.get("profile") or self.profile_of(entry["region"], day)
            where = entry.get("region") or profile
            for key, actual in (("holiday", self.holidays_on), ("school_holiday", self.school_holidays_on)):
                if key not in entry:
                    continue
                found = actual(profile, day)
                expected = entry[key]
                if (expected is None and found) or (expected is not None and expected not in found):
                    failures.append(f"{self.code} {day} {where}: expected {key} {expected}, found {', '.join(found) or 'none'}")
        return failures

    def _school_year_span(self, school_year: str) -> tuple[date, date]:
        start = date.fromisoformat(f"{school_year[:4]}-{self.school_year_starts}")
        next_start = date.fromisoformat(f"{int(school_year[:4]) + 1}-{self.school_year_starts}")
        return start, next_start - timedelta(days=1)


def load_all(data: Path | str) -> list[Country]:
    return [load_country(path) for path in sorted(Path(data).iterdir()) if (path / "country.yaml").exists()]


def load_country(folder: Path | str) -> Country:
    folder = Path(folder)
    meta = _yaml(folder / "country.yaml")
    where = f"{folder.name}/country.yaml"

    code = _required(meta, "country", where)
    if not COUNTRY.match(code) or code != folder.name:
        raise FormatError(f"{where}: country must be the ISO 3166-1 code and match the folder name")
    for key in ("name", "name_local", "language", "timezone"):
        _required(meta, key, where)
    weekend = tuple(_weekday(day, where) + 1 for day in meta.get("weekend", ["saturday", "sunday"]))
    school_year_starts = str(meta.get("school_year_starts", "08-01"))
    _check_month_day(school_year_starts, where)

    subdivisions = {}
    for sub, names in (meta.get("subdivisions") or {}).items():
        if not SUBDIVISION.match(sub) or not sub.startswith(f"{code}-"):
            raise FormatError(f"{where}: {sub} is not an ISO 3166-2 code of {code}")
        subdivisions[sub] = (_required(names, "name", f"{where} {sub}"), _required(names, "name_local", f"{where} {sub}"))

    # Every subdivision is a profile; without subdivisions the country is the only one.
    profiles = {sub: Profile(sub, sub, *names) for sub, names in subdivisions.items()}
    if not subdivisions:
        profiles[code] = Profile(code, code, meta["name"], meta["name_local"])
    for pid, value in (meta.get("profiles") or {}).items():
        sub = next((s for s in subdivisions if pid == s or pid.startswith(f"{s}-")), None)
        if not PROFILE.match(pid) or sub is None:
            raise FormatError(f"{where}: profile {pid} must start with the code of its subdivision")
        profiles[pid] = Profile(pid, sub, _required(value, "name", f"{where} {pid}"), _required(value, "name_local", f"{where} {pid}"))

    country = Country(
        code=code, name=meta["name"], name_local=meta["name_local"], language=meta["language"],
        timezone=meta["timezone"], weekend=weekend, school_year_starts=school_year_starts,
        subdivisions=subdivisions, profiles=profiles, rules=[], attribution=meta.get("attribution"),
    )

    holidays = _yaml(folder / "public-holidays.yaml")
    country.rules = [_rule(raw, country, f"{code}/public-holidays.yaml") for raw in holidays.get("holidays") or []]
    names: dict[str, tuple[str, str]] = {}
    for rule in country.rules:
        if names.setdefault(rule.holiday_id, (rule.name, rule.name_local)) != (rule.name, rule.name_local):
            raise FormatError(f"{code}/public-holidays.yaml {rule.holiday_id}: every rule with this id needs the same names")

    for key, names in (meta.get("school_holidays") or {}).items():
        if not ID.match(key):
            raise FormatError(f"{where}: school holiday {key} must consist of lowercase letters, digits and hyphens")
        country.school_holidays[key] = (_required(names, "name", f"{where} {key}"), _required(names, "name_local", f"{where} {key}"))
    clash = set(country.school_holidays) & {r.holiday_id for r in country.rules}
    if clash:
        raise FormatError(f"{where}: {', '.join(sorted(clash))} used for a public and a school holiday")
    for path in sorted((folder / "school-holidays").glob("*.yaml")):
        country.school_periods += _school_year(path, country)
    _check_school_overlaps(country)

    if meta.get("regions"):
        country.region_type = _required(meta["regions"], "type", f"{where} regions")
        country.region_code_name = meta["regions"].get("code")
        country.regions = _regions(folder / "regions.csv", country)
        if (folder / "region-profiles.csv").exists():
            country.region_profiles = _region_profiles(folder / "region-profiles.csv", country)

    if (folder / "expected.yaml").exists():
        country.expectations = _expectations(folder / "expected.yaml", country)
    return country


def easter_sunday(year: int) -> date:
    """Easter Sunday in the Gregorian calendar (Meeus/Jones/Butcher algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def orthodox_easter_sunday(year: int) -> date:
    """Orthodox Easter Sunday (Julian computus), as a Gregorian date."""
    a, b, c = year % 4, year % 7, year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month, day = divmod(d + e + 114, 31)
    julian_to_gregorian = year // 100 - year // 400 - 2
    return date(year, month, day + 1) + timedelta(days=julian_to_gregorian)


def _rule(raw: dict, country: Country, file: str) -> Rule:
    holiday_id = str(raw.get("id", ""))
    where = f"{file} {holiday_id or raw}"
    if not ID.match(holiday_id):
        raise FormatError(f"{where}: id must consist of lowercase letters, digits and hyphens")
    for key in ("name", "name_local", "in"):
        _required(raw, key, where)

    kinds = [key for key in ("date", "dates", "easter", "orthodox_easter") if key in raw]
    if len(kinds) != 1:
        raise FormatError(f"{where}: set exactly one of date, dates, easter and orthodox_easter")
    kind, value = _date_rule(kinds[0], raw[kinds[0]], where)

    applies_to = tuple(str(p) for p in raw["in"])
    matched: list[str] = []
    for pattern in applies_to:
        hits = _matching_profiles(pattern, country)
        if not hits:
            raise FormatError(f"{where}: {pattern} matches no profile")
        matched += [h for h in hits if h not in matched]

    level = raw.get("level") or ("national" if applies_to == (country.code,) else "subdivision")
    if level not in LEVELS:
        raise FormatError(f"{where}: level must be national, subdivision or municipal")

    valid_from, valid_until = _optional_date(raw.get("from"), where), _optional_date(raw.get("until"), where)
    if valid_from and valid_until and valid_from > valid_until:
        raise FormatError(f"{where}: from is after until")

    return Rule(holiday_id, raw["name"], raw["name_local"], kind, value, applies_to, tuple(matched), level,
                valid_from, valid_until, raw.get("legal_basis"), raw.get("source"), raw.get("note"))


def _date_rule(key: str, value, where: str) -> tuple[str, tuple]:
    if key in ("easter", "orthodox_easter"):
        if not isinstance(value, int) or isinstance(value, bool):
            raise FormatError(f"{where}: {key} must be a number of days")
        return key, (value,)
    if key == "dates":
        if not isinstance(value, list) or not value:
            raise FormatError(f"{where}: dates must be a list of dates")
        return "dates", tuple(sorted(_date(v, where) for v in value))
    if isinstance(value, dict):
        weekday = _weekday(value.get("weekday"), where)
        if "before" in value:
            _check_month_day(str(value["before"]), where)
            return "weekday_before", (weekday, str(value["before"]))
        nth, month = value.get("nth"), value.get("month")
        if nth not in (1, 2, 3, 4, 5, -1) or month not in range(1, 13):
            raise FormatError(f"{where}: a weekday rule needs before, or nth (1 to 5 or -1) and month")
        return "nth_weekday", (weekday, nth, month)
    if isinstance(value, date) or (isinstance(value, str) and len(value) == 10):
        return "dates", (_date(value, where),)
    _check_month_day(str(value), where)
    return "fixed", (str(value),)


def _matching_profiles(pattern: str, country: Country) -> list[str]:
    """A code matches the profile with that code and every profile below it."""
    return [p for p in country.profiles if pattern == country.code or p == pattern or p.startswith(f"{pattern}-")]


def _school_year(path: Path, country: Country) -> list[SchoolPeriod]:
    where = f"{country.code}/school-holidays/{path.name}"
    data = _yaml(path)
    school_year = str(_required(data, "school_year", where))
    two_years = country.school_year_starts != "01-01"
    pattern = r"^\d{4}/\d{2}$" if two_years else r"^\d{4}$"
    if not re.match(pattern, school_year) or (two_years and int(school_year[2:4]) + 1) % 100 != int(school_year[5:]):
        raise FormatError(f"{where}: school_year must look like {'2026/27' if two_years else '2026'}")
    if path.stem != school_year.replace("/", "-"):
        raise FormatError(f"{where}: file name must be {school_year.replace('/', '-')}.yaml")
    first, last = country._school_year_span(school_year)

    periods = []
    for applies_to, holidays in (data.get("periods") or {}).items():
        profiles = _matching_profiles(str(applies_to), country)
        if not profiles:
            raise FormatError(f"{where}: {applies_to} matches no profile")
        for holiday_id, value in (holidays or {}).items():
            if holiday_id not in country.school_holidays:
                raise FormatError(f"{where} {applies_to}: {holiday_id} is not listed under school_holidays in country.yaml")
            for part in value if isinstance(value, list) else [value]:
                start, end = _interval(part, f"{where} {applies_to} {holiday_id}")
                # Summer holidays belong to the school year they end, even where they start
                # in August (Bavaria). Nothing starts before the school year.
                if not first <= start <= last + timedelta(days=62):
                    raise FormatError(f"{where} {applies_to} {holiday_id}: {start} is outside school year {school_year}")
                periods.append(SchoolPeriod(school_year, holiday_id, str(applies_to), tuple(profiles), start, end, data.get("source")))
    return periods


def _interval(value, where: str) -> tuple[date, date]:
    if isinstance(value, str) and "/" in value:
        start, end = (_date(v, where) for v in value.split("/", 1))
        if start > end:
            raise FormatError(f"{where}: {value} ends before it starts")
        return start, end
    day = _date(value, where)
    return day, day


def _check_school_overlaps(country: Country) -> None:
    by_profile: dict[str, list[SchoolPeriod]] = {}
    for period in country.school_periods:
        for profile in period.profiles:
            by_profile.setdefault(profile, []).append(period)
    for profile, periods in by_profile.items():
        periods.sort(key=lambda p: p.start)
        for a, b in zip(periods, periods[1:]):
            if b.start <= a.end:
                raise FormatError(f"{country.code}: school holidays overlap for {profile}: "
                                  f"{a.holiday_id} {a.start}/{a.end} and {b.holiday_id} {b.start}/{b.end}")


def _regions(path: Path, country: Country) -> dict[str, Region]:
    where = f"{country.code}/regions.csv"
    regions: dict[str, Region] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = {"code", "name", "subdivision_code"} - set(reader.fieldnames or [])
        if missing:
            raise FormatError(f"{where}: columns missing: {', '.join(sorted(missing))}")
        for line, row in enumerate(reader, start=2):
            code, sub = row["code"], row["subdivision_code"]
            if not code or code in regions:
                raise FormatError(f"{where} line {line}: code is empty or used twice")
            if sub not in country.subdivisions:
                raise FormatError(f"{where} line {line}: unknown subdivision {sub}")
            for column in ("population", "latitude", "longitude"):
                if row.get(column):
                    try:
                        float(row[column])
                    except ValueError:
                        raise FormatError(f"{where} line {line}: {column} is not a number") from None
            regions[code] = Region(code, row["name"], sub, row)
    return regions


def _region_profiles(path: Path, country: Country) -> list[RegionProfile]:
    where = f"{country.code}/region-profiles.csv"
    result: list[RegionProfile] = []
    with path.open(newline="", encoding="utf-8") as f:
        for line, row in enumerate(csv.DictReader(f), start=2):
            here = f"{where} line {line}"
            region = country.regions.get(row["code"])
            profile = country.profiles.get(row["calendar_profile_id"])
            if region is None:
                raise FormatError(f"{here}: unknown region {row['code']}")
            if profile is None or profile.subdivision != region.subdivision:
                raise FormatError(f"{here}: {row['calendar_profile_id']} is not a profile of {region.subdivision}")
            valid_from, valid_until = _optional_date(row["valid_from"], here), _optional_date(row["valid_until"], here)
            if valid_from and valid_until and valid_from > valid_until:
                raise FormatError(f"{here}: valid_from is after valid_until")
            result.append(RegionProfile(row["code"], profile.id, valid_from, valid_until))

    result.sort(key=lambda r: (r.code, r.valid_from or date.min))
    for a, b in zip(result, result[1:]):
        if a.code == b.code and (a.valid_until is None or b.valid_from is None or b.valid_from <= a.valid_until):
            raise FormatError(f"{where}: periods overlap for region {a.code}")
    return result


def _expectations(path: Path, country: Country) -> list[dict]:
    where = f"{country.code}/expected.yaml"
    entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    for entry in entries:
        entry["date"] = _date(entry.get("date"), f"{where} {entry}")
        if ("profile" in entry) == ("region" in entry):
            raise FormatError(f"{where} {entry}: set exactly one of profile and region")
        if "profile" in entry and entry["profile"] not in country.profiles:
            raise FormatError(f"{where} {entry}: unknown profile")
        if "region" in entry:
            entry["region"] = str(entry["region"])
            if entry["region"] not in country.regions:
                raise FormatError(f"{where} {entry}: unknown region")
        if "holiday" not in entry and "school_holiday" not in entry:
            raise FormatError(f"{where} {entry}: set holiday or school_holiday")
    return entries


def _nth_weekday(year: int, month: int, weekday: int, nth: int) -> date:
    if nth == -1:
        last = date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)
        return last - timedelta(days=(last.weekday() - weekday) % 7)
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (nth - 1))


def _within(day: date, valid_from: date | None, valid_until: date | None) -> bool:
    return (valid_from is None or day >= valid_from) and (valid_until is None or day <= valid_until)


def _yaml(path: Path) -> dict:
    if not path.exists():
        raise FormatError(f"{path.parent.name}/{path.name} is missing")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _required(data: dict, key: str, where: str):
    if not isinstance(data, dict) or data.get(key) in (None, "", []):
        raise FormatError(f"{where}: {key} is missing")
    return data[key]


def _weekday(value, where: str) -> int:
    if value not in WEEKDAYS:
        raise FormatError(f"{where}: {value} is not a weekday ({', '.join(WEEKDAYS)})")
    return WEEKDAYS.index(value)


def _date(value, where: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise FormatError(f"{where}: {value} is not a valid date") from None


def _optional_date(value, where: str) -> date | None:
    return _date(value, where) if value not in (None, "") else None


def _check_month_day(value: str, where: str) -> None:
    if not MONTH_DAY.match(value):
        raise FormatError(f"{where}: {value} is not a valid date")
    _date(f"2000-{value}", where)  # 2000 is a leap year, so 02-29 passes
