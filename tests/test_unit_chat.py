"""Unit tests for bin/omarchy-thunderbird-chat.

Chat accounts are read from the profile's prefs.js. This pins the parsing and the
honest empty case (no accounts is a valid, common answer).
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
CHAT = REPO / "bin/omarchy-thunderbird-chat"

PREFS = (
    'user_pref("chat.prpls.prpl-irc.acc1.username", "bob");\n'
    'user_pref("chat.prpls.prpl-irc.acc1.server", "irc.libera.chat");\n'
    'user_pref("chat.prpls.prpl-matrix.acc9.username", "@bob:matrix.org");\n'
    'user_pref("mail.server.server1.hostname", "mail.example.com");\n'
)


def load_module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    try:
        loader.exec_module(module)
    except SystemExit as exc:
        raise ImportError("%s exited at import (%r)" % (name, exc)) from exc
    return module


chat = load_module("tb_chat", CHAT)


class ParseCase(unittest.TestCase):
    def test_groups_accounts_by_protocol(self):
        found = chat.accounts_from_prefs(PREFS)
        self.assertEqual(found["prpl-irc"], ["acc1"])
        self.assertEqual(found["prpl-matrix"], ["acc9"])

    def test_non_chat_prefs_are_ignored(self):
        self.assertNotIn("mail", chat.accounts_from_prefs(PREFS))

    def test_no_accounts(self):
        self.assertEqual(chat.accounts_from_prefs('user_pref("mail.x", 1);\n'), {})


class CliCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        profile = self.root / "thunderbird" / "abc.default-release"
        profile.mkdir(parents=True)
        (self.root / "thunderbird" / "profiles.ini").write_text(
            "[Profile0]\nName=default\nPath=abc.default-release\nDefault=1\nIsRelative=1\n")
        self.profile = profile

    def tearDown(self):
        self._tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run(["python3", str(CHAT), "--profile", str(self.profile), *args],
                              capture_output=True, text=True)

    def test_empty_profile_reports_no_accounts(self):
        (self.profile / "prefs.js").write_text('user_pref("mail.x", 1);\n')
        out = self.run_cli().stdout
        self.assertIn("No chat accounts", out)

    def test_json_lists_protocols(self):
        (self.profile / "prefs.js").write_text(PREFS)
        data = json.loads(self.run_cli("--json").stdout)
        self.assertEqual(data["accounts"], 2)
        self.assertIn("prpl-irc", data["protocols"])

    def test_a_profile_path_that_is_not_a_directory_exits_one(self):
        result = subprocess.run(
            ["python3", str(CHAT), "--profile", str(self.profile / "nope")],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)


class ResolveProfileCase(unittest.TestCase):
    def fake_run(self, returncode, stdout):
        return mock.patch.object(chat.subprocess, "run",
                                 lambda cmd, **kw: mock.Mock(returncode=returncode, stdout=stdout))

    def test_explicit_path_bypasses_the_finder(self):
        with mock.patch.object(chat.subprocess, "run") as run:
            self.assertEqual(chat.resolve_profile("/tmp/p"), pathlib.Path("/tmp/p"))
            run.assert_not_called()

    def test_finder_is_called_in_text_mode_with_captured_output(self):
        record = {}

        def run(cmd, **kwargs):
            record["kwargs"] = kwargs
            return mock.Mock(returncode=0, stdout="/var/tmp/tb/p\n")

        with mock.patch.object(chat.subprocess, "run", run):
            chat.resolve_profile(None)
        self.assertIs(record["kwargs"]["capture_output"], True)
        self.assertIs(record["kwargs"]["text"], True)

    def test_nonzero_returncode_yields_none(self):
        with self.fake_run(1, "/var/tmp/tb/p\n"):
            self.assertIsNone(chat.resolve_profile(None))

    def test_empty_stdout_yields_none(self):
        with self.fake_run(0, "  \n"):
            self.assertIsNone(chat.resolve_profile(None))


if __name__ == "__main__":
    unittest.main()
