"""Unit tests: the shipped theme CSS and the enterprise policy skeleton.

Both files are data rather than code, but they are the heart of the plugin: the CSS
maps every stock Omarchy theme onto Thunderbird's chrome variables and the policy
skeleton pins the privacy defaults. Correctness here is a set of exact facts, so
each one is asserted directly against the shipped file.
"""
import json
import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
CSS = REPO / "themes/userChrome.css"
POLICIES = REPO / "bin/policies.json"

# The 22 stock Omarchy themes, as listed in the CSS header.
THEMES = [
    "catppuccin", "catppuccin-latte", "ethereal", "everforest",
    "flexoki-light", "gruvbox", "hackerman", "kanagawa", "last-horizon",
    "lumon", "lupine", "matte-black", "miasma", "nord", "osaka-jade",
    "retro-82", "ristretto", "rose-pine", "solitude", "tokyo-night",
    "vantablack", "white",
]

CORE_VARS = [
    "--toolbar-bgcolor", "--toolbar-color",
    "--folder-pane-background", "--thread-pane-background",
    "--message-pane-background", "--focus-outline-color",
]


def theme_blocks(text):
    """{theme-name: block-body} for every :root[data-omarchy-theme="..."] rule."""
    return {m.group(1): m.group(2) for m in re.finditer(
        r':root\[data-omarchy-theme="([^"]+)"\]\s*\{(.*?)\}', text, re.S)}


class ThemeCssCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = CSS.read_text()
        cls.blocks = theme_blocks(cls.text)

    def test_all_22_stock_themes_are_covered(self):
        self.assertEqual(sorted(self.blocks), sorted(THEMES))

    def test_fallback_root_block_exists(self):
        # The :root default is what paints before userChrome.js sets the attribute.
        self.assertRegex(self.text, r":root\s*\{")

    def test_every_theme_sets_the_core_chrome_variables(self):
        for theme, body in self.blocks.items():
            for var in CORE_VARS:
                self.assertIn(var, body, "%s is missing %s" % (theme, var))

    def test_every_theme_declares_a_colour_scheme(self):
        for theme, body in self.blocks.items():
            self.assertRegex(body, r"color-scheme:\s*(dark|light)", theme)

    def test_colour_values_are_six_digit_hex(self):
        values = re.findall(r"--[a-z-]+:\s*(#[0-9A-Fa-f]+)", self.text)
        self.assertTrue(values)
        for value in values:
            self.assertEqual(len(value), 7, value)


class PoliciesCase(unittest.TestCase):
    # Pref prefixes Thunderbird's enterprise policy will actually apply; anything
    # else is logged as "not allowed for stability reasons" and silently ignored.
    ALLOWED_PREFIXES = (
        "accessibility.", "app.update.", "browser.", "calendar.", "chat.",
        "datareporting.policy.", "dom.", "extensions.", "general.autoScroll",
        "general.smoothScroll", "geo.", "gfx.", "intl.", "layers.", "layout.",
        "mail.", "mailnews.", "media.", "network.", "pdfjs.", "places.", "print.",
        "signon.", "spellchecker.", "ui.", "widget.",
    )

    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(POLICIES.read_text())["policies"]

    def test_telemetry_is_disabled(self):
        self.assertIs(self.data["DisableTelemetry"], True)

    def test_default_client_prompt_is_suppressed(self):
        # The plugin IS the default client, so Thunderbird must not keep asking.
        self.assertIs(self.data["DontCheckDefaultClient"], True)

    def test_remote_content_is_blocked_by_default(self):
        pref = self.data["Preferences"]["mail.remote_content.blocked_by_default"]
        self.assertIs(pref["Value"], True)

    def test_every_policy_pref_is_on_the_allowlist(self):
        # A pref outside these prefixes does nothing (TB rejects it) — silent config
        # drift. Everything the plugin actually needs lives in profile/user.js.
        for key in self.data.get("Preferences", {}):
            self.assertTrue(
                any(key.startswith(prefix) for prefix in self.ALLOWED_PREFIXES),
                "policy pref %s is outside Thunderbird's allowlist" % key)


if __name__ == "__main__":
    unittest.main()
