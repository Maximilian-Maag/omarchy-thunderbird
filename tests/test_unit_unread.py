"""Unit tests for bin/omarchy-thunderbird-unread.

The read-state rule is the heart of this tool: Thunderbird's mbox ``X-Mozilla-Status``
low bit is the Read flag, so a message is unread when that bit is clear. The parser,
the per-file counter and the profile scanner are each pinned here against synthetic
mbox files, which is also what makes the file a mutation target.
"""

import importlib.machinery
import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock

REPO = pathlib.Path(__file__).resolve().parent.parent
UNREAD_PATH = REPO / "bin/omarchy-thunderbird-unread"


def load_module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    try:
        loader.exec_module(module)
    except SystemExit as exc:
        # A tool whose ``if __name__ == "__main__"`` guard is broken would run
        # sys.exit() during import. Left uncaught that exits the whole test process
        # with status 0 — a silent, green outcome. Turn it into a hard test failure.
        raise ImportError("%s exited at import (%r)" % (name, exc)) from exc
    return module


unread = load_module("tb_unread", UNREAD_PATH)


def mbox(*statuses):
    """A minimal mbox body: one message per status value (hex string)."""
    parts = []
    for i, status in enumerate(statuses):
        parts.append(
            "From sender%d@example.com Thu Jan  1 00:00:00 2026\n"
            "X-Mozilla-Status: %s\n"
            "X-Mozilla-Status2: 00000000\n"
            "Subject: message %d\n\n"
            "body\n\n" % (i, status, i))
    return "".join(parts)


class StatusCase(unittest.TestCase):
    def test_read_flag_set_means_read(self):
        self.assertTrue(unread.status_is_read("0001"))
        self.assertTrue(unread.status_is_read("0009"))

    def test_clear_read_flag_means_unread(self):
        self.assertFalse(unread.status_is_read("0000"))
        self.assertFalse(unread.status_is_read("0008"))

    def test_hex_base_is_sixteen_not_a_higher_radix(self):
        # 0x10 -> low bit clear -> unread. Read as base 17 it would be 17 (odd),
        # which would wrongly report the message as read.
        self.assertFalse(unread.status_is_read("0010"))
        # 0x11 -> low bit set -> read, in either radix.
        self.assertTrue(unread.status_is_read("0011"))

    def test_unparseable_status_counts_as_unread(self):
        self.assertFalse(unread.status_is_read("zzzz"))


class CountFileCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_counts_total_and_unread(self):
        path = self.dir / "Inbox"
        path.write_text(mbox("0000", "0001", "0000", "0001", "0000"))
        self.assertEqual(unread.count_file(path), (5, 3))

    def test_all_read_gives_zero_unread(self):
        path = self.dir / "Inbox"
        path.write_text(mbox("0001", "0001"))
        self.assertEqual(unread.count_file(path), (2, 0))

    def test_missing_file_is_zero(self):
        self.assertEqual(unread.count_file(self.dir / "nope"), (0, 0))


class ScanCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.profile = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel, text):
        path = self.profile / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_scan_collects_mbox_stores_and_skips_msf(self):
        self.write("Mail/Local Folders/Inbox", mbox("0000", "0000"))
        self.write("Mail/Local Folders/Sent", mbox("0001"))
        # A .msf summary is not a message store; even when it happens to contain a
        # status-like line it must be skipped, so the fixture carries one on purpose.
        self.write("Mail/Local Folders/Inbox.msf", mbox("0000", "0000", "0000"))
        self.write("ImapMail/imap.example/INBOX", mbox("0000", "0001"))
        folders = unread.scan_profile(self.profile)
        self.assertEqual(folders["Mail/Local Folders/Inbox"], (2, 2))
        self.assertEqual(folders["Mail/Local Folders/Sent"], (1, 0))
        self.assertEqual(folders["ImapMail/imap.example/INBOX"], (2, 1))
        self.assertNotIn("Mail/Local Folders/Inbox.msf", folders)

    def test_suffixed_files_are_not_treated_as_stores(self):
        self.write("Mail/Local Folders/Inbox", mbox("0000"))
        for name in ("Inbox.msf", "panacea.dat", "history.sqlite", "x.ini", "y.json"):
            self.write("Mail/Local Folders/" + name, mbox("0000"))
        folders = unread.scan_profile(self.profile)
        self.assertEqual(sorted(folders), ["Mail/Local Folders/Inbox"])

    def test_empty_profile_has_no_folders(self):
        (self.profile / "Mail").mkdir()
        self.assertEqual(unread.scan_profile(self.profile), {})


class MainCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.profile = pathlib.Path(self._tmp.name)
        (self.profile / "Mail" / "Local Folders").mkdir(parents=True)
        (self.profile / "Mail" / "Local Folders" / "Inbox").write_text(
            mbox("0000", "0000", "0001"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_default_prints_the_integer(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = unread.main(["--profile", str(self.profile)])
        self.assertEqual(rc, 0)
        self.assertEqual(buf.getvalue().strip(), "2")

    def test_json_lists_folders(self):
        import contextlib
        import io
        import json
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = unread.main(["--profile", str(self.profile), "--json"])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["unread"], 2)
        self.assertEqual(data["folders"]["Mail/Local Folders/Inbox"],
                         {"total": 3, "unread": 2})

    def test_missing_profile_exits_1(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = unread.main(["--profile", str(self.profile / "ghost")])
        self.assertEqual(rc, 1)


class ResolveProfileCase(unittest.TestCase):
    """resolve_profile parses the finder's subprocess result; pin its contract."""

    def fake_run(self, returncode, stdout, record=None):
        def run(cmd, **kwargs):
            if record is not None:
                record["kwargs"] = kwargs
            return mock.Mock(returncode=returncode, stdout=stdout)
        return mock.patch.object(unread.subprocess, "run", run)

    def test_explicit_path_bypasses_the_finder(self):
        with mock.patch.object(unread.subprocess, "run") as run:
            self.assertEqual(unread.resolve_profile("/tmp/abc"), pathlib.Path("/tmp/abc"))
            run.assert_not_called()

    def test_normalises_whitespace_from_stdout(self):
        with self.fake_run(0, "/var/tmp/thunderbird/abc.default-release\n"):
            self.assertEqual(unread.resolve_profile(None),
                             pathlib.Path("/var/tmp/thunderbird/abc.default-release"))

    def test_finder_is_called_in_text_mode_with_captured_output(self):
        record = {}
        with self.fake_run(0, "/x\n", record):
            unread.resolve_profile(None)
        self.assertIs(record["kwargs"]["capture_output"], True)
        self.assertIs(record["kwargs"]["text"], True)

    def test_nonzero_returncode_yields_none_even_with_output(self):
        with self.fake_run(1, "/x\n"):
            self.assertIsNone(unread.resolve_profile(None))

    def test_empty_stdout_yields_none(self):
        with self.fake_run(0, "   \n"):
            self.assertIsNone(unread.resolve_profile(None))


if __name__ == "__main__":
    unittest.main()
