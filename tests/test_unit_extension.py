"""Unit tests for the guard extension's manifest and bin/omarchy-thunderbird-xpi.

The extension's security logic lives in guard-engine.js (tested by the js kind). This
covers the packaging around it: the manifest Thunderbird must accept, and the xpi the
build tool produces and installs.
"""

import importlib.machinery
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

REPO = pathlib.Path(__file__).resolve().parent.parent
EXT = REPO / "extension"
XPI_PATH = REPO / "bin/omarchy-thunderbird-xpi"
GECKO_ID = "guard@omarchy-thunderbird.maximilian-maag"


def load_module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    try:
        loader.exec_module(module)
    except SystemExit as exc:
        raise ImportError("%s exited at import (%r)" % (name, exc)) from exc
    return module


xpi = load_module("tb_xpi", XPI_PATH)


class ManifestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((EXT / "manifest.json").read_text())

    def test_required_keys_present(self):
        for key in ("manifest_version", "name", "version", "background"):
            self.assertIn(key, self.manifest)

    def test_gecko_id_matches_the_install_filename(self):
        self.assertEqual(xpi.extension_id(self.manifest), GECKO_ID)

    def test_background_loads_rules_then_engine_then_background(self):
        scripts = self.manifest["background"]["scripts"]
        self.assertEqual(scripts, ["guard-rules.js", "guard-engine.js", "background.js"])
        for name in scripts:
            self.assertTrue((EXT / name).is_file(), "missing %s" % name)

    def test_requests_the_mail_permissions_it_uses(self):
        for perm in ("messagesRead", "messagesModify", "storage", "notifications"):
            self.assertIn(perm, self.manifest["permissions"])


class BuildCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self._tmp.name) / "guard.xpi"

    def tearDown(self):
        self._tmp.cleanup()

    def test_xpi_contains_the_extension_files(self):
        xpi.build_xpi(EXT, self.out)
        with zipfile.ZipFile(self.out) as archive:
            names = archive.namelist()
        self.assertIn("manifest.json", names)
        self.assertIn("guard-engine.js", names)
        self.assertIn("guard-rules.js", names)
        self.assertIn("background.js", names)

    def test_manifest_in_the_xpi_parses_and_has_the_id(self):
        xpi.build_xpi(EXT, self.out)
        with zipfile.ZipFile(self.out) as archive:
            manifest = json.loads(archive.read("manifest.json"))
        self.assertEqual(xpi.extension_id(manifest), GECKO_ID)

    def test_build_is_byte_identical_across_runs(self):
        first = pathlib.Path(self._tmp.name) / "a.xpi"
        second = pathlib.Path(self._tmp.name) / "b.xpi"
        xpi.build_xpi(EXT, first)
        xpi.build_xpi(EXT, second)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_entries_use_the_fixed_timestamp(self):
        # The archive is reproducible only because every entry carries the fixed zip
        # epoch timestamp, not the build time.
        xpi.build_xpi(EXT, self.out)
        with zipfile.ZipFile(self.out) as archive:
            for info in archive.infolist():
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0), info.filename)

    def test_files_to_pack_excludes_directories(self):
        (EXT / "subdir").exists()
        names = [p.name for p in xpi.files_to_pack(EXT)]
        self.assertIn("manifest.json", names)
        self.assertTrue(all(p.is_file() for p in xpi.files_to_pack(EXT)))

    def test_build_creates_missing_parent_directories(self):
        nested = pathlib.Path(self._tmp.name) / "deep" / "nested" / "guard.xpi"
        xpi.build_xpi(EXT, nested)
        self.assertTrue(nested.is_file())

    def test_missing_manifest_key_is_rejected(self):
        broken = pathlib.Path(self._tmp.name) / "ext"
        broken.mkdir()
        (broken / "manifest.json").write_text('{"name": "x"}')
        with self.assertRaises(ValueError):
            xpi.build_xpi(broken, self.out)


class InstallCase(unittest.TestCase):
    def test_install_copies_xpi_into_the_profile_extensions_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            profile = root / "thunderbird" / "abc.default-release"
            profile.mkdir(parents=True)
            (root / "thunderbird" / "profiles.ini").write_text(
                "[Profile0]\nName=default\nPath=abc.default-release\nDefault=1\nIsRelative=1\n")
            out = root / "guard.xpi"
            env = dict(os.environ, XDG_CONFIG_HOME=str(root))
            result = subprocess.run(
                [sys.executable, str(XPI_PATH), "--install", "--out", str(out)],
                env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            dest = profile / "extensions" / ("%s.xpi" % GECKO_ID)
            self.assertTrue(dest.is_file(), "xpi not installed into the profile")
            with zipfile.ZipFile(dest) as archive:
                self.assertIn("manifest.json", archive.namelist())


class ResolveProfileCase(unittest.TestCase):
    def fake_run(self, returncode, stdout):
        return mock.patch.object(xpi.subprocess, "run",
                                 lambda cmd, **kw: mock.Mock(returncode=returncode, stdout=stdout))

    def test_explicit_path_bypasses_the_finder(self):
        with mock.patch.object(xpi.subprocess, "run") as run:
            self.assertEqual(xpi.resolve_profile("/tmp/p"), pathlib.Path("/tmp/p"))
            run.assert_not_called()

    def test_finder_result_is_parsed(self):
        with self.fake_run(0, "/var/tmp/tb/abc\n"):
            self.assertEqual(xpi.resolve_profile(None), pathlib.Path("/var/tmp/tb/abc"))

    def test_nonzero_returncode_yields_none(self):
        with self.fake_run(1, "/var/tmp/tb/abc\n"):
            self.assertIsNone(xpi.resolve_profile(None))

    def test_empty_stdout_yields_none(self):
        with self.fake_run(0, "  \n"):
            self.assertIsNone(xpi.resolve_profile(None))


if __name__ == "__main__":
    unittest.main()
