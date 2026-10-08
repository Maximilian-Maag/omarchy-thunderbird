"""Regression tests for the Hyprland keybindings in bin/bindings.lua.

Each test names the bug it pins, from the plugin's own history:

  * launch-or-focus (c5cd43f): the focus pattern was ``^thunderbird$``, but the
    Wayland window class is ``org.mozilla.Thunderbird``. The pattern never matched,
    so Super+Shift+E/C spawned a second Thunderbird instead of focusing the running
    one.
  * workspace-4-silent (c5cd43f): nothing placed Thunderbird, so the instance
    autostarted at login stole focus on whatever workspace was active. The window
    rule must move it to workspace 4 *silently*.
"""
import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
BINDINGS = (REPO / "bin/bindings.lua").read_text()

HEY_COMBOS = ["SUPER + SHIFT + E", "SUPER + SHIFT + ALT + E", "SUPER + SHIFT + C"]


class LaunchOrFocusCase(unittest.TestCase):
    def test_focus_uses_the_wayland_window_class_not_the_old_anchor(self):
        patterns = re.findall(r'focus\s*=\s*"([^"]+)"', BINDINGS)
        self.assertTrue(patterns, "no o.bind focus= entries found")
        for pattern in patterns:
            self.assertNotEqual(pattern, "^thunderbird$",
                                "the old anchored class never matched the Wayland window")
            self.assertIn("Thunderbird", pattern)

    def test_hey_webapp_bindings_are_unbound_before_rebinding(self):
        for combo in HEY_COMBOS:
            self.assertIn('hl.unbind("%s")' % combo, BINDINGS,
                          "%s must be unbound first" % combo)

    def test_three_native_thunderbird_bindings_exist(self):
        self.assertEqual(len(re.findall(r"o\.bind\(", BINDINGS)), 3)


class WorkspaceFourCase(unittest.TestCase):
    def test_window_rule_pins_thunderbird_to_workspace_4_silently(self):
        m = re.search(r'o\.window\("([^"]+)"\s*,\s*\{[^}]*?workspace\s*=\s*"([^"]*)"',
                      BINDINGS)
        self.assertIsNotNone(m, "no o.window workspace rule found")
        pattern, placement = m.groups()
        self.assertEqual(placement, "4 silent",
                         "the autostarted instance must not steal focus")
        self.assertIn("hunderbird", pattern)
        self.assertIn("mozilla", pattern)

    def test_window_rule_also_matches_the_org_mozilla_class(self):
        self.assertRegex(BINDINGS, r"org.*mozilla",
                         "the rule must cover the Wayland app_id org.mozilla.Thunderbird")


if __name__ == "__main__":
    unittest.main()
