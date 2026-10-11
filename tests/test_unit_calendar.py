"""Unit tests for bin/omarchy-thunderbird-calendar.

Thunderbird stores calendar times as microseconds since the epoch; getting that unit
wrong is the whole ballgame, so it is pinned here against a synthetic calendar
database built with the shipped schema's columns.
"""

import contextlib
import datetime
import importlib.machinery
import importlib.util
import io
import json
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = pathlib.Path(__file__).resolve().parent.parent
CAL = REPO / "bin/omarchy-thunderbird-calendar"


def load_module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    try:
        loader.exec_module(module)
    except SystemExit as exc:
        raise ImportError("%s exited at import (%r)" % (name, exc)) from exc
    return module


cal = load_module("tb_cal", CAL)


def make_db(path, events, recurrences=()):
    """Build a calendar store. Event rows are (id, cal_id, title, start, end, status)
    with an optional 7th element, the recurrence_id of a detached exception."""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE cal_events (id TEXT, cal_id TEXT, title TEXT, "
                 "event_start INTEGER, event_end INTEGER, ical_status TEXT, "
                 "recurrence_id INTEGER)")
    conn.execute("CREATE TABLE cal_recurrence (item_id TEXT, cal_id TEXT, icalString TEXT)")
    for row in events:
        row = tuple(row) + (None,) * (7 - len(row))
        conn.execute("INSERT INTO cal_events VALUES (?,?,?,?,?,?,?)", row)
    conn.executemany("INSERT INTO cal_recurrence VALUES (?,?,?)",
                     [(item, "cal", ical) for item, ical in recurrences])
    conn.commit()
    conn.close()


def usecs(dt):
    return int(dt.timestamp()) * 1_000_000


class UnitCase(unittest.TestCase):
    def test_the_storage_unit_is_microseconds(self):
        self.assertEqual(cal.USECS_PER_SECOND, 1000000)

    def test_microseconds_are_divided_by_a_million(self):
        self.assertEqual(cal.usecs_to_epoch(1_700_000_000_000_000), 1_700_000_000)
        self.assertEqual(cal.usecs_to_epoch(1_700_000_000_500_000), 1_700_000_000)

    def test_to_datetime_matches_fromtimestamp(self):
        dt = datetime.datetime(2030, 1, 1, 12, 0)
        self.assertEqual(cal.to_datetime(usecs(dt)), dt.replace(second=0, microsecond=0))


class LoadCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_loads_rows_from_a_calendar_db(self):
        db = self.dir / "local.sqlite"
        start = datetime.datetime.now() + datetime.timedelta(hours=2)
        make_db(db, [("1", "cal", "Standup", usecs(start), usecs(start + datetime.timedelta(hours=1)), "CONFIRMED")])
        with tempfile.TemporaryDirectory() as work:
            events = cal.load_events(db, pathlib.Path(work))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["title"], "Standup")

    def test_end_and_status_columns_are_preserved(self):
        db = self.dir / "local.sqlite"
        start = datetime.datetime.now() + datetime.timedelta(hours=2)
        make_db(db, [("1", "cal", "Review", usecs(start), usecs(start + datetime.timedelta(hours=1)), "CONFIRMED")])
        with tempfile.TemporaryDirectory() as work:
            event = cal.load_events(db, pathlib.Path(work))[0]
        self.assertEqual(event["status"], "CONFIRMED")
        self.assertEqual(event["end_usecs"] - event["start_usecs"], 3600 * 1000000)

    def test_a_non_calendar_sqlite_file_yields_no_events(self):
        db = self.dir / "other.sqlite"
        conn = sqlite3.connect(str(db)); conn.execute("CREATE TABLE t (x)"); conn.commit(); conn.close()
        with tempfile.TemporaryDirectory() as work:
            self.assertEqual(cal.load_events(db, pathlib.Path(work)), [])


