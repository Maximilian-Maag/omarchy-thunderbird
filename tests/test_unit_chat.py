"""Unit tests for bin/omarchy-thunderbird-chat.

Chat accounts live under the ``messenger.account.<key>.*`` namespace (options one level
deeper, under ``options.``). The earlier assumption of a
``chat.prpls.<protocol>.<account>.<field>`` shape was wrong — this pins the real one and
the honest empty case.
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
    'user_pref("messenger.account.libera.name", "Libera");\n'
    'user_pref("messenger.account.libera.prpl", "prpl-irc");\n'
    'user_pref("messenger.account.libera.options.username", "bob@irc.libera.chat");\n'
    'user_pref("messenger.account.libera.autoLogin", false);\n'
    'user_pref("messenger.account.matrix1.prpl", "prpl-matrix");\n'
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
    def test_unquote_keeps_an_unquoted_short_value(self):
        self.assertEqual(chat._unquote("ab"), "ab")

    def test_unquote_of_an_empty_quoted_string(self):
        self.assertEqual(chat._unquote('""'), "")

    def test_unquote_strips_quotes(self):
        self.assertEqual(chat._unquote('"hi there"'), "hi there")

    def test_unquote_handles_escapes(self):
        self.assertEqual(chat._unquote('"a\\"b"'), 'a"b')

    def test_groups_fields_by_account_key(self):
        found = chat.accounts_from_prefs(PREFS)
        self.assertEqual(found["libera"]["name"], "Libera")
        self.assertEqual(found["libera"]["prpl"], "prpl-irc")
        self.assertEqual(found["libera"]["options.username"], "bob@irc.libera.chat")

    def test_boolean_values_are_kept_unquoted(self):
        self.assertEqual(chat.accounts_from_prefs(PREFS)["libera"]["autoLogin"], "false")

    def test_non_chat_prefs_are_ignored(self):
        keys = chat.accounts_from_prefs(PREFS)
        self.assertNotIn("mail", keys)
        self.assertEqual(sorted(keys), ["libera", "matrix1"])

    def test_no_accounts(self):
        self.assertEqual(chat.accounts_from_prefs('user_pref("mail.x", 1);\n'), {})

    def test_group_by_protocol(self):
        grouped = chat.group_by_protocol(chat.accounts_from_prefs(PREFS))
        self.assertEqual(grouped["prpl-irc"], ["libera"])
        self.assertEqual(grouped["prpl-matrix"], ["matrix1"])

    def test_an_account_without_a_protocol_is_not_reported_as_one(self):
        grouped = chat.group_by_protocol({"broken": {"name": "x"}})
        self.assertEqual(grouped, {})


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
        self.assertIn("No chat accounts", self.run_cli().stdout)

    def test_json_lists_protocols_and_names(self):
        (self.profile / "prefs.js").write_text(PREFS)
        data = json.loads(self.run_cli("--json").stdout)
        self.assertEqual(data["accounts"], 2)
        self.assertIn("prpl-irc", data["protocols"])
        self.assertEqual(data["names"]["libera"], "Libera")

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

    def test_finder_result_is_parsed(self):
        with self.fake_run(0, "/var/tmp/tb/p\n"):
            self.assertEqual(chat.resolve_profile(None), pathlib.Path("/var/tmp/tb/p"))

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
