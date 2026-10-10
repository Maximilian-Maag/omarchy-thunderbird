"""Regression tests: the documented preference contract of profile/user.js.

The unit/js kinds prove the file parses and that the new prefs differ from
Thunderbird's defaults. This kind pins the *whole* documented contract as a golden
map: if any key here is removed, renamed, or has its value flipped during later work,
the regression fails and points at exactly which promise was broken.

Deliberately readable and dependency-light — it parses the shipped file directly
rather than importing another test module, so it stands on its own.
"""

import pathlib
import re
import unittest

USER_JS = pathlib.Path(__file__).resolve().parent.parent / "profile/user.js"

# The prefs this plugin promises. Value types are the JS literal types.
GOLDEN = {
    "toolkit.legacyUserProfileCustomizations.stylesheets": True,
    "mail.tabs.autoHide": False,
    "mail.tabs.drawInTitlebar": True,
    "mail.forward_message_mode": 1,
    "mail.remote_content.blocked_by_default": True,
    "permissions.default.image": 2,
    "datareporting.healthreport.uploadEnabled": False,
    "datareporting.policy.dataSubmissionEnabled": False,
    "toolkit.telemetry.enabled": False,
    "app.normandy.enabled": False,
    "browser.crashReports.unsubmittedCheck.enabled": False,
    "mail.biff.animate_dock_icon": False,
    "mail.biff.alert.show_preview": False,
    "mail.biff.play_sound": False,
    "mail.biff.use_new_count_in_badge": True,
    "mail.identity.default.sig_on_reply": False,
    "mail.openpgp.remind_encryption_possible": False,
    "mail.openpgp.allow_external_gnupg": True,
    "mailnews.start_page.enabled": False,
    "calendar.view.useSystemColors": False,
}


def parse(text):
    def literal(raw):
        raw = raw.strip()
        if raw in ("true", "false"):
            return raw == "true"
        if re.fullmatch(r"-?\d+", raw):
            return int(raw)
        m = re.fullmatch(r'"(.*)"', raw)
        return m.group(1) if m else raw

    return {k: literal(v) for k, v in
            re.findall(r'user_pref\(\s*"([^"]+)"\s*,\s*([^)]*?)\s*\)', text)}


class PrefContractCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prefs = parse(USER_JS.read_text())

    def test_every_promised_pref_is_present_with_its_value(self):
        for key, want in GOLDEN.items():
            self.assertIn(key, self.prefs, "pref %s disappeared from user.js" % key)
            self.assertEqual(self.prefs[key], want,
                             "pref %s changed: want %r got %r"
                             % (key, want, self.prefs[key]))

    def test_no_promised_pref_is_silently_dropped(self):
        # Guard the count too: a wholesale edit that removes prefs without touching
        # the map above would otherwise pass. 27 is the documented floor.
        self.assertGreaterEqual(len(self.prefs), 27)


if __name__ == "__main__":
    unittest.main()
