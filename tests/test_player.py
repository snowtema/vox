import os
import signal
import subprocess
import sys
import unittest
from unittest import mock

from vox import player
from tests.support import IsolatedCase


def sleeper() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])


class MuteTest(IsolatedCase):
    def test_toggle(self):
        self.assertFalse(player.is_muted())
        player.set_muted(True)
        self.assertTrue(player.is_muted())
        player.set_muted(True)                       # идемпотентно
        player.set_muted(False)
        self.assertFalse(player.is_muted())
        player.set_muted(False)


class CurrentPidTest(IsolatedCase):
    def test_no_file(self):
        self.assertIsNone(player.current_pid())

    def test_garbage_in_file(self):
        player.pid_file().write_text("не число")
        self.assertIsNone(player.current_pid())

    def test_own_pid_is_not_foreign(self):
        player.pid_file().write_text(str(os.getpid()))
        self.assertIsNone(player.current_pid())

    def test_dead_process(self):
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        player.pid_file().write_text(str(proc.pid))
        self.assertIsNone(player.current_pid())

    def test_live_process(self):
        proc = sleeper()
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        player.pid_file().write_text(str(proc.pid))
        self.assertEqual(player.current_pid(), proc.pid)


class StopTest(IsolatedCase):
    def test_nothing_to_stop(self):
        self.assertFalse(player.stop())

    def test_stale_pid_file_is_cleaned(self):
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        player.pid_file().write_text(str(proc.pid))
        self.assertFalse(player.stop())
        self.assertFalse(player.pid_file().exists())

    def test_terminates_running_process(self):
        proc = sleeper()
        self.addCleanup(proc.kill)
        player.pid_file().write_text(str(proc.pid))
        self.assertTrue(player.stop())
        self.assertEqual(proc.wait(timeout=10), -signal.SIGTERM)
        self.assertFalse(player.pid_file().exists())


class ClaimReleaseTest(IsolatedCase):
    def setUp(self):
        super().setUp()
        player._children.clear()
        self.addCleanup(player._children.clear)

    def test_claim_writes_own_pid_and_installs_handlers(self):
        with mock.patch("vox.player.signal.signal") as sig:
            player.claim()
        self.assertEqual(player.pid_file().read_text(), str(os.getpid()))
        self.assertEqual({c.args[0] for c in sig.call_args_list},
                         {signal.SIGTERM, signal.SIGINT, signal.SIGHUP})

    def test_claim_silences_previous_speaker(self):
        proc = sleeper()
        self.addCleanup(proc.kill)
        player.pid_file().write_text(str(proc.pid))
        with mock.patch("vox.player.signal.signal"):
            player.claim()
        self.assertEqual(proc.wait(timeout=10), -signal.SIGTERM)

    def test_claim_survives_non_main_thread(self):
        with mock.patch("vox.player.signal.signal", side_effect=ValueError):
            player.claim()                                 # не должно падать

    def test_release_kills_tracked_children_and_frees_slot(self):
        proc = sleeper()
        self.addCleanup(proc.kill)
        player.track(proc)
        player.pid_file().write_text(str(os.getpid()))
        player.release()
        self.assertEqual(proc.wait(timeout=10), -signal.SIGKILL)
        self.assertFalse(player.pid_file().exists())

    def test_release_keeps_foreign_pid_file(self):
        player.pid_file().write_text("1")
        player.release()
        self.assertEqual(player.pid_file().read_text(), "1")

    def test_signal_handler_kills_children_and_exits(self):
        for signum, code in ((signal.SIGTERM, 143), (signal.SIGINT, 130)):
            with self.subTest(signum=signum):
                proc = sleeper()
                self.addCleanup(proc.kill)
                player.track(proc)
                player.pid_file().write_text(str(os.getpid()))
                with self.assertRaises(SystemExit) as ctx:
                    player._on_signal(signum, None)
                self.assertEqual(ctx.exception.code, code)
                proc.wait(timeout=10)
                self.assertFalse(player.pid_file().exists())


class DurationTest(unittest.TestCase):
    def test_estimate(self):
        self.assertEqual(player.estimate_seconds("х" * 1400, 200), 60)
        self.assertEqual(player.estimate_seconds("х" * 700, 200), 30)
        self.assertEqual(player.estimate_seconds("", 200), 1)

    def test_estimate_guards_against_tiny_rate(self):
        self.assertGreaterEqual(player.estimate_seconds("х" * 100, 0), 1)

    def test_format(self):
        self.assertEqual(player.fmt_duration(5), "0:05")
        self.assertEqual(player.fmt_duration(65), "1:05")
        self.assertEqual(player.fmt_duration(600), "10:00")


if __name__ == "__main__":
    unittest.main()