class UpcomingCase(unittest.TestCase):
    def setUp(self):
        self.now = datetime.datetime(2030, 6, 1, 12, 0)

    def event(self, title, start, end, status="CONFIRMED"):
        return {"title": title, "start_usecs": usecs(start), "end_usecs": usecs(end),
                "status": status, "calendar": "cal", "id": title}

    def test_past_events_are_excluded(self):
        past = self.event("past", self.now - datetime.timedelta(days=2), self.now - datetime.timedelta(days=2))
        future = self.event("future", self.now + datetime.timedelta(hours=1), self.now + datetime.timedelta(hours=2))
        out = cal.upcoming([past, future], now=self.now, days=7)
        self.assertEqual([e["title"] for e in out], ["future"])

    def test_events_beyond_the_horizon_are_excluded(self):
        far = self.event("far", self.now + datetime.timedelta(days=30), self.now + datetime.timedelta(days=30))
        soon = self.event("soon", self.now + datetime.timedelta(hours=3), self.now + datetime.timedelta(hours=4))
        out = cal.upcoming([far, soon], now=self.now, days=7)
        self.assertEqual([e["title"] for e in out], ["soon"])

    def test_cancelled_events_are_skipped(self):
        c = self.event("cancelled", self.now + datetime.timedelta(hours=1), self.now + datetime.timedelta(hours=2), status="CANCELLED")
        out = cal.upcoming([c], now=self.now)
        self.assertEqual(out, [])

    def test_results_are_sorted_by_start(self):
        later = self.event("later", self.now + datetime.timedelta(hours=5), self.now + datetime.timedelta(hours=6))
        sooner = self.event("sooner", self.now + datetime.timedelta(hours=1), self.now + datetime.timedelta(hours=2))
        out = cal.upcoming([later, sooner], now=self.now)
        self.assertEqual([e["title"] for e in out], ["sooner", "later"])

    def test_an_ongoing_event_is_kept(self):
        ongoing = self.event("now", self.now - datetime.timedelta(hours=1), self.now + datetime.timedelta(hours=1))
        self.assertEqual(len(cal.upcoming([ongoing], now=self.now)), 1)

    def test_an_event_ending_exactly_now_is_kept(self):
        edge = self.event("edge", self.now - datetime.timedelta(hours=1), self.now)
        self.assertEqual([e["title"] for e in cal.upcoming([edge], now=self.now)], ["edge"])

    def test_an_event_starting_exactly_at_the_horizon_is_kept(self):
        horizon = self.now + datetime.timedelta(days=7)
        edge = self.event("edge", horizon, horizon + datetime.timedelta(hours=1))
        self.assertEqual([e["title"] for e in cal.upcoming([edge], now=self.now, days=7)], ["edge"])


class ResolveProfileCase(unittest.TestCase):
    def fake_run(self, returncode, stdout):
        return mock.patch.object(cal.subprocess, "run",
                                 lambda cmd, **kw: mock.Mock(returncode=returncode, stdout=stdout))

    def test_explicit_path_bypasses_the_finder(self):
        with mock.patch.object(cal.subprocess, "run") as run:
            self.assertEqual(cal.resolve_profile("/tmp/p"), pathlib.Path("/tmp/p"))
            run.assert_not_called()

    def test_finder_is_called_in_text_mode_with_captured_output(self):
        record = {}

        def run(cmd, **kwargs):
            record["kwargs"] = kwargs
            return mock.Mock(returncode=0, stdout="/var/tmp/tb/p\n")

        with mock.patch.object(cal.subprocess, "run", run):
            cal.resolve_profile(None)
        self.assertIs(record["kwargs"]["capture_output"], True)
        self.assertIs(record["kwargs"]["text"], True)

    def test_nonzero_returncode_yields_none(self):
        with self.fake_run(1, "/var/tmp/tb/p\n"):
            self.assertIsNone(cal.resolve_profile(None))

    def test_empty_stdout_yields_none(self):
        with self.fake_run(0, "  \n"):
            self.assertIsNone(cal.resolve_profile(None))


