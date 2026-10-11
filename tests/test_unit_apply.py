"""Unit tests for bin/omarchy-thunderbird-apply and the shipped config/ files.

The applier turns config/*.json into the profile's user.js (settings/tags) and prefs.js
(chat accounts, which must be registered with Thunderbird's account manager rather than
pinned in user.js). Its parsing, validation and merge logic are pinned here, and the
*shipped* config is checked too: every tag is well-formed and every configured pref
actually differs from Thunderbird's built-in default (a pref equal to the default is
dropped from prefs.js and does nothing).
"""

import importlib.machinery
import importlib.util
import json
import pathlib
import re
import tempfile
import unittest
import zipfile
from unittest import mock

REPO = pathlib.Path(__file__).resolve().parent.parent
APPLY_PATH = REPO / "bin/omarchy-thunderbird-apply"
CONFIG = REPO / "config"
PREF = re.compile(r'user_pref\(\s*"([^"]+)"\s*,\s*(.*?)\s*\)')
OMNI = pathlib.Path("/usr/lib/thunderbird/omni.ja")


def load_module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    try:
        loader.exec_module(module)
    except SystemExit as exc:
        raise ImportError("%s exited at import (%r)" % (name, exc)) from exc
    return module


apply = load_module("tb_apply", APPLY_PATH)


def tb_defaults():
    if not OMNI.is_file():
        return None
    defaults = {}
    patch = re.compile(r'pref\(\s*"([^"]+)"\s*,\s*([^;\n]*?)\s*\)')
    with zipfile.ZipFile(OMNI) as archive:
        for name in archive.namelist():
            if not name.endswith((".js", ".mjs")):
                continue
            body = archive.read(name).decode("utf-8", "replace")
            for key, raw in patch.findall(body):
                defaults.setdefault(key, raw.strip())
    return defaults


class TagsCase(unittest.TestCase):
    def test_shipped_tags_are_valid(self):
        tags = apply.load_tags(CONFIG / "tags.json")
        self.assertGreaterEqual(len(tags), 5)
        for tag in tags:
            self.assertRegex(tag["key"], r"^[A-Za-z0-9_-]+$")
            self.assertRegex(tag["color"], r"^#[0-9A-Fa-f]{6}$")
            self.assertTrue(tag["name"].strip())

    def test_tags_to_prefs_emits_name_and_colour(self):
        prefs = apply.tags_to_prefs([{"key": "x", "name": "X", "color": "#112233"}])
        self.assertEqual(prefs["mailnews.tags.x.tag"], "X")
        self.assertEqual(prefs["mailnews.tags.x.color"], "#112233")

    def test_bad_tag_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = pathlib.Path(tmp) / "tags.json"
            f.write_text(json.dumps({"tags": [{"key": "bad key!", "name": "x", "color": "#000000"}]}))
            with self.assertRaises(ValueError):
                apply.load_tags(f)

    def test_bad_colour_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = pathlib.Path(tmp) / "tags.json"
            f.write_text(json.dumps({"tags": [{"key": "x", "name": "x", "color": "red"}]}))
            with self.assertRaises(ValueError):
                apply.load_tags(f)

    def test_duplicate_tag_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = pathlib.Path(tmp) / "tags.json"
            dup = {"key": "x", "name": "x", "color": "#000000"}
            f.write_text(json.dumps({"tags": [dup, dup]}))
            with self.assertRaises(ValueError):
                apply.load_tags(f)

    def test_an_empty_tag_list_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = pathlib.Path(tmp) / "tags.json"
            f.write_text(json.dumps({"tags": []}))
            with self.assertRaises(ValueError):
                apply.load_tags(f)

    def test_a_non_list_tags_value_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = pathlib.Path(tmp) / "tags.json"
            f.write_text(json.dumps({"tags": {"key": "x"}}))
            with self.assertRaises(ValueError):
                apply.load_tags(f)


