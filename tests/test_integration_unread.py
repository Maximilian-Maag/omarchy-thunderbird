"""Integration test: the unread backend wired to the profile finder.

The unit tests drive the scanner with an explicit profile. Here the two shipped tools
run together: ``omarchy-thunderbird-unread`` with no ``--profile`` must locate the
profile through ``omarchy-tb-profile`` (using XDG_CONFIG_HOME) and count the mail in
it. This is the seam a regression in either tool would slip through.
"""

import json
import os
import pathlib
import subprocess
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
UNREAD = REPO / "bin/omarchy-thunderbird-unread"

MBOX = (
    "From a@example.com Thu Jan  1 00:00:00 2026\n"
    "X-Mozilla-Status: 0000\nSubject: fresh\n\none\n\n"
    "From b@example.com Thu Jan  1 00:00:00 2026\n"
    "X-Mozilla-Status: 0001\nSubject: read\n\ntwo\n\n"
)


class UnreadIntegrationCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        profile = self.root / "thunderbird" / "abc.default-release"
        (profile / "Mail" / "Local Folders").mkdir(parents=True)
        (self.root / "thunderbird" / "profiles.ini").write_text(
            "[Profile0]\nName=default\nPath=abc.default-release\nDefault=1\nIsRelative=1\n")
        (profile / "Mail" / "Local Folders" / "Inbox").write_text(MBOX)
        self.profile = profile

    def tearDown(self):
        self._tmp.cleanup()

    def run_unread(self, *args):
        env = dict(os.environ, XDG_CONFIG_HOME=str(self.root))
        return subprocess.run(["python3", str(UNREAD), *args], env=env,
                              capture_output=True, text=True)

    def test_counts_via_the_profile_finder(self):
        result = self.run_unread()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "1")

    def test_json_via_the_profile_finder(self):
        result = self.run_unread("--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["unread"], 1)
        self.assertEqual(data["folders"]["Mail/Local Folders/Inbox"],
                         {"total": 2, "unread": 1})


if __name__ == "__main__":
    unittest.main()