class RecurrenceCase(unittest.TestCase):
    def setUp(self):
        # A Monday, so weekday arithmetic is easy to reason about.
        self.monday = datetime.datetime(2030, 6, 3, 9, 0)

    def expand(self, rrule, horizon_days=30, start=None, **kw):
        start = start or self.monday
        return cal.expand_occurrences(start, cal.parse_rrule("RRULE:" + rrule),
                                      start + datetime.timedelta(days=horizon_days), **kw)

    def test_unfold_rejoins_continuation_lines(self):
        self.assertEqual(cal.unfold("RRULE:FREQ=WEEKLY;\r\n INTERVAL=2"), "RRULE:FREQ=WEEKLY;INTERVAL=2")

    def test_parse_rrule_finds_the_rule(self):
        rule = cal.parse_rrule("BEGIN:VEVENT\r\nDTSTART:20300603T090000\r\nRRULE:FREQ=WEEKLY;INTERVAL=2\r\nEND:VEVENT")
        self.assertEqual(rule, {"FREQ": "WEEKLY", "INTERVAL": "2"})

    def test_parse_rrule_returns_none_without_a_rule(self):
        self.assertIsNone(cal.parse_rrule("BEGIN:VEVENT\r\nEND:VEVENT"))

    def test_parse_until_accepts_both_forms(self):
        self.assertEqual(cal.parse_until("20300610T090000Z"), datetime.datetime(2030, 6, 10, 9, 0))
        self.assertEqual(cal.parse_until("20300610"), datetime.datetime(2030, 6, 10))

    def test_parse_until_rejects_garbage(self):
        self.assertIsNone(cal.parse_until("nonsense"))

    def test_daily(self):
        occ = self.expand("FREQ=DAILY", horizon_days=3)
        self.assertEqual([d.day for d in occ], [3, 4, 5, 6])

    def test_daily_with_interval(self):
        occ = self.expand("FREQ=DAILY;INTERVAL=2", horizon_days=4)
        self.assertEqual([d.day for d in occ], [3, 5, 7])

    def test_weekly_defaults_to_the_start_weekday(self):
        occ = self.expand("FREQ=WEEKLY", horizon_days=14)
        self.assertEqual([(d.month, d.day) for d in occ], [(6, 3), (6, 10), (6, 17)])

    def test_weekly_with_byday(self):
        occ = self.expand("FREQ=WEEKLY;BYDAY=MO,WE", horizon_days=7)
        self.assertEqual([(d.month, d.day) for d in occ], [(6, 3), (6, 5), (6, 10)])

    def test_weekly_with_interval_and_byday(self):
        occ = self.expand("FREQ=WEEKLY;INTERVAL=2;BYDAY=MO", horizon_days=21)
        self.assertEqual([(d.month, d.day) for d in occ], [(6, 3), (6, 17)])

    def test_monthly_keeps_the_day_of_month(self):
        occ = self.expand("FREQ=MONTHLY", horizon_days=70)
        self.assertEqual([(d.month, d.day) for d in occ], [(6, 3), (7, 3), (8, 3)])

    def test_monthly_with_bymonthday(self):
        occ = self.expand("FREQ=MONTHLY;BYMONTHDAY=15", horizon_days=50)
        self.assertEqual([(d.month, d.day) for d in occ], [(6, 15), (7, 15)])

    def test_monthly_occurrences_keep_the_time_of_day(self):
        occ = self.expand("FREQ=MONTHLY", horizon_days=1)
        self.assertEqual([d.hour for d in occ], [9])

    def test_monthly_skips_months_without_the_day(self):
        start = datetime.datetime(2030, 1, 31, 9, 0)
        occ = self.expand("FREQ=MONTHLY;BYMONTHDAY=31", horizon_days=120, start=start)
        self.assertEqual([(d.month, d.day) for d in occ], [(1, 31), (3, 31), (5, 31)])

    def test_yearly(self):
        occ = self.expand("FREQ=YEARLY", horizon_days=800)
        self.assertEqual([d.year for d in occ], [2030, 2031, 2032])

    def test_count_limits_the_total(self):
        occ = self.expand("FREQ=DAILY;COUNT=2", horizon_days=10)
        self.assertEqual(len(occ), 2)

    def test_until_limits_the_last_occurrence(self):
        occ = self.expand("FREQ=DAILY;UNTIL=20300605T090000Z", horizon_days=10)
        self.assertEqual([d.day for d in occ], [3, 4, 5])

    def test_an_unsupported_freq_produces_nothing(self):
        self.assertEqual(self.expand("FREQ=HOURLY"), [])

    def test_a_missing_rule_is_none_and_one_occurrence_is_returned(self):
        self.assertEqual(cal.expand_occurrences(self.monday, None, self.monday + datetime.timedelta(days=1)),
                         [self.monday])


