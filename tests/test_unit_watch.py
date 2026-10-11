"""Unit tests for bin/omarchy-thunderbird-watch (the widget push daemon).

The interesting logic is what counts as a mail change and what command to run, both of
which are pure and pinned here.
"""

import importlib.machinery
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = pathlib.Path(__file__).resolve().parent.parent
WATCH = REPO / "bin/omarchy-thunderbird-watch"


def load_module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    try:
        loader.exec_module(module)
    except SystemExit as exc:
        raise ImportError("%s exited at import (%r)" % (name, exc)) from exc
    return module


watch = load_module("tb_watch", WATCH)


class MailDirsCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.profile = pathlib.Path(self._tmp.name) / "abc.default-release"
        self.profile.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_stores_yields_nothing(self):
        self.assertEqual(watch.mail_dirs(self.profile), [])

    def test_existing_stores_are_found(self):
        (self.profile / "Mail").mkdir()
        (self.profile / "ImapMail").mkdir()
        self.assertEqual([d.name for d in watch.mail_dirs(self.profile)], ["Mail", "ImapMail"])


class IsInterestingCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.mail = self.root / "Mail" / "Local Folders"
        self.mail.mkdir(parents=True)
        self.dirs = [self.root / "Mail"]

    def tearDown(self):
        self._tmp.cleanup()

    def test_an_mbox_file_is_interesting(self):
        self.assertTrue(watch.is_interesting(self.mail / "Inbox", self.dirs))

    def test_a_nested_message_file_is_interesting(self):
        self.assertTrue(watch.is_interesting(self.mail / "sub" / "Inbox", self.dirs))

    def test_a_file_outside_the_stores_is_not(self):
        self.assertFalse(watch.is_interesting(self.root / "prefs.js", self.dirs))

    def test_a_lock_file_is_not(self):
        self.assertFalse(watch.is_interesting(self.mail / ".parentlock", self.dirs))
        self.assertFalse(watch.is_interesting(self.mail / "Inbox.lock", self.dirs))

    def test_a_dotfile_is_not(self):
        self.assertFalse(watch.is_interesting(self.mail / ".hidden", self.dirs))

    def test_a_temporary_file_is_not(self):
        self.assertFalse(watch.is_interesting(self.mail / "Inbox.tmp", self.dirs))


class CommandCase(unittest.TestCase):
    def test_the_ipc_call_matches_the_widget_handler(self):
        self.assertEqual(watch.refresh_command(),
                         ["qs", "ipc", "call", "Maximilian-Maag.thunderbird", "refresh"])

    def test_the_target_can_be_overridden(self):
        self.assertEqual(watch.refresh_command("other.widget")[-2], "other.widget")

    def test_fingerprint_of_an_empty_store_is_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            mail = pathlib.Path(tmp) / "Mail"
            mail.mkdir()
            self.assertEqual(watch.fingerprint([mail]), (0, 0.0))

    def test_fingerprint_tracks_new_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            mail = pathlib.Path(tmp) / "Mail"
            mail.mkdir()
            dirs = [mail]
            before = watch.fingerprint(dirs)
            (mail / "Inbox").write_text("From x\n")
            self.assertNotEqual(watch.fingerprint(dirs), before)

    def test_fingerprint_ignores_uninteresting_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            mail = pathlib.Path(tmp) / "Mail"
            mail.mkdir()
            (mail / ".parentlock").write_text("x")
            self.assertEqual(watch.fingerprint([mail]), (0, 0.0))


class RefreshCase(unittest.TestCase):
    def test_refresh_calls_the_ipc_command_and_reports_success(self):
        record = {}

        def run(command, **kwargs):
            record["command"] = command
            record["kwargs"] = kwargs
            return mock.Mock(returncode=0)

        with mock.patch.object(watch.subprocess, "run", run):
            self.assertIs(watch.refresh("w.target"), True)
        self.assertEqual(record["command"], ["qs", "ipc", "call", "w.target", "refresh"])
        self.assertIs(record["kwargs"]["capture_output"], True)
        self.assertEqual(record["kwargs"]["timeout"], 10)

    def test_refresh_reports_failure_when_the_call_blows_up(self):
        with mock.patch.object(watch.subprocess, "run", side_effect=OSError("no qs")):
            self.assertIs(watch.refresh(), False)