class ResolveProfileCase(unittest.TestCase):
    def fake_run(self, returncode, stdout):
        return mock.patch.object(apply.subprocess, "run",
                                 lambda cmd, **kw: mock.Mock(returncode=returncode, stdout=stdout))

    def test_explicit_path_bypasses_the_finder(self):
        with mock.patch.object(apply.subprocess, "run") as run:
            self.assertEqual(apply.resolve_profile("/tmp/p"), pathlib.Path("/tmp/p"))
            run.assert_not_called()

    def test_finder_result_is_parsed(self):
        with self.fake_run(0, "/var/tmp/tb/abc\n"):
            self.assertEqual(apply.resolve_profile(None), pathlib.Path("/var/tmp/tb/abc"))

    def test_finder_is_called_in_text_mode_with_captured_output(self):
        record = {}

        def run(cmd, **kwargs):
            record["kwargs"] = kwargs
            return mock.Mock(returncode=0, stdout="/var/tmp/tb/abc\n")

        with mock.patch.object(apply.subprocess, "run", run):
            apply.resolve_profile(None)
        self.assertIs(record["kwargs"]["capture_output"], True)
        self.assertIs(record["kwargs"]["text"], True)

    def test_nonzero_returncode_yields_none(self):
        with self.fake_run(1, "/var/tmp/tb/abc\n"):
            self.assertIsNone(apply.resolve_profile(None))

    def test_empty_stdout_yields_none(self):
        with self.fake_run(0, "   \n"):
            self.assertIsNone(apply.resolve_profile(None))


class ChatAccountsCase(unittest.TestCase):
    def write(self, tmp, payload):
        path = pathlib.Path(tmp) / "chat.json"
        path.write_text(json.dumps(payload))
        return path

    def test_a_missing_file_means_no_accounts(self):
        self.assertEqual(apply.load_chat_accounts(pathlib.Path("/nonexistent/chat.json")), [])

    def test_shipped_chat_json_is_valid(self):
        accounts = apply.load_chat_accounts(REPO / "config" / "chat.json")
        self.assertEqual(accounts, [])  # shipped empty: nothing is written until opted in

    def test_a_valid_account_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, {"accounts": [
                {"id": 1, "name": "Libera", "protocol": "prpl-irc",
                 "username": "bob@irc.libera.chat", "autoLogin": True, "autoJoin": "#x"}]})
            self.assertEqual(len(apply.load_chat_accounts(path)), 1)

    def test_a_non_integer_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, {"accounts": [{"id": "libera", "name": "x", "protocol": "prpl-irc"}]})
            with self.assertRaises(ValueError):
                apply.load_chat_accounts(path)

    def test_a_boolean_id_is_rejected(self):
        # bool is an int subclass; it must still be refused.
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, {"accounts": [{"id": True, "name": "x", "protocol": "prpl-irc"}]})
            with self.assertRaises(ValueError):
                apply.load_chat_accounts(path)

    def test_a_zero_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, {"accounts": [{"id": 0, "name": "x", "protocol": "prpl-irc"}]})
            with self.assertRaises(ValueError):
                apply.load_chat_accounts(path)

    def test_a_duplicate_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            acct = {"id": 2, "name": "x", "protocol": "prpl-irc"}
            path = self.write(tmp, {"accounts": [acct, dict(acct)]})
            with self.assertRaises(ValueError):
                apply.load_chat_accounts(path)

    def test_a_missing_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, {"accounts": [{"id": 1, "name": " ", "protocol": "prpl-irc"}]})
            with self.assertRaises(ValueError):
                apply.load_chat_accounts(path)

    def test_a_protocol_that_is_not_prpl_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, {"accounts": [{"id": 1, "name": "x", "protocol": "irc"}]})
            with self.assertRaises(ValueError):
                apply.load_chat_accounts(path)

    def test_a_non_boolean_autoLogin_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, {"accounts": [{"id": 1, "name": "x", "protocol": "prpl-irc", "autoLogin": "yes"}]})
            with self.assertRaises(ValueError):
                apply.load_chat_accounts(path)