class DetachedExceptionCase(unittest.TestCase):
    """A rescheduled single occurrence must move, not duplicate."""

    def setUp(self):
        # Master weekly series whose NEXT occurrence is two hours from now.
        self.next_occ = datetime.datetime.now() + datetime.timedelta(hours=2)
        self.master = self.next_occ - datetime.timedelta(days=7)

    def build(self, moved_hours=24):
        moved = self.next_occ + datetime.timedelta(hours=moved_hours)
        events = [
            ("r1", "cal", "Standup", usecs(self.master),
             usecs(self.master + datetime.timedelta(minutes=30)), "CONFIRMED"),
            # exception: same id, recurrence_id = original slot, own start = new time
            ("r1", "cal", "Standup (moved)", usecs(moved),
             usecs(moved + datetime.timedelta(minutes=30)), "CONFIRMED", usecs(self.next_occ)),
        ]
        return events, moved

    def test_the_moved_occurrence_replaces_the_original_slot(self):
        events, moved = self.build()
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "local.sqlite"
            make_db(db, events, recurrences=[("r1", "BEGIN:VEVENT\r\nRRULE:FREQ=WEEKLY\r\nEND:VEVENT")])
            with tempfile.TemporaryDirectory() as work:
                loaded = cal.load_events(db, pathlib.Path(work))
        occ = cal.upcoming(loaded, days=7)
        self.assertEqual(len(occ), 1, [o["title"] for o in occ])
        self.assertEqual(datetime.datetime.fromisoformat(occ[0]["start"]),
                         moved.replace(second=0, microsecond=0))

    def test_the_exception_is_not_expanded_as_its_own_series(self):
        # cal_recurrence is keyed by the shared id, so without the override guard the
        # exception row would inherit the master's weekly rule and fan out.
        events, _ = self.build()
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "local.sqlite"
            make_db(db, events, recurrences=[("r1", "BEGIN:VEVENT\r\nRRULE:FREQ=WEEKLY\r\nEND:VEVENT")])
            with tempfile.TemporaryDirectory() as work:
                loaded = cal.load_events(db, pathlib.Path(work))
        exception = [e for e in loaded if e.get("override_of")]
        self.assertEqual(len(exception), 1)
        self.assertIsNone(exception[0]["rule"])
        self.assertLessEqual(len(cal.upcoming(loaded, days=7)), 2)

    def test_a_lone_exception_without_a_master_still_shows(self):
        moved = datetime.datetime.now() + datetime.timedelta(hours=3)
        events = [("gone", "cal", "Orphan", usecs(moved),
                   usecs(moved + datetime.timedelta(minutes=30)), "CONFIRMED",
                   usecs(moved - datetime.timedelta(days=7)))]
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "local.sqlite"
            make_db(db, events)
            with tempfile.TemporaryDirectory() as work:
                loaded = cal.load_events(db, pathlib.Path(work))
        occ = cal.upcoming(loaded, days=7)
        self.assertEqual([o["title"] for o in occ], ["Orphan"])


class RecurrenceBoundaryCase(unittest.TestCase):
    def setUp(self):
        self.start = datetime.datetime(2030, 6, 3, 9, 0)  # a Monday

    def expand(self, rrule, horizon, limit=cal.MAX_OCCURRENCES):
        return cal.expand_occurrences(self.start, cal.parse_rrule("RRULE:" + rrule), horizon, limit)

    def test_the_limit_is_exactly_respected_for_weekly(self):
        horizon = self.start + datetime.timedelta(days=60)
        occ = self.expand("FREQ=WEEKLY;BYDAY=MO,WE", horizon, limit=3)
        self.assertEqual(len(occ), 3)
        self.assertEqual([(d.month, d.day) for d in occ], [(6, 3), (6, 5), (6, 10)])

    def test_the_limit_is_exactly_respected_for_daily(self):
        horizon = self.start + datetime.timedelta(days=30)
        occ = self.expand("FREQ=DAILY", horizon, limit=2)
        self.assertEqual([d.day for d in occ], [3, 4])

    def test_the_limit_is_exactly_respected_for_monthly(self):
        horizon = self.start + datetime.timedelta(days=200)
        occ = self.expand("FREQ=MONTHLY", horizon, limit=2)
        self.assertEqual([(d.month, d.day) for d in occ], [(6, 3), (7, 3)])

    def test_a_month_whose_first_day_is_the_horizon_is_still_considered(self):
        # Midnight start so an occurrence can land exactly on the horizon.
        start = datetime.datetime(2030, 6, 3, 0, 0)
        horizon = datetime.datetime(2030, 7, 1, 0, 0)
        occ = cal.expand_occurrences(start, cal.parse_rrule("RRULE:FREQ=MONTHLY;BYMONTHDAY=1"), horizon)
        self.assertEqual([(d.month, d.day) for d in occ], [(7, 1)])


