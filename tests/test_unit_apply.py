"""Unit tests for bin/omarchy-thunderbird-apply and the shipped config/ files.

The applier turns config/*.json into the profile's user.js. Its parsing, validation
and merge logic are pinned here, and the *shipped* config is checked too: every tag is
well-formed and every configured pref actually differs from Thunderbird's built-in
default (a pref equal to the default is dropped from prefs.js and does nothing).
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
