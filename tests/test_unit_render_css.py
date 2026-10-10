"""Unit tests for bin/omarchy-tb-render-css.

The renderer is what makes a theme actually apply: it inlines the active theme's
declarations into the stylesheet's default :root block, so no userChromeJS loader is
required. These tests drive the real module (loaded from its extensionless path) and
assert the exact shape of its output — which is also what makes the file a mutation
target.
"""

import importlib.machinery
import importlib.util
import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
RENDER_PATH = REPO / "bin/omarchy-tb-render-css"
SOURCE = (REPO / "themes/userChrome.css").read_text()


def load_module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    try:
        loader.exec_module(module)
    except SystemExit as exc:
        # A broken ``if __name__ == "__main__"`` guard runs sys.exit() during import;
        # uncaught, that exits the test process with status 0 (a silent pass). Fail.
        raise ImportError("%s exited at import (%r)" % (name, exc)) from exc
    return module


render_css = load_module("render_css", RENDER_PATH)

FALLBACK = re.compile(r"(:root\s*\{)(.*?)\}", re.S)


def first_root_body(css):
    return FALLBACK.search(css).group(2)


class ThemeBlockCase(unittest.TestCase):
    def test_finds_a_known_theme_block(self):
        body = render_css._theme_block(SOURCE, "tokyo-night")
        self.assertIsNotNone(body)
        self.assertIn("--toolbar-bgcolor: #1a1b26;", body)

    def test_unknown_theme_has_no_block(self):
        self.assertIsNone(render_css._theme_block(SOURCE, "not-a-theme"))


class RenderCase(unittest.TestCase):
    def test_theme_is_inlined_into_first_root_block(self):
        out = render_css.render(SOURCE, "tokyo-night")
        body = first_root_body(out)
        self.assertIn("applied theme = tokyo-night", body)
        self.assertIn("--toolbar-bgcolor: #1a1b26;", body)

    def test_unknown_theme_uses_the_bundled_fallback(self):
        out = render_css.render(SOURCE, "nope")
        body = first_root_body(out)
        self.assertIn("applied theme = catppuccin (fallback)", body)
        # catppuccin's mocha background is the fallback
        self.assertIn("--toolbar-bgcolor: #1e1e2e;", body)

    def test_attribute_theme_blocks_are_left_untouched(self):
        out = render_css.render(SOURCE, "nord")
        # every theme block is still present, so loader users keep working too
        self.assertEqual(out.count(':root[data-omarchy-theme="'),
                         SOURCE.count(':root[data-omarchy-theme="'))

    def test_output_braces_balance(self):
        out = render_css.render(SOURCE, "gruvbox")
        self.assertEqual(out.count("{"), out.count("}"))

    def test_each_known_theme_renders_its_own_background(self):
        # A cheap regression net: several themes must inline *their* colour.
        for theme, bg in (("nord", "#2e3440"), ("tokyo-night", "#1a1b26")):
            body = first_root_body(render_css.render(SOURCE, theme))
            self.assertIn("--toolbar-bgcolor: %s;" % bg, body, theme)


class ContentCase(unittest.TestCase):
    def test_content_css_maps_the_theme_palette(self):
        out = render_css.render_content(SOURCE, "tokyo-night")
        # message-pane-background -> body background
        self.assertIn("--tb-bg: #1a1b26;", out)
        # toolbar-color -> text
        self.assertIn("--tb-fg: #a9b1d6;", out)
        # selected-item-color -> link/accent
        self.assertIn("--tb-accent: #7aa2f7;", out)

    def test_content_css_styles_body_links_and_quotes(self):
        out = render_css.render_content(SOURCE, "nord")
        self.assertIn("body {", out)
        self.assertIn("a:link", out)
        self.assertIn('blockquote[type="cite"]', out)

    def test_content_css_uses_the_fallback_for_unknown_themes(self):
        out = render_css.render_content(SOURCE, "nope")
        self.assertIn("Applied theme: catppuccin (fallback)", out)
        self.assertIn("--tb-bg: #1e1e2e;", out)

    def test_content_css_braces_balance(self):
        out = render_css.render_content(SOURCE, "gruvbox")
        self.assertEqual(out.count("{"), out.count("}"))

    def test_main_renders_content_kind_to_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            dest = pathlib.Path(tmp) / "userContent.css"
            rc = render_css.main(["nord", "--kind", "content",
                                  "--source", str(REPO / "themes/userChrome.css"),
                                  "--output", str(dest)])
            self.assertEqual(rc, 0)
            self.assertIn("--tb-bg: #2e3440;", dest.read_text())


class WriteAtomicCase(unittest.TestCase):
    def test_replaces_a_symlink_instead_of_writing_through_it(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            victim = root / "plugin-source.css"
            victim.write_text("ORIGINAL")
            dest = root / "userChrome.css"
            dest.symlink_to(victim)
            render_css.write_atomic(dest, "REPLACED")
            self.assertFalse(dest.is_symlink())
            self.assertEqual(dest.read_text(), "REPLACED")
            self.assertEqual(victim.read_text(), "ORIGINAL")

    def test_writes_a_plain_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            dest = pathlib.Path(tmp) / "out.css"
            render_css.write_atomic(dest, "hello")
            self.assertEqual(dest.read_text(), "hello")


class MainCase(unittest.TestCase):
    def test_main_writes_output_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            dest = pathlib.Path(tmp) / "userChrome.css"
            rc = render_css.main(["tokyo-night", "--source", str(REPO / "themes/userChrome.css"),
                                  "--output", str(dest)])
            self.assertEqual(rc, 0)
            self.assertIn("applied theme = tokyo-night", dest.read_text())

    def test_main_reports_a_missing_stylesheet(self):
        rc = render_css.main(["nord", "--source", "/no/such/file.css", "--output", "/tmp/x"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