class RecurringEventCase(unittest.TestCase):
    def test_a_weekly_meeting_shows_the_upcoming_occurrence_not_the_master(self):
        # Master is 10 weeks in the past; the next weekly occurrence is within a week.
        master = datetime.datetime.now() - datetime.timedelta(weeks=10)
        event = {"title": "Standup", "start_usecs": usecs(master),
                 "end_usecs": usecs(master + datetime.timedelta(minutes=30)),
                 "status": "CONFIRMED", "calendar": "cal", "id": "r1",
                 "rule": cal.parse_rrule("RRULE:FREQ=WEEKLY")}
        occ = cal.upcoming([event], days=7)
        self.assertGreaterEqual(len(occ), 1)
        self.assertGreaterEqual(datetime.datetime.fromisoformat(occ[0]["start"]),
                                datetime.datetime.now() - datetime.timedelta(minutes=1))

    def test_expansion_is_loaded_from_the_recurrence_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "local.sqlite"
            master = datetime.datetime.now() - datetime.timedelta(weeks=3)
            make_db(db,
                    [("r1", "cal", "Weekly", usecs(master), usecs(master + datetime.timedelta(hours=1)), "CONFIRMED")],
                    recurrences=[("r1", "BEGIN:VEVENT\r\nRRULE:FREQ=WEEKLY;BYDAY=%s\r\nEND:VEVENT" %
                                  ["MO", "TU", "WE", "TH", "FR", "SA", "SU"][master.weekday()])])
            with tempfile.TemporaryDirectory() as work:
                events = cal.load_events(db, pathlib.Path(work))
        self.assertIsNotNone(events[0]["rule"])
        self.assertEqual(events[0]["rule"]["FREQ"], "WEEKLY")
        self.assertTrue(cal.upcoming(events, days=7))

    def test_a_non_recurring_event_still_shows_once(self):
        start = datetime.datetime.now() + datetime.timedelta(hours=2)
        event = {"title": "One-off", "start_usecs": usecs(start),
                 "end_usecs": usecs(start + datetime.timedelta(hours=1)),
                 "status": "CONFIRMED", "calendar": "cal", "id": "x", "rule": None}
        self.assertEqual(len(cal.upcoming([event], days=7)), 1)


class CliCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        profile = self.root / "thunderbird" / "abc.default-release"
        (profile / "calendar-data").mkdir(parents=True)
        (self.root / "thunderbird" / "profiles.ini").write_text(
            "[Profile0]\nName=default\nPath=abc.default-release\nDefault=1\nIsRelative=1\n")
        start = datetime.datetime.now() + datetime.timedelta(hours=3)
        make_db(profile / "calendar-data" / "local.sqlite",
                [("1", "cal", "Dentist", usecs(start), usecs(start + datetime.timedelta(hours=1)), "CONFIRMED")])
        self.profile = profile

    def tearDown(self):
        self._tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run(["python3", str(CAL), "--profile", str(self.profile), *args],
                              capture_output=True, text=True)

    def test_count(self):
        self.assertEqual(self.run_cli("--count").stdout.strip(), "1")

    def test_json(self):
        data = json.loads(self.run_cli("--json").stdout)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["events"][0]["title"], "Dentist")

    def test_human_output_lists_the_title(self):
        self.assertIn("Dentist", self.run_cli().stdout)

    def test_a_profile_path_that_is_not_a_directory_exits_one(self):
        result = subprocess.run(
            ["python3", str(CAL), "--profile", str(self.profile / "nope")],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)

    def test_the_default_horizon_is_seven_days(self):
        # An event 7.5 days out is outside the default 7-day window.
        far = datetime.datetime.now() + datetime.timedelta(days=7, hours=12)
        make_db(self.profile / "calendar-data" / "far.sqlite",
                [("2", "cal", "Far", usecs(far), usecs(far + datetime.timedelta(hours=1)), "CONFIRMED")])
        self.assertEqual(self.run_cli("--count").stdout.strip(), "1")

    def test_a_weekly_recurring_event_is_expanded_through_the_cli(self):
        # Master three weeks in the past; the next weekly occurrence is still ahead.
        master = datetime.datetime.now() - datetime.timedelta(weeks=3)
        weekday = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"][master.weekday()]
        make_db(self.profile / "calendar-data" / "recur.sqlite",
                [("r1", "cal", "Standup", usecs(master), usecs(master + datetime.timedelta(minutes=30)), "CONFIRMED")],
                recurrences=[("r1", "BEGIN:VEVENT\r\nRRULE:FREQ=WEEKLY;BYDAY=%s\r\nEND:VEVENT" % weekday)])
        self.assertGreaterEqual(int(self.run_cli("--count").stdout.strip()), 1)


if __name__ == "__main__":
    unittest.main()
