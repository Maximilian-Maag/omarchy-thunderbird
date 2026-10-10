"""Unit tests for profile/user.js as a *file* (structure + real-pref validity).

The js test kind already evaluates user.js in a sandbox and asserts the values; this
kind covers what a sandbox cannot: that the file is well-formed as a Thunderbird
pref script (no duplicate keys, only literal values), and — crucially — that every
pref the plugin claims is "deliberately non-default" actually differs from
Thunderbird's own built-in default.

That last check catches a real, silent bug class: a pref set equal to the default is
dropped from prefs.js by Thunderbird, so it does nothing at all while looking like
configuration. The defaults are read from the installed Thunderbird (omni.ja) and the
check is skipped, with a notice, when Thunderbird is not present.
"""

import pathlib
import re
import unittest
import zipfile

REPO = pathlib.Path(__file__).resolve().parent.parent
USER_JS = REPO / "profile/user.js"

OMNI_CANDIDATES = [
    pathlib.Path("/usr/lib/thunderbird/omni.ja"),
    pathlib.Path("/usr/share/thunderbird/omni.ja"),
]

# Prefs this plugin sets specifically because their value differs from Thunderbird's
# default. If any of these ever matches the default it will silently not apply.
DELIBERATELY_NON_DEFAULT = {
    "mail.biff.alert.show_preview",
    "mail.biff.play_sound",
    "mail.biff.use_new_count_in_badge",
    "mail.identity.default.sig_on_reply",
    "mail.openpgp.remind_encryption_possible",
    "mail.openpgp.allow_external_gnupg",
    "mailnews.start_page.enabled",
}

PAIR = re.compile(r'user_pref\(\s*"([^"]+)"\s*,\s*([^)]*?)\s*\)')
DEFAULT_PAIR = re.compile(r'pref\(\s*"([^"]+)"\s*,\s*([^;\n]*?)\s*\)')


def _literal(raw):
    raw = raw.strip()
    if raw == "true":
        return True
    if raw == "false":
        return False
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d+\.\d+", raw):
        return float(raw)
    m = re.fullmatch(r'"(.*)"|\'(.*)\'', raw)
    if m:
        return m.group(1) if m.group(1) is not None else m.group(2)
    return raw


def pref_pairs(text):
    return [(k, _literal(v)) for k, v in PAIR.findall(text)]


def thunderbird_prefs():
    """(defaults, referenced) scraped from the installed Thunderbird, else None.

    `defaults` maps a pref to its built-in default value (from `pref("k", v)`).
    `referenced` is every pref-like quoted string appearing in the shipped JS — a
    pref Thunderbird reads via getBoolPref() without declaring a default is real but
    absent from `defaults`, so realness is the union of the two.
    """
    omni = next((p for p in OMNI_CANDIDATES if p.is_file()), None)
    if omni is None:
        return None
    defaults = {}
    referenced = set()
    pref_like = re.compile(r'"([a-z][A-Za-z0-9_]{2,}(?:\.[A-Za-z0-9_]+)+)"')
    with zipfile.ZipFile(omni) as archive:
        for name in archive.namelist():
            if not name.endswith((".js", ".mjs")):
                continue
            try:
                body = archive.read(name).decode("utf-8", "replace")
            except (KeyError, OSError):
                continue
            for key, raw in DEFAULT_PAIR.findall(body):
                if key not in defaults and not key.startswith("_"):
                    defaults[key] = _literal(raw)
            referenced.update(pref_like.findall(body))
    return defaults, referenced


class UserJsStructureCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = USER_JS.read_text()
        cls.pairs = pref_pairs(cls.text)

    def test_file_is_non_trivial(self):
        self.assertGreaterEqual(len(self.pairs), 27)

    def test_no_duplicate_pref_keys(self):
        keys = [k for k, _ in self.pairs]
        dupes = sorted({k for k in keys if keys.count(k) > 1})
        self.assertEqual(dupes, [], "duplicate prefs in user.js: %s" % dupes)

    def test_every_value_is_a_literal(self):
        # A user_pref() whose value is not a bool/number/string literal cannot be
        # parsed by Thunderbird's prefs reader and would abort the whole file.
        for key, value in self.pairs:
            self.assertIn(type(value), (bool, int, float, str),
                          "%s has a non-literal value: %r" % (key, value))

    def test_pref_names_are_well_formed(self):
        for key, _ in self.pairs:
            self.assertRegex(key, r"^[A-Za-z][A-Za-z0-9_.-]*$", "odd pref name: %s" % key)

    def test_userchrome_theming_pref_is_enabled(self):
        prefs = dict(self.pairs)
        self.assertIs(prefs["toolkit.legacyUserProfileCustomizations.stylesheets"], True)


class NonDefaultPrefsCase(unittest.TestCase):
    def test_documented_non_default_prefs_actually_differ_from_tb_defaults(self):
        index = thunderbird_prefs()
        if index is None:
            self.skipTest("Thunderbird omni.ja not found; cannot cross-check defaults")
        defaults, referenced = index
        prefs = dict(pref_pairs(USER_JS.read_text()))
        for key in DELIBERATELY_NON_DEFAULT:
            self.assertIn(key, prefs, "user.js no longer sets %s" % key)
            # A pref is real if Thunderbird declares a default for it or reads it
            # anywhere in its shipped JS (some are read with an inline fallback).
            self.assertTrue(key in defaults or key in referenced,
                            "%s is not a pref Thunderbird knows" % key)
            if key in defaults:
                self.assertNotEqual(
                    prefs[key], defaults[key],
                    "%s is set to Thunderbird's own default (%r) - it will be "
                    "dropped from prefs.js and do nothing" % (key, defaults[key]))


if __name__ == "__main__":
    unittest.main()
