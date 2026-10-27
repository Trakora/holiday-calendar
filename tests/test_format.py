"""The data format: date rules, checks that catch mistakes, and every country in rules/."""

import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from holiday_format import FormatError, easter_sunday, load_all, load_country, orthodox_easter_sunday  # noqa: E402

RULES = Path(__file__).parents[1] / "rules"


@pytest.mark.parametrize("country", load_all(RULES), ids=lambda c: c.code)
def test_expected_dates_hold(country):
    assert country.failed_expectations() == []


@pytest.mark.parametrize("year, western, orthodox", [
    (2024, date(2024, 3, 31), date(2024, 5, 5)),
    (2025, date(2025, 4, 20), date(2025, 4, 20)),
    (2026, date(2026, 4, 5), date(2026, 4, 12)),
    (2027, date(2027, 3, 28), date(2027, 5, 2)),
])
def test_easter(year, western, orthodox):
    assert easter_sunday(year) == western
    assert orthodox_easter_sunday(year) == orthodox


def make_country(tmp_path: Path, holidays: list[dict], **extra) -> Path:
    """A minimal country XX with two subdivisions and one extra profile."""
    folder = tmp_path / "XX"
    folder.mkdir()
    meta = {
        "country": "XX", "name": "Test", "name_local": "Test", "language": "en", "timezone": "UTC",
        "subdivisions": {"XX-A": {"name": "A", "name_local": "A"}, "XX-B": {"name": "B", "name_local": "B"}},
        "profiles": {"XX-A-1": {"name": "A, part 1", "name_local": "A, part 1"}},
        "school_holidays": {"summer": {"name": "Summer", "name_local": "Summer"}},
    }
    meta.update(extra.pop("meta", {}))
    (folder / "country.yaml").write_text(yaml.safe_dump(meta), encoding="utf-8")
    (folder / "public-holidays.yaml").write_text(yaml.safe_dump({"holidays": holidays}), encoding="utf-8")
    for name, content in extra.items():
        path = folder / name.replace("__", "/")
        path.parent.mkdir(exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return folder


def rule(**fields) -> dict:
    return {"id": "test-day", "name": "Test Day", "name_local": "Test Day", "date": "01-01", "in": ["XX"]} | fields


@pytest.mark.parametrize("when, year, expected", [
    ({"date": "12-25"}, 2026, [date(2026, 12, 25)]),
    ({"date": "02-29"}, 2027, []),
    ({"date": "2020-05-08"}, 2020, [date(2020, 5, 8)]),
    ({"date": "2020-05-08"}, 2021, []),
    ({"dates": ["2026-03-20", "2027-03-10"]}, 2027, [date(2027, 3, 10)]),
    ({"easter": -2}, 2026, [date(2026, 4, 3)]),
    ({"orthodox_easter": 1}, 2026, [date(2026, 4, 13)]),
    ({"date": {"weekday": "wednesday", "before": "11-23"}}, 2026, [date(2026, 11, 18)]),
    ({"date": {"weekday": "wednesday", "before": "11-23"}}, 2022, [date(2022, 11, 16)]),  # 23 November 2022 was a Wednesday
    ({"date": {"weekday": "thursday", "nth": 4, "month": 11}}, 2026, [date(2026, 11, 26)]),
    ({"date": {"weekday": "monday", "nth": -1, "month": 5}}, 2026, [date(2026, 5, 25)]),
])
def test_date_rules(tmp_path, when, year, expected):
    holiday = {k: v for k, v in rule().items() if k != "date"} | when
    [parsed] = load_country(make_country(tmp_path, [holiday])).rules
    assert parsed.dates_in(year) == expected


def test_a_code_matches_its_profiles(tmp_path):
    country = load_country(make_country(tmp_path, [rule(**{"in": ["XX-A"]})]))
    assert country.rules[0].profiles == ("XX-A", "XX-A-1")


@pytest.mark.parametrize("broken, message", [
    ({"date": "02-30"}, "not a valid date"),
    ({"in": ["XX-C"]}, "matches no profile"),
    ({"easter": 1}, "exactly one"),
    ({"id": "Test Day"}, "lowercase"),
    ({"level": "district"}, "level"),
    ({"name_local": ""}, "name_local is missing"),
])
def test_broken_rules_are_rejected(tmp_path, broken, message):
    with pytest.raises(FormatError, match=message):
        load_country(make_country(tmp_path, [rule(**broken)]))


def school_year(periods: str, year: str = "2026/27") -> str:
    return f"school_year: {year}\nperiods:\n{periods}"


def test_school_holidays(tmp_path):
    folder = make_country(tmp_path, [rule()], **{
        "school-holidays__2026-27.yaml": school_year("  XX-A:\n    summer: [2027-07-01/2027-08-10, 2027-08-20]\n"),
    })
    country = load_country(folder)
    assert country.school_holidays_on("XX-A-1", date(2027, 8, 1)) == ["summer"]
    assert country.school_holidays_on("XX-B", date(2027, 8, 1)) == []
    assert country.school_coverage("XX-A") == (date(2026, 8, 1), date(2027, 7, 31))
    assert country.school_coverage("XX-B") is None


@pytest.mark.parametrize("file, content, message", [
    ("2026-27.yaml", "  XX-A:\n    summer: 2027-08-10/2027-07-01\n", "ends before it starts"),
    ("2026-27.yaml", "  XX-A:\n    autumn: 2026-10-01\n", "not listed under school_holidays"),
    ("2026-27.yaml", "  XX-A:\n    summer: 2026-07-01\n", "outside school year"),
    ("2026-27.yaml", "  XX-A:\n    summer: [2027-07-01/2027-07-10, 2027-07-05]\n", "overlap"),
    ("2026.yaml", "  XX-A:\n    summer: 2027-07-01\n", "file name"),
])
def test_broken_school_holidays_are_rejected(tmp_path, file, content, message):
    folder = make_country(tmp_path, [rule()], **{f"school-holidays__{file}": school_year(content)})
    with pytest.raises(FormatError, match=message):
        load_country(folder)


REGIONS = "code,name,subdivision_code\n001,One,XX-A\n002,Two,XX-B\n"


def test_region_profiles(tmp_path):
    folder = make_country(tmp_path, [rule()], meta={"regions": {"type": "municipality"}}, **{
        "regions.csv": REGIONS,
        "region-profiles.csv": "code,calendar_profile_id,valid_from,valid_until\n001,XX-A-1,2020-01-01,\n",
    })
    country = load_country(folder)
    assert country.profile_of("001", date(2019, 12, 31)) == "XX-A"
    assert country.profile_of("001", date(2020, 1, 1)) == "XX-A-1"
    assert country.profile_of("002", date(2020, 1, 1)) == "XX-B"


@pytest.mark.parametrize("assignments, message", [
    ("002,XX-A-1,,\n", "not a profile of XX-B"),
    ("003,XX-A-1,,\n", "unknown region"),
    ("001,XX-A-1,,2020-12-31\n001,XX-A-1,2020-06-01,\n", "overlap"),
])
def test_broken_region_profiles_are_rejected(tmp_path, assignments, message):
    folder = make_country(tmp_path, [rule()], meta={"regions": {"type": "municipality"}}, **{
        "regions.csv": REGIONS,
        "region-profiles.csv": "code,calendar_profile_id,valid_from,valid_until\n" + assignments,
    })
    with pytest.raises(FormatError, match=message):
        load_country(folder)


def test_failed_expectation_is_reported(tmp_path):
    folder = make_country(tmp_path, [rule()], **{"expected.yaml": "- { date: 2026-01-02, profile: XX-B, holiday: test-day }\n"})
    assert load_country(folder).failed_expectations() == [
        "XX 2026-01-02 XX-B: expected holiday test-day, found none"
    ]
