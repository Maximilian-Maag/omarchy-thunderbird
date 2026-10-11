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


def make_db(path, events):
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE cal_events (id TEXT, cal_id TEXT, title TEXT, "
                 "event_start INTEGER, event_end INTEGER, ical_status TEXT)")
    conn.executemany("INSERT INTO cal_events VALUES (?,?,?,?,?,?)", events)
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


if __name__ == "__main__":
    unittest.main()
