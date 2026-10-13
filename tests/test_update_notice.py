"""0.1.36: a newer client is mentioned on stderr at most once a day, never on stdout."""
import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from ekbasis import client as C


class TestUpdateNotice(unittest.TestCase):
    def run_notice(self, latest, home, env=None):
        err, out = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"HOME": home, **(env or {})}), redirect_stderr(err), redirect_stdout(out):
            C._maybe_notice_update(latest)
        return err.getvalue(), out.getvalue()

    def test_newer_once_a_day(self):
        home = tempfile.mkdtemp()
        err, out = self.run_notice("99.0.0", home)
        self.assertIn("99.0.0 is available", err)
        self.assertEqual(out, "")
        err2, _ = self.run_notice("99.0.0", home)
        self.assertEqual(err2, "")   # already told today

    def test_same_or_older_or_off_or_garbage(self):
        home = tempfile.mkdtemp()
        self.assertEqual(self.run_notice(C.__version__, home)[0], "")
        self.assertEqual(self.run_notice("0.0.1", home)[0], "")
        self.assertEqual(self.run_notice("99.0.0", home, {"EKBASIS_NO_UPDATE_CHECK": "1"})[0], "")
        self.assertEqual(self.run_notice("not-a-version", home)[0], "")
        self.assertEqual(self.run_notice(None, home)[0], "")
