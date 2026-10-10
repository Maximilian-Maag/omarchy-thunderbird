"""Unit tests for bin/omarchy-tb-profile.

The profile finder decides which Thunderbird profile the plugin writes its assets
into. Getting this wrong means theming the wrong profile, so the preference order is
pinned here against synthetic profiles.ini files in a temporary XDG tree.
"""

import importlib.machinery
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
PROFILE_PATH = REPO / "bin/omarchy-tb-profile"


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


tb_profile = load_module("tb_profile", PROFILE_PATH)


class FindProfileCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write_ini(self, text):
        (self.root / "profiles.ini").write_text(text)

    def test_no_profiles_ini_returns_none(self):
        self.assertIsNone(tb_profile.find_profile(self.root))

    def test_prefers_default_release(self):
        self.write_ini(
            "[Profile0]\nName=plain\nPath=plain.default\nDefault=1\nIsRelative=1\n"
            "[Profile1]\nName=release\nPath=abc.default-release\nDefault=0\nIsRelative=1\n")
        self.assertEqual(tb_profile.find_profile(self.root),
                         self.root / "abc.default-release")

    def test_falls_back_to_default_flag(self):
        self.write_ini("[Profile0]\nName=plain\nPath=plain.default\nDefault=1\nIsRelative=1\n")
        self.assertEqual(tb_profile.find_profile(self.root), self.root / "plain.default")

    def test_falls_back_to_first_relative_profile(self):
        self.write_ini("[Profile0]\nName=odd\nPath=odd.profile\nIsRelative=1\n")
        self.assertEqual(tb_profile.find_profile(self.root), self.root / "odd.profile")

    def test_profile_without_path_is_skipped(self):
        self.write_ini("[General]\nStartWithLastProfile=1\n"
                       "[Profile0]\nName=x\nDefault=1\nIsRelative=1\n")
        self.assertIsNone(tb_profile.find_profile(self.root))

    def test_default_flag_beats_an_earlier_relative_profile(self):
        # A profile flagged Default=1 must win over an earlier IsRelative-only one.
        self.write_ini(
            "[Profile0]\nName=first\nPath=first.profile\nIsRelative=1\n"
            "[Profile1]\nName=second\nPath=second.profile\nDefault=1\nIsRelative=1\n")
        self.assertEqual(tb_profile.find_profile(self.root),
                         self.root / "second.profile")


class CliCase(unittest.TestCase):
    """Run the tool as a program: this is the contract callers rely on."""

    def run_cli(self, xdg):
        env = dict(os.environ, XDG_CONFIG_HOME=xdg)
        return subprocess.run([sys.executable, str(PROFILE_PATH)], env=env,
                              capture_output=True, text=True)

    def test_cli_exits_1_when_no_profile_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / "thunderbird").mkdir()
            self.assertEqual(self.run_cli(tmp).returncode, 1)

    def test_cli_prints_the_profile_and_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            tb = pathlib.Path(tmp) / "thunderbird"
            tb.mkdir()
            (tb / "profiles.ini").write_text(
                "[Profile0]\nName=r\nPath=z.default-release\nDefault=1\nIsRelative=1\n")
            result = self.run_cli(tmp)
            self.assertEqual(result.returncode, 0)
            self.assertIn("z.default-release", result.stdout)


class MainCase(unittest.TestCase):
    def test_main_honours_xdg_config_home(self):
        import contextlib
        import io
        import os
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "thunderbird").mkdir()
            (root / "thunderbird" / "profiles.ini").write_text(
                "[Profile0]\nName=r\nPath=z.default-release\nDefault=1\nIsRelative=1\n")
            old = os.environ.get("XDG_CONFIG_HOME")
            os.environ["XDG_CONFIG_HOME"] = tmp
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = tb_profile.main([])
                printed = buf.getvalue().strip()
            finally:
                if old is None:
                    os.environ.pop("XDG_CONFIG_HOME", None)
                else:
                    os.environ["XDG_CONFIG_HOME"] = old
            self.assertEqual(rc, 0)
            self.assertEqual(printed, str(root / "thunderbird" / "z.default-release"))


if __name__ == "__main__":
    unittest.main()
