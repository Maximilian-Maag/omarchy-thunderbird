"""Integration tests: hooks/theme-set against a throw-away Thunderbird profile.

The hook is the plugin's only live integration surface: Omarchy calls it with the
name of the active theme and it writes that theme into whichever profile
Thunderbird reads at startup. These tests run the real hook under a temporary
XDG_CONFIG_HOME with a synthetic profiles.ini — never the user's own profile and
never the desktop session.
"""
import os
import pathlib
import subprocess
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
HOOK = REPO / "hooks/theme-set"


class ThemeSetHookCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.tb = self.root / "thunderbird"
        self.tb.mkdir()
        self.env = {**os.environ, "XDG_CONFIG_HOME": str(self.root)}
        self.env.pop("XDG_STATE_HOME", None)

    def add_profile(self, name, *, relative=True, exists=True):
        section = "IsRelative=1" if relative else "IsRelative=0"
        (self.tb / "profiles.ini").write_text(
            "[Profile0]\nName=default\nPath=%s\nDefault=1\n%s\n" % (name, section))
        profile = self.tb / name
        if exists:
            profile.mkdir(parents=True)
        return profile

    def run_hook(self, *args):
        return subprocess.run(["bash", str(HOOK), *args], env=self.env,
                              capture_output=True, text=True)

    def test_theme_is_written_into_the_default_release_profile(self):
        profile = self.add_profile("abc.default-release")
        proc = self.run_hook("Tokyo Night")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        state = profile / "chrome/omarchy-active-theme"
        self.assertEqual(state.read_text().strip(), "tokyo-night")

    def test_generated_helper_carries_the_slug(self):
        profile = self.add_profile("abc.default-release")
        self.run_hook("gruvbox")
        helper = (profile / "chrome/set-theme.uc.js").read_text()
        self.assertIn('const theme = "gruvbox";', helper)
        self.assertIn("data-omarchy-theme", helper)
        self.assertIn("JSON.stringify(theme)", helper)

    def test_unset_theme_is_a_silent_noop(self):
        profile = self.add_profile("abc.default-release")
        proc = self.run_hook()
        self.assertEqual(proc.returncode, 0)
        self.assertFalse((profile / "chrome").exists())

    def test_missing_profile_directory_creates_nothing(self):
        self.add_profile("ghost-profile", exists=False)
        proc = self.run_hook("nord")
        self.assertEqual(proc.returncode, 0)
        self.assertFalse((self.tb / "ghost-profile").exists())

    def test_existing_userchrome_symlink_is_preserved(self):
        profile = self.add_profile("abc.default-release")
        chrome = profile / "chrome"
        chrome.mkdir()
        target = REPO / "themes/userChrome.css"
        (chrome / "userChrome.css").symlink_to(target)
        proc = self.run_hook("everforest")
        self.assertEqual(proc.returncode, 0)
        self.assertTrue((chrome / "userChrome.css").is_symlink())
        self.assertEqual(os.readlink(chrome / "userChrome.css"), str(target))


if __name__ == "__main__":
    unittest.main()
