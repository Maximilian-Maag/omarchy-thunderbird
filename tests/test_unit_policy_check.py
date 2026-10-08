"""Unit tests: tools/policy_check.py, the policy engine this repository runs on.

The checker is what keeps the repository honest, so its own rules are pinned here:
a declared test kind with no tests, a mutation config with no targets or a weak
threshold, a source file neither mutated nor exempted, and a CI file that does not
run the suite must all FAIL. The rules are exercised against synthetic repositories
in a temp directory, so the real tree is never touched.
"""
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent


def load_checker():
    spec = importlib.util.spec_from_file_location("policy_check", REPO / "tools/policy_check.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["policy_check"] = mod
    spec.loader.exec_module(mod)
    return mod


class PolicyCheckCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pc = load_checker()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.write("tools/mutator.py", "x = 1\n")
        self.write("tools/run_tests.sh", "#!/bin/bash\necho hi\n")

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def spec(self, **over):
        base = {
            "kinds": ["unit"],
            "files": {},
            "runner": "tools/run_tests.sh",
            "mutator": "tools/mutator.py",
            "mutation_config": "tests/mutation.json",
            "ci": ".github/workflows/test.yml",
            "min_kill_rate": 0.80,
            "source_globs": ["bin/*"],
        }
        base.update(over)
        return base

    def mutation(self, rate=0.85, targets=None, exempt=None):
        data = {"min_kill_rate": rate,
                "targets": targets if targets is not None else
                [{"path": "bin/thing", "lang": "shell", "tests": ["true"]}]}
        if exempt is not None:
            data["exempt"] = exempt
        self.write("tests/mutation.json", json.dumps(data))
        self.write("bin/thing", "#!/bin/bash\necho x\n")
        self.write(".github/workflows/test.yml", "run: bash tools/run_tests.sh\n")
        self.write("tests/test_unit_a.py", "# t\n")

    def check(self, spec):
        rep = self.pc.Report()
        self.pc.check_tests(self.root, [], {"tests": spec}, rep)
        return rep

    @staticmethod
    def failures(rep):
        return {rule for status, rule, _ in rep.results if status == "FAIL"}

    # ── the small helpers ────────────────────────────────────────────────
    def test_report_tracks_failures(self):
        rep = self.pc.Report()
        rep.ok("a")
        rep.warn("b", "")
        self.assertFalse(rep.failed)
        rep.fail("c", "because")
        self.assertTrue(rep.failed)

    def test_sample_truncates_with_a_count(self):
        self.assertEqual(self.pc.sample(["a", "b", "c", "d"], 2), "a, b (+2 more)")

    def test_allowed_matches_exact_paths_and_globs(self):
        bucket = {"a.txt": "x", "docs/*.md": "y"}
        self.assertTrue(self.pc.allowed(bucket, "a.txt"))
        self.assertTrue(self.pc.allowed(bucket, "docs/readme.md"))
        self.assertFalse(self.pc.allowed(bucket, "docs/readme.rst"))

    # ── the test-kind and mutation rules ─────────────────────────────────
    def test_a_declared_kind_without_a_file_fails(self):
        self.mutation()
        rep = self.check(self.spec(kinds=["unit", "regression"]))
        self.assertIn("tests/regression-present", self.failures(rep))

    def test_a_complete_layout_passes(self):
        self.mutation()
        rep = self.check(self.spec())
        self.assertFalse(rep.failed, [r for r in rep.results if r[0] == "FAIL"])

    def test_no_mutation_targets_fails(self):
        self.mutation(targets=[])
        rep = self.check(self.spec())
        self.assertIn("tests/mutation-targets", self.failures(rep))

    def test_a_threshold_below_the_floor_fails(self):
        self.mutation(rate=0.50)
        rep = self.check(self.spec(min_kill_rate=0.80))
        self.assertIn("tests/mutation-threshold", self.failures(rep))

    def test_an_unaccounted_source_file_fails(self):
        self.mutation()
        self.write("bin/orphan", "#!/bin/bash\n")
        rep = self.check(self.spec())
        self.assertIn("tests/no-gaps", self.failures(rep))

    def test_an_exempt_entry_without_a_reason_fails(self):
        self.mutation(exempt=[{"path": "bin/thing"}])
        rep = self.check(self.spec())
        self.assertIn("tests/no-gaps", self.failures(rep))

    def test_ci_must_run_the_test_suite(self):
        self.mutation()
        self.write(".github/workflows/test.yml", "run: echo nope\n")
        rep = self.check(self.spec())
        self.assertIn("tests/ci-runs-suite", self.failures(rep))

    # ── the manifest rules ───────────────────────────────────────────────
    def test_manifest_version_must_match_the_changelog(self):
        self.write("manifest.json", json.dumps({
            "id": "a.b", "name": "n", "version": "1.2.0",
            "author": "x", "license": "MIT", "description": "d"}))
        self.write("CHANGELOG.md", "## [1.1.0] — 2026-01-01\n")
        rep = self.pc.Report()
        self.pc.check_manifest(self.root, [], {"plugin": True}, rep)
        self.assertIn("plugin/version-matches-changelog", self.failures(rep))

    def test_manifest_missing_required_keys_fails(self):
        self.write("manifest.json", json.dumps({"id": "a.b"}))
        self.write("CHANGELOG.md", "## [1.0.0] — 2026-01-01\n")
        rep = self.pc.Report()
        self.pc.check_manifest(self.root, [], {"plugin": True}, rep)
        self.assertIn("plugin/manifest-keys", self.failures(rep))


if __name__ == "__main__":
    unittest.main()
