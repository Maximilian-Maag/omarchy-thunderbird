"""Regression tests for the Thunderbird 155 chrome-variable compatibility layer.

Thunderbird 155 replaced the chrome variable layer this plugin was written against:

* the surface colours (``--toolbar-bgcolor``, the ``--*-pane-*`` family) became a
  ``--layout-*`` system — ``--layout-background-0/1/2`` for surfaces and
  ``--layout-color-0/1/2`` for text;
* the button variables were renamed into the ``--button-<variant>-<property>`` form
  (``--button-primary-bgcolor`` -> ``--button-primary-background-color``);
* selection and the accent are now *derived* from ``--selected-item-color`` /
  ``--color-accent-primary`` / the ``--button-primary-*`` family rather than read.

The per-theme ``:root`` blocks still set the original palette names (they are the
theme palette, and the supplementary rules consume them too). ``themes/userChrome.css``
therefore ends with a compatibility ``:root`` block that bridges those palette entries
onto the names Thunderbird 155 actually consumes.

These tests pin that bridge, so a future Thunderbird rename — or a careless edit that
drops or mis-spells a mapping — is caught here instead of showing up as an unthemed
window.
"""

import importlib.machinery
import importlib.util
import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
SOURCE = (REPO / "themes/userChrome.css").read_text()
RENDER_PATH = REPO / "bin/omarchy-tb-render-css"

# target variable (what Thunderbird 155 consumes) -> palette variable (what the
# theme blocks set, and what the compatibility layer bridges from)
MAPPING = {
    "--toolbar-background-color": "--toolbar-bgcolor",
    "--toolbar-text-color": "--toolbar-color",
    "--layout-background-0": "--toolbar-bgcolor",
    "--layout-background-1": "--thread-pane-background",
    "--layout-color-0": "--toolbar-color",
    "--layout-color-1": "--thread-pane-color",
    "--sidebar-background": "--sidebar-background-color",
    "--sidebar-color": "--sidebar-text-color",
    "--tree-view-color": "--thread-pane-color",
    "--theme-splitter-color": "--splitter-color",
    "--toolbarbutton-background-color-hover": "--toolbarbutton-hover-background",
    "--toolbarbutton-background-color-active": "--toolbarbutton-active-background",
    "--button-primary-background-color": "--button-primary-bgcolor",
    "--button-primary-hover-background-color": "--button-primary-hover-bgcolor",
    "--button-primary-text-color": "--button-primary-color",
    "--color-accent-primary": "--button-primary-bgcolor",
    "--sidebar-highlight-background-color": "--selected-item-color",
    "--selected-item-color": "--button-primary-bgcolor",
    "--new-folder-color": "--button-primary-bgcolor",
    "--new-focused-folder-color": "--selected-item-text-color",
}


def _load_render():
    loader = importlib.machinery.SourceFileLoader("render_css_reg", str(RENDER_PATH))
    spec = importlib.util.spec_from_loader("render_css_reg", loader)
    module = importlib.util.module_from_spec(spec)
    try:
        loader.exec_module(module)
    except SystemExit as exc:
        # a broken ``if __name__ == "__main__"`` guard runs sys.exit() at import and
        # would otherwise exit the test process 0 — a silent pass. Fail instead.
        raise ImportError("renderers exited at import (%r)" % exc) from exc
    return module


def compat_block():
    """The ``:root`` block of the TB 155 compatibility layer."""
    marker = SOURCE.find("THUNDERBIRD 155 COMPATIBILITY")
    assert marker != -1, "the Thunderbird 155 compatibility section is missing"
    match = re.search(r":root\s*\{(.*?)\}", SOURCE[marker:], re.S)
    assert match, "the Thunderbird 155 compatibility layer has no :root block"
    return match.group(1)


class Tb155CompatCase(unittest.TestCase):
    def test_the_compatibility_layer_is_present(self):
        self.assertIn("THUNDERBIRD 155 COMPATIBILITY", SOURCE)
        self.assertGreater(len(compat_block()), 200)

    def test_every_current_variable_is_bridged(self):
        block = compat_block()
        for target, source in MAPPING.items():
            self.assertIn("%s: var(%s)" % (target, source), block,
                          "%s is not bridged to %s" % (target, source))

    def test_the_bridge_declares_the_new_names_not_the_old_ones(self):
        block = compat_block()
        self.assertIn("--layout-background-0:", block)
        self.assertIn("--button-primary-background-color:", block)
        # the layer maps *onto* the new names; it must not re-declare old ones
        # the layer maps *onto* the new names; it must not re-declare the old palette
        # names (--selected-item-color is the one exception: TB 155 derives it from
        # other variables, so the bridge re-asserts the theme's value explicitly).
        for old in set(MAPPING.values()) - {"--selected-item-color"}:
            self.assertNotIn("%s:" % old, block,
                             "%s is re-declared in the bridge instead of bridged" % old)

    def test_every_bridged_variable_is_actually_set_by_the_theme_blocks(self):
        # a bridge to a variable nothing sets would silently do nothing
        for source in set(MAPPING.values()):
            self.assertRegex(SOURCE, re.escape(source) + r"\s*:",
                             "%s is bridged but never set" % source)

    def test_the_renderer_sets_every_bridged_variable_for_derived_themes(self):
        # a user's own theme has no curated block, so its palette comes from the
        # renderer's derived_block — that must set the same source variables.
        render = _load_render()
        block = render.derived_block({
            "mode": "dark", "background": "#000000", "foreground": "#ffcc00",
            "accent": "#ffcc00", "selection": "#1a1810", "dark_background": "#0a0a0a",
            "lighter_background": "#1a1810", "dark_foreground": "#8a7300",
        })
        for source in set(MAPPING.values()):
            self.assertIn("%s:" % source, block,
                          "the renderer does not set %s for derived themes" % source)

    def test_render_output_keeps_the_compatibility_layer(self):
        render = _load_render()
        out = render.render(SOURCE, "tokyo-night")
        self.assertIn("THUNDERBIRD 155 COMPATIBILITY", out)
        self.assertIn("--toolbar-background-color: var(--toolbar-bgcolor)", out)
        self.assertIn("--layout-background-1: var(--thread-pane-background)", out)


if __name__ == "__main__":
    unittest.main()