class DebounceCase(unittest.TestCase):
    def test_it_fires_once_the_interval_has_elapsed(self):
        self.assertIs(watch.should_fire(10.0, 9.0, 1.0), True)

    def test_it_fires_at_exactly_the_interval(self):
        self.assertIs(watch.should_fire(10.0, 9.5, 0.5), True)

    def test_it_does_not_fire_before_the_interval(self):
        self.assertIs(watch.should_fire(10.0, 9.8, 0.5), False)


class WatchPollCase(unittest.TestCase):
    def test_it_refreshes_only_when_the_fingerprint_changes(self):
        sequence = [(1, 1.0), (2, 2.0), (2, 2.0), (2, 2.0)]
        calls = {"refresh": 0, "sleep": 0}

        def sleep(_interval):
            calls["sleep"] += 1
            if calls["sleep"] > 3:
                raise KeyboardInterrupt  # end the (otherwise infinite) loop

        def fingerprint(_dirs):
            return sequence[min(calls["sleep"], len(sequence) - 1)]

        with mock.patch.object(watch, "fingerprint", fingerprint), \
             mock.patch.object(watch.time, "sleep", sleep), \
             mock.patch.object(watch, "refresh", lambda target: calls.__setitem__("refresh", calls["refresh"] + 1)):
            with self.assertRaises(KeyboardInterrupt):
                watch.watch_poll([], "t", 1)
        # initial read is the baseline; one change fires, the repeats do not
        self.assertEqual(calls["refresh"], 1)


class CliCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.profile = self.root / "thunderbird" / "abc.default-release"
        (self.profile / "Mail" / "Local Folders").mkdir(parents=True)
        (self.root / "thunderbird" / "profiles.ini").write_text(
            "[Profile0]\nName=default\nPath=abc.default-release\nDefault=1\nIsRelative=1\n")

    def tearDown(self):
        self._tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run(["python3", str(WATCH), "--profile", str(self.profile), *args],
                              capture_output=True, text=True)

    def test_once_reports_the_targets_and_command(self):
        data = json.loads(self.run_cli("--once").stdout)
        self.assertEqual(data["command"], ["qs", "ipc", "call",
                                           "Maximilian-Maag.thunderbird", "refresh"])
        self.assertTrue(data["watch"][0].endswith("Mail"))

    def test_an_empty_profile_exits_one(self):
        empty = self.root / "empty"
        empty.mkdir()
        result = subprocess.run(["python3", str(WATCH), "--once", "--profile", str(empty)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)

    def test_a_path_that_is_not_a_directory_exits_one(self):
        result = subprocess.run(
            ["python3", str(WATCH), "--once", "--profile", str(self.profile / "nope")],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)


class ResolveProfileCase(unittest.TestCase):
    def fake_run(self, returncode, stdout):
        return mock.patch.object(watch.subprocess, "run",
                                 lambda cmd, **kw: mock.Mock(returncode=returncode, stdout=stdout))

    def test_explicit_path_bypasses_the_finder(self):
        with mock.patch.object(watch.subprocess, "run") as run:
            self.assertEqual(watch.resolve_profile("/tmp/p"), pathlib.Path("/tmp/p"))
            run.assert_not_called()

    def test_finder_is_called_in_text_mode_with_captured_output(self):
        record = {}

        def run(cmd, **kwargs):
            record["kwargs"] = kwargs
            return mock.Mock(returncode=0, stdout="/var/tmp/tb/p\n")

        with mock.patch.object(watch.subprocess, "run", run):
            watch.resolve_profile(None)
        self.assertIs(record["kwargs"]["capture_output"], True)
        self.assertIs(record["kwargs"]["text"], True)

    def test_nonzero_returncode_yields_none(self):
        with self.fake_run(1, "/var/tmp/tb/p\n"):
            self.assertIsNone(watch.resolve_profile(None))

    def test_empty_stdout_yields_none(self):
        with self.fake_run(0, "  \n"):
            self.assertIsNone(watch.resolve_profile(None))


if __name__ == "__main__":
    unittest.main()
