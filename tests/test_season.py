"""The end of a hiring season: internship counts fall at many companies at once, so `internships vanished` must not
fire for roles that simply close, and each company that does trip it gets its own line until it is dismissed.

No real record of a season's end exists (Simplify's file starts in March 2026), so this simulates ten weeks on the
student-role counts of the 93 companies with 5 or more on Oct 30 2026, with real closures as a guide (Goldman went
from 19 to 0 on Sep 4 2026). Treat the numbers as simulated until a real season ends in spring 2027."""
import random
import statistics

import pytest

from internwatch import alerts, liveness

from conftest import company

COUNTS = [658,235,211,172,151,135,105,101,99,98,89,77,73,71,62,50,49,44,42,39,38,36,34,32,30,29,28,28,27,26,25,24,23,22,21,21,21,20,20,20,19,18,17,16,16,15,15,15,15,14,14,13,13,13,13,13,13,12,12,11,11,11,11,11,10,9,9,8,8,8,8,8,8,7,7,7,6,6,6,6,6,6,5,5,5,5,5,5,5,5,5,5,5]
DAYS = 70


def closing_days(shape: str, n: int, rng: random.Random) -> list[int]:
    if shape == "gradual":
        return [rng.randrange(DAYS) for _ in range(n)]
    if shape == "batches":
        days = [rng.randrange(DAYS) for _ in range(rng.randint(2, 4))]
        return [rng.choice(days) for _ in range(n)]
    if shape == "one day each":
        return [rng.randrange(42)] * n
    return [10] * n  # every company on the same day


def alert_day(shape: str, n: int, rng: random.Random) -> int | None:
    """The day the real rule fires for one company, one poll a day."""
    closes = closing_days(shape, n, rng)
    left = [sum(1 for c in closes if c > day) for day in range(DAYS + 1)]
    for day in range(3, DAYS + 1):
        if liveness.vanished([left[day], left[day - 1], left[day - 2], left[day - 3]]) is not None:
            return day
    return None


def lines_by_week(shape: str, seeds: int = 60) -> list[float]:
    """The lines this rule adds to each daily email at weeks 2, 4, 6, 8 and 10, median over the seeds. Nothing leaves
    the list before roles return, so the last number is also what stays after the season."""
    runs = []
    for seed in range(seeds):
        rng = random.Random(seed)
        days = [d for d in (alert_day(shape, n, rng) for n in COUNTS) if d is not None]
        runs.append([sum(1 for d in days if d <= week * 7) for week in (2, 4, 6, 8, 10)])
    return [statistics.median(r[i] for r in runs) for i in range(5)]


def test_the_counts_are_the_93_companies():
    assert len(COUNTS) == 93 and min(COUNTS) >= 5


@pytest.mark.parametrize("shape,expected", [
    ("gradual", [0, 0, 0, 0, 5]),
    ("batches", [1, 6, 14, 30, 56]),
    ("one day each", [28, 60, 91, 91, 91]),
    ("same day", [93, 93, 93, 93, 93]),
])
def test_lines_in_each_daily_email_as_a_season_ends(shape, expected):
    got = lines_by_week(shape)
    assert got == pytest.approx(expected, abs=3)


def test_roles_closing_gradually_rarely_trip_the_rule():
    assert lines_by_week("gradual")[3] <= 1  # until the very last roles go, in the tenth week


def each_company_alerting(cfg, db):
    return [{"key": f"c{i}", "name": f"Company {i}", "kind": "internships vanished", "summary": f"student roles fell ({n} → 0)",
             "alert": {"id": f"live_alert:c{i}:students", "rule": "students", "need": n / 2}} for i, n in enumerate(COUNTS)]


def add_check(db, key, students):
    db.add_check(1, key, "2027-06-01T00:00:00Z", 0.1, "ok", None, None, 50, students, 0, 0, 1)


def test_each_company_gets_its_own_line_with_no_cap_and_no_roll_up(make_cfg, memdb):
    cfg = make_cfg([company(f"c{i}") for i in range(len(COUNTS))])
    alerts.record(memdb, each_company_alerting(cfg, memdb), [])
    open_alerts = alerts.for_email(memdb)[0]
    assert len(open_alerts) == 93 and len({a["company"] for a in open_alerts}) == 93


def test_lines_stay_after_the_season_and_clear_as_roles_return(make_cfg, memdb):
    cfg = make_cfg([company(f"c{i}") for i in range(len(COUNTS))])
    alerts.record(memdb, each_company_alerting(cfg, memdb), [])
    for i in range(len(COUNTS)):
        add_check(memdb, f"c{i}", 0)
    for _ in range(3):                       # the quiet months: nothing clears on its own
        alerts.sweep(cfg, memdb)
    assert len(alerts.for_email(memdb)[0]) == 93
    add_check(memdb, "c0", COUNTS[0] // 2 - 1)   # roles coming back, not yet at half: still listed
    add_check(memdb, "c1", COUNTS[1])        # back
    alerts.sweep(cfg, memdb)
    assert len(alerts.for_email(memdb)[0]) == 92
    add_check(memdb, "c0", COUNTS[0])
    alerts.sweep(cfg, memdb)
    open_alerts, resolved = alerts.for_email(memdb)
    assert len(open_alerts) == 91 and len(resolved) == 2


def test_one_command_clears_a_whole_season(make_cfg, memdb):
    make_cfg([company("c0")])
    alerts.record(memdb, each_company_alerting(None, memdb), [])
    assert len(alerts.dismiss(memdb, kind="internships vanished")) == 93
    assert alerts.for_email(memdb)[0] == []
