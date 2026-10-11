"""Regression tests: the declarative auto-sort rule contract.

Pins the rule set and — the cross-file contract that matters — that every tag a rule
applies exists in config/tags.json.
"""

import json
import pathlib
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
CONFIG = REPO / "config"

GOLDEN_RULE_NAMES = [
    "Ordering confirmations",
    "Invoices",
    "Mailing lists and newsletters",
    "Newsletters by wording",
    "Code hosting notifications",
    "Receipts without a matching folder",
]


class RuleContractCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = json.loads((CONFIG / "rules.json").read_text())["rules"]
        cls.tag_keys = {t["key"] for t in json.loads((CONFIG / "tags.json").read_text())["tags"]}

    def test_rule_names_are_unchanged(self):
        self.assertEqual([r["name"] for r in self.rules], GOLDEN_RULE_NAMES)

    def test_every_applied_tag_exists(self):
        for rule in self.rules:
            for tag in rule.get("actions", {}).get("add_tags", []):
                self.assertIn(tag, self.tag_keys,
                              "%s applies unknown tag %r" % (rule["name"], tag))

    def test_the_destinations_are_named(self):
        for rule in self.rules:
            move = rule.get("actions", {}).get("move_to")
            if move is not None:
                self.assertTrue(move.strip(), "%s has an empty move_to" % rule["name"])


if __name__ == "__main__":
    unittest.main()
