"""Unit tests for bin/omarchy-thunderbird-rules and the shipped config/rules.json.

The rules CLI is what stops a typo in a rule from shipping as a silent no-op — most
of all a rule that tags a message with a tag that does not exist.
"""

import importlib.machinery
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
RULES_CLI = REPO / "bin/omarchy-thunderbird-rules"
CONFIG = REPO / "config"


def load_module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    try:
        loader.exec_module(module)
    except SystemExit as exc:
        raise ImportError("%s exited at import (%r)" % (name, exc)) from exc
    return module


rules_cli = load_module("tb_rules", RULES_CLI)
TAG_KEYS = rules_cli.tag_keys(CONFIG / "tags.json")


class ValidateCase(unittest.TestCase):
    def problems(self, rule):
        return rules_cli.validate_rules([rule], TAG_KEYS)

    def test_shipped_rules_are_valid(self):
        rules = json.loads((CONFIG / "rules.json").read_text())["rules"]
        self.assertEqual(rules_cli.validate_rules(rules, TAG_KEYS), [])

    def test_unknown_match_key_is_flagged(self):
        out = self.problems({"name": "x", "match": {"bogus": 1}, "actions": {}})
        self.assertTrue(any("unknown match key" in p for p in out))

    def test_unknown_action_key_is_flagged(self):
        out = self.problems({"name": "x", "match": {}, "actions": {"delete": True}})
        self.assertTrue(any("unknown action key" in p for p in out))

    def test_unknown_tag_is_flagged(self):
        out = self.problems({"name": "x", "match": {}, "actions": {"add_tags": ["nope"]}})
        self.assertTrue(any("unknown tag" in p for p in out))

    def test_known_tag_is_accepted(self):
        self.assertEqual(self.problems({"name": "x", "match": {}, "actions": {"add_tags": ["invoice"]}}), [])

    def test_empty_move_to_is_flagged(self):
        out = self.problems({"name": "x", "match": {}, "actions": {"move_to": "  "}})
        self.assertTrue(any("move_to is empty" in p for p in out))

    def test_duplicate_names_are_flagged(self):
        out = rules_cli.validate_rules(
            [{"name": "dup", "match": {}, "actions": {}}, {"name": "dup", "match": {}, "actions": {}}],
            TAG_KEYS)
        self.assertTrue(any("duplicate name" in p for p in out))

    def test_a_non_list_match_value_is_flagged(self):
        out = self.problems({"name": "x", "match": {"subject_contains": "invoice"}, "actions": {}})
        self.assertTrue(any("must be a list" in p for p in out))

    def test_empty_rule_list_is_flagged(self):
        self.assertTrue(rules_cli.validate_rules([], TAG_KEYS))

    def test_has_attachment_bool_is_allowed_as_a_non_list(self):
        self.assertEqual(self.problems({"name": "x", "match": {"has_attachment": True}, "actions": {}}), [])


class CliCase(unittest.TestCase):
    def test_validate_exits_zero_for_shipped_config(self):
        result = subprocess.run([sys.executable, str(RULES_CLI), "--validate"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_validate_exits_one_for_broken_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / "tags.json").write_text(json.dumps({"tags": [{"key": "invoice", "name": "I", "color": "#000000"}]}))
            (pathlib.Path(tmp) / "rules.json").write_text(json.dumps(
                {"rules": [{"name": "x", "match": {}, "actions": {"add_tags": ["ghost"]}}]}))
            result = subprocess.run([sys.executable, str(RULES_CLI), "--validate", "--config-dir", tmp],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("ghost", result.stdout)

    def test_missing_config_dir_exits_one(self):
        result = subprocess.run(
            [sys.executable, str(RULES_CLI), "--validate", "--config-dir", "/nonexistent/deep/tmp"],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)

    def test_missing_tags_file_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / "rules.json").write_text(json.dumps({"rules": [{"name": "x", "match": {}, "actions": {}}]}))
            result = subprocess.run([sys.executable, str(RULES_CLI), "--validate", "--config-dir", tmp],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
