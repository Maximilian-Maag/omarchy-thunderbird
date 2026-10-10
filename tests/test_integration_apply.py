"""Integration test: omarchy-thunderbird-apply writes a real profile's user.js.

Runs the shipped applier as a program against a throwaway profile (temp
XDG_CONFIG_HOME) and checks the file it produces: the tags and settings land, the
base prefs are present, re-running is idempotent (no duplicate keys), and a pref the
user added by hand survives a re-run.
"""

import os
import pathlib
import re
import subprocess
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
APPLY = REPO / "bin/omarchy-thunderbird-apply"
PREF = re.compile(r'user_pref\(\s*"([^"]+)"')


class ApplyIntegrationCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.profile = self.root / "thunderbird" / "abc.default-release"
        self.profile.mkdir(parents=True)
        (self.root / "thunderbird" / "profiles.ini").write_text(
            "[Profile0]\nName=default\nPath=abc.default-release\nDefault=1\nIsRelative=1\n")

    def tearDown(self):
        self._tmp.cleanup()

    def run_apply(self):
        env = dict(os.environ, XDG_CONFIG_HOME=str(self.root))
        return subprocess.run(["python3", str(APPLY)], env=env, capture_output=True, text=True)

    @property
    def userjs(self):
        return (self.profile / "user.js").read_text()

    def test_tags_and_settings_land_in_user_js(self):
        result = self.run_apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.userjs
        self.assertIn('user_pref("mailnews.tags.important.tag", "Important");', text)
        self.assertIn('user_pref("mailnews.tags.suspicious.color", "#d20f39");', text)
        self.assertIn('user_pref("mail.spam.logging.enabled", true);', text)
        # base prefs still present
        self.assertIn("toolkit.legacyUserProfileCustomizations.stylesheets", text)

    def test_rerun_is_idempotent(self):
        self.run_apply()
        first = self.userjs
        self.run_apply()
        self.assertEqual(self.userjs, first)
        # no key appears twice
        keys = PREF.findall(self.userjs)
        self.assertEqual(len(keys), len(set(keys)), "duplicate pref keys in user.js")

    def test_a_hand_added_pref_survives_a_rerun(self):
        self.run_apply()
        target = self.profile / "user.js"
        target.write_text(target.read_text() + '\nuser_pref("mine.keep", 7);\n')
        self.run_apply()
        self.assertIn('user_pref("mine.keep", 7);', self.userjs)


if __name__ == "__main__":
    unittest.main()
