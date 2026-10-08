"""Regression test: a no-op policy run is not a failure.

Pins db77452 + f35b206: before them, the pre-commit hook and CI treated "nothing
changed against the base" as a policy failure, so a clean commit was blocked for
having nothing to check. The checker must exit 0 when there is genuinely nothing
to look at, and must keep reporting zero failures in CI mode.
"""
import pathlib
import subprocess
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent


def run_policy(*args):
    return subprocess.run([sys.executable, "tools/policy_check.py", *args],
                          cwd=str(REPO), capture_output=True, text=True)


class NoopRunCase(unittest.TestCase):
    def test_changed_with_nothing_to_check_exits_zero(self):
        proc = run_policy("--changed")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("0 failed", proc.stdout)

    def test_ci_mode_reports_zero_failures(self):
        proc = run_policy("--ci")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("0 failed", proc.stdout)


if __name__ == "__main__":
    unittest.main()