class AccountManagerPrefsCase(unittest.TestCase):
    def acct(self, **kw):
        base = {"id": 1, "name": "Libera", "protocol": "prpl-irc"}
        base.update(kw)
        return base

    def test_registers_the_account_with_the_manager(self):
        prefs = apply.account_manager_prefs({}, [self.acct(
            username="bob@irc.libera.chat", autoLogin=True, autoJoin="#a,#b")])
        self.assertEqual(prefs["mail.accountmanager.accounts"], "account1")
        self.assertEqual(prefs["mail.account.account1.server"], "server1")
        self.assertEqual(prefs["mail.server.server1.type"], "im")
        self.assertEqual(prefs["mail.server.server1.hostname"], "prpl-irc")
        self.assertEqual(prefs["mail.server.server1.userName"], "Libera")
        self.assertEqual(prefs["mail.server.server1.imAccount"], "account1")
        self.assertEqual(prefs["messenger.account.account1.name"], "Libera")
        self.assertEqual(prefs["messenger.account.account1.prpl"], "prpl-irc")
        self.assertIs(prefs["messenger.account.account1.autoLogin"], True)
        self.assertEqual(prefs["messenger.account.account1.autoJoin"], "#a,#b")
        self.assertEqual(prefs["messenger.account.account1.options.username"], "bob@irc.libera.chat")

    def test_existing_accounts_and_server_numbers_are_preserved(self):
        existing = {"mail.accountmanager.accounts": '"account1,account2"',
                    "mail.account.account1.server": '"server2"',
                    "mail.server.server2.type": '"imap"'}
        prefs = apply.account_manager_prefs(existing, [self.acct(id=3)])
        self.assertEqual(prefs["mail.accountmanager.accounts"], "account1,account2,account3")
        self.assertEqual(prefs["mail.account.account3.server"], "server1")  # server1 free, server2 taken

    def test_an_existing_chat_account_reuses_its_server(self):
        existing = {"mail.accountmanager.accounts": '"account1"',
                    "mail.account.account1.server": '"server5"',
                    "mail.server.server5.type": '"im"'}
        prefs = apply.account_manager_prefs(existing, [self.acct(id=1)])
        self.assertNotIn("mail.account.account1.server", prefs)  # reused, not rewritten
        self.assertEqual(prefs["mail.server.server5.imAccount"], "account1")
        self.assertEqual(prefs["mail.accountmanager.accounts"], "account1")

    def test_an_id_clashing_with_a_real_account_is_refused(self):
        existing = {"mail.accountmanager.accounts": '"account1"',
                    "mail.account.account1.server": '"server1"',
                    "mail.server.server1.type": '"imap"'}
        with self.assertRaises(ValueError):
            apply.account_manager_prefs(existing, [self.acct(id=1)])

    def test_no_accounts_means_no_updates(self):
        self.assertEqual(apply.account_manager_prefs({}, []), {})

    def test_optional_fields_are_omitted_when_absent(self):
        prefs = apply.account_manager_prefs({}, [self.acct()])
        self.assertIs(prefs["messenger.account.account1.autoLogin"], False)
        self.assertNotIn("messenger.account.account1.autoJoin", prefs)
        self.assertNotIn("messenger.account.account1.options.username", prefs)

    def test_unquote_handles_quoted_bare_and_escapes(self):
        self.assertEqual(apply._unquote('"hi"'), "hi")
        self.assertEqual(apply._unquote("bare"), "bare")
        self.assertEqual(apply._unquote('"a\\"b"'), 'a"b')
        self.assertEqual(apply._unquote('"a\\\\b"'), "a\\b")

    def test_next_free_server_skips_used_numbers(self):
        self.assertEqual(apply._next_free_server(set()), "server1")
        self.assertEqual(apply._next_free_server({"server1", "server2"}), "server3")


class PrefsFileCase(unittest.TestCase):
    def test_read_prefs_captures_keys_and_raw_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "prefs.js"
            p.write_text('// c\nuser_pref("a.b", "x");\nuser_pref("n", 3);\n')
            self.assertEqual(apply.read_prefs(p), {"a.b": '"x"', "n": "3"})

    def test_read_prefs_of_a_missing_file_is_empty(self):
        self.assertEqual(apply.read_prefs(pathlib.Path("/nonexistent/prefs.js")), {})

    def test_upsert_replaces_existing_and_appends_new(self):
        out = apply.upsert_pref_lines('// keep\nuser_pref("a", 1);\n', {"a": 2, "b": "z"})
        self.assertIn("// keep", out)
        self.assertIn('user_pref("a", 2);', out)
        self.assertIn('user_pref("b", "z");', out)
        self.assertNotIn('user_pref("a", 1);', out)

    def test_upsert_is_idempotent(self):
        once = apply.upsert_pref_lines('user_pref("a", 1);\n', {"a": 1})
        self.assertEqual(once, apply.upsert_pref_lines(once, {"a": 1}))

    def test_upsert_leaves_unmanaged_lines_alone(self):
        out = apply.upsert_pref_lines('user_pref("keep.me", "yes");\n', {"new.key": 1})
        self.assertIn('user_pref("keep.me", "yes");', out)
        self.assertIn('user_pref("new.key", 1);', out)


