"""Checks the rules in rules/ and shows what it produces.

    python tools/check.py                       check every country
    python tools/check.py DE                    check one country
    python tools/check.py DE 2027               public and school holidays in 2027, per profile
    python tools/check.py DE 2027 DE-HH         only for one profile

Exits with 1 if anything is wrong, so CI can run it on every pull request.
"""

import sys
from pathlib import Path

from holiday_format import FormatError, load_country

RULES = Path(__file__).resolve().parent.parent / "rules"


def main(args: list[str]) -> int:
    folders = [RULES / args[0]] if args else sorted(p for p in RULES.iterdir() if (p / "country.yaml").exists())
    failed = False
    for folder in folders:
        try:
            country = load_country(folder)
        except FormatError as error:
            print(f"✗ {error}")
            failed = True
            continue
        failures = country.failed_expectations()
        for failure in failures:
            print(f"✗ {failure}")
        failed |= bool(failures)
        if not failures:
            print(f"✓ {country.code}: {len(country.rules)} rules, {len(country.profiles)} profiles, "
                  f"{len(country.school_periods)} school holiday periods, {len(country.regions)} regions, "
                  f"{len(country.expectations)} expectations")
        if len(args) >= 2:
            show(country, int(args[1]), args[2] if len(args) > 2 else None)
    return 1 if failed else 0


def show(country, year: int, only: str | None) -> None:
    days: dict[str, list[str]] = {}
    for day, profile, rule in country.public_holidays(year, year):
        days.setdefault(profile, []).append(f"{day}  {rule.name_local}")
    for period in country.school_periods:
        if period.start.year <= year <= period.end.year:
            for profile in period.profiles:
                name = country.school_holidays[period.holiday_id][1]
                days.setdefault(profile, []).append(f"{period.start}  {name} to {period.end}")
    for profile in sorted(days):
        if only and profile != only:
            continue
        print(f"\n{profile}  {country.profiles[profile].name}")
        for line in sorted(days[profile]):
            print(f"  {line}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
