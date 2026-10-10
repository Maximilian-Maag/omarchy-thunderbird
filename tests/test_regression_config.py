"""Regression tests: the declarative config contract.

The tag set and settings are configuration the user relies on; this pins them as a
golden map so a later edit that silently drops a tag or changes a colour fails loudly.
"""

import json
import pathlib
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
CONFIG = REPO / "config"

GOLDEN_TAGS = {
    "important": "#e64553",
    "action": "#fe640b",
    "waiting": "#df8e1d",
    "newsletter": "#8839ef",
    "invoice": "#40a02b",
    "receipt": "#179299",
    "archive": "#7c7f93",
    "suspicious": "#d20f39",
}

GOLDEN_SETTINGS = {
    "mail.spam.logging.enabled": True,
}


class ConfigContractCase(unittest.TestCase):
    def test_tag_keys_and_colours_are_unchanged(self):
        tags = json.loads((CONFIG / "tags.json").read_text())["tags"]
        got = {tag["key"]: tag["color"] for tag in tags}
        self.assertEqual(got, GOLDEN_TAGS)

    def test_a_suspicious_tag_exists_for_the_guard(self):
        tags = json.loads((CONFIG / "tags.json").read_text())["tags"]
        self.assertTrue(any(t["key"] == "suspicious" for t in tags))

    def test_settings_are_unchanged(self):
        prefs = json.loads((CONFIG / "settings.json").read_text())["prefs"]
        self.assertEqual(prefs, GOLDEN_SETTINGS)


if __name__ == "__main__":
    unittest.main()