class ProvisionCase(unittest.TestCase):
    def test_provision_writes_the_registration_to_prefs_js(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = pathlib.Path(tmp)
            (profile / "prefs.js").write_text('user_pref("mail.accountmanager.accounts", "");\n')
            n = apply.provision_accounts(profile, [{"id": 1, "name": "Libera", "protocol": "prpl-irc"}])
            self.assertEqual(n, 1)
            text = (profile / "prefs.js").read_text()
            self.assertIn('user_pref("mail.server.server1.type", "im");', text)
            self.assertIn('user_pref("mail.accountmanager.accounts", "account1");', text)
            # never user.js
            self.assertFalse((profile / "user.js").exists())

    def test_provision_with_no_accounts_is_a_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = pathlib.Path(tmp)
            self.assertEqual(apply.provision_accounts(profile, []), 0)
            self.assertFalse((profile / "prefs.js").exists())

    def test_provision_refuses_while_thunderbird_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = pathlib.Path(tmp)
            (profile / "prefs.js").write_text("")
            with mock.patch.object(apply, "thunderbird_running", lambda: True):
                with self.assertRaises(apply.ThunderbirdRunning):
                    apply.provision_accounts(profile, [{"id": 1, "name": "x", "protocol": "prpl-irc"}])

    def test_thunderbird_running_handles_a_missing_pgrep(self):
        with mock.patch.object(apply.subprocess, "run", side_effect=OSError):
            self.assertFalse(apply.thunderbird_running())

    def test_thunderbird_running_reads_the_returncode(self):
        with mock.patch.object(apply.subprocess, "run", lambda cmd, **kw: mock.Mock(returncode=0)):
            self.assertTrue(apply.thunderbird_running())
        with mock.patch.object(apply.subprocess, "run", lambda cmd, **kw: mock.Mock(returncode=1)):
            self.assertFalse(apply.thunderbird_running())

    def test_thunderbird_running_captures_output(self):
        record = {}

        def run(cmd, **kw):
            record.update(kw)
            return mock.Mock(returncode=1)

        with mock.patch.object(apply.subprocess, "run", run):
            apply.thunderbird_running()
        self.assertIs(record["capture_output"], True)


class LiteralCase(unittest.TestCase):
    def test_booleans_numbers_and_strings(self):
        self.assertEqual(apply.literal(True), "true")
        self.assertEqual(apply.literal(False), "false")
        self.assertEqual(apply.literal(2), "2")
        self.assertEqual(apply.literal("hi"), '"hi"')

    def test_quotes_are_escaped(self):
        self.assertEqual(apply.literal('a"b'), '"a\\"b"')


class BuildCase(unittest.TestCase):
    BASE = 'user_pref("base.one", true);\nuser_pref("base.two", 1);\n'

    def prefs(self, text):
        return {k: v for k, v in PREF.findall(text)}

    def test_config_overrides_base_and_comes_last(self):
        out = apply.build_userjs(self.BASE, {"base.one": False})
        self.assertTrue(out.rindex("base.one") > out.index("base.two"))
        self.assertEqual(self.prefs(out)["base.one"], "false")
        self.assertEqual(out.count('user_pref("base.one"'), 1)

    def test_foreign_prefs_are_preserved(self):
        existing = self.BASE + 'user_pref("mine.keep", 5);\n'
        out = apply.build_userjs(self.BASE, {"new.pref": 1}, existing)
        self.assertIn('user_pref("mine.keep", 5);', out)

    def test_managed_keys_are_not_duplicated(self):
        existing = self.BASE + 'user_pref("base.one", false);\n'
        out = apply.build_userjs(self.BASE, {"new.pref": 1}, existing)
        self.assertEqual(out.count('user_pref("base.one"'), 1)

    def test_output_parses_and_ends_with_newline(self):
        out = apply.build_userjs(self.BASE, {"a.b": 1, "c.d": "s"})
        self.assertTrue(out.endswith("\n"))
        self.assertIn('user_pref("c.d", "s");', out)


class ShippedConfigCase(unittest.TestCase):
    def test_settings_json_is_well_formed(self):
        prefs = apply.load_settings(CONFIG / "settings.json")
        self.assertTrue(prefs)

    def test_configured_prefs_differ_from_tb_defaults(self):
        defaults = tb_defaults()
        if defaults is None:
            self.skipTest("Thunderbird omni.ja not found")
        prefs = apply.load_settings(CONFIG / "settings.json")
        for key, value in prefs.items():
            if key in defaults:
                rendered = apply.literal(value)
                self.assertNotEqual(
                    rendered, defaults[key],
                    "%s equals Thunderbird's default (%s) - inert" % (key, defaults[key]))

    def test_tag_prefs_are_not_tb_defaults(self):
        defaults = tb_defaults()
        if defaults is None:
            self.skipTest("Thunderbird omni.ja not found")
        prefs = apply.tags_to_prefs(apply.load_tags(CONFIG / "tags.json"))
        for key in prefs:
            self.assertNotIn(key, defaults, "%s collides with a TB default pref" % key)


if __name__ == "__main__":
    unittest.main()
