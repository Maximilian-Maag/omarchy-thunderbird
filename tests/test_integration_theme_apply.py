"""Integration test: hook -> profile lookup -> renderer -> applied stylesheet.

This is the seam the unit tests cannot see on their own. It runs the *real* theme-set
hook under a temporary XDG tree (never the live profile), then checks the file the
hook produced against the stylesheet's own theme block: the applied :root must carry
exactly the requested theme's declarations, and every attribute block must survive so
loader users are unaffected. A regression that broke any link in that chain — the
profile lookup, the render call, the inlining — fails here.
"""

import os
import pathlib
import re
import subprocess
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
HOOK = REPO / "hooks/theme-set"
SOURCE = (REPO / "themes/userChrome.css").read_text()

DECL = re.compile(r"(--[a-z-]+)\s*:\s*([^;]+);")


def first_root_body(css):
    return re.search(r":root\s*\{(.*?)\}", css, re.S).group(1)


def theme_body(css, theme):
    return re.search(
        r':root\[data-omarchy-theme="%s"\]\s*\{(.*?)\}' % re.escape(theme),
        css, re.S).group(1)


def decls(body):
    return {k: v.strip() for k, v in DECL.findall(body)}


class ThemeApplyCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        (self.root / "thunderbird" / "abc.default-release").mkdir(parents=True)
        (self.root / "thunderbird" / "profiles.ini").write_text(
            "[Profile0]\nName=default\nPath=abc.default-release\nDefault=1\nIsRelative=1\n")

    def tearDown(self):
        self._tmp.cleanup()

    def run_hook(self, *args):
        env = dict(os.environ, XDG_CONFIG_HOME=str(self.root))
        return subprocess.run(["bash", str(HOOK), *args], env=env,
                              capture_output=True, text=True)

    @property
    def css_path(self):
        return self.root / "thunderbird" / "abc.default-release" / "chrome" / "userChrome.css"

    @property
    def content_path(self):
        return self.root / "thunderbird" / "abc.default-release" / "chrome" / "userContent.css"

    def test_hook_also_renders_the_message_body_stylesheet(self):
        self.run_hook("tokyo-night")
        content = self.content_path.read_text()
        # The body background must be the theme's message-pane colour.
        self.assertIn("--tb-bg: #1a1b26;", content)
        self.assertIn("Applied theme: tokyo-night", content)

    def test_applied_root_matches_the_requested_theme_exactly(self):
        for theme in ("tokyo-night", "nord", "gruvbox"):
            result = self.run_hook(theme)
            self.assertEqual(result.returncode, 0, result.stderr)
            applied = decls(first_root_body(self.css_path.read_text()))
            wanted = decls(theme_body(SOURCE, theme))
            self.assertEqual(applied, wanted, "applied :root != %s block" % theme)

    def test_every_attribute_block_survives_the_render(self):
        self.run_hook("tokyo-night")
        rendered = self.css_path.read_text()
        self.assertEqual(rendered.count(':root[data-omarchy-theme="'),
                         SOURCE.count(':root[data-omarchy-theme="'))

    def test_switching_themes_rewrites_the_applied_stylesheet(self):
        self.run_hook("tokyo-night")
        first = first_root_body(self.css_path.read_text())
        self.run_hook("nord")
        second = first_root_body(self.css_path.read_text())
        self.assertIn("applied theme = nord", second)
        self.assertNotEqual(first, second)

    def test_empty_theme_is_a_noop(self):
        self.run_hook("tokyo-night")
        before = self.css_path.read_text()
        self.run_hook("")
        self.assertEqual(self.css_path.read_text(), before)


if __name__ == "__main__":
    unittest.main()
