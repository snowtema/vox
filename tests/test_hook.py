import importlib.util
import io
import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from tests.support import IsolatedCase, ROOT

spec = importlib.util.spec_from_file_location("stop_speak", ROOT / "hooks" / "stop-speak.py")
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class StopHookTest(IsolatedCase):
    def run_hook(self, payload, *, popen_side_effect=None):
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        with mock.patch("sys.stdin", io.StringIO(raw)), \
                mock.patch.object(hook.subprocess, "Popen", side_effect=popen_side_effect) as popen:
            rc = hook.main()
        return rc, popen

    def test_launches_vox_detached_with_auto_flags(self):
        rc, popen = self.run_hook({"transcript_path": "/t/x.jsonl", "cwd": "/work"})
        self.assertEqual(rc, 0)
        cmd = popen.call_args.args[0]
        self.assertEqual(cmd[0], str(ROOT / "bin" / "vox"))
        self.assertEqual(cmd[1:], ["--last", "--auto", "--quiet", "--transcript", "/t/x.jsonl"])
        kwargs = popen.call_args.kwargs
        self.assertEqual(kwargs["cwd"], "/work")
        self.assertTrue(kwargs["start_new_session"])
        for stream in ("stdin", "stdout", "stderr"):
            self.assertEqual(kwargs[stream], subprocess.DEVNULL)

    def test_without_transcript_path_vox_finds_it_itself(self):
        _, popen = self.run_hook({"cwd": "/work"})
        self.assertNotIn("--transcript", popen.call_args.args[0])

    def test_missing_cwd_becomes_none(self):
        _, popen = self.run_hook({})
        self.assertIsNone(popen.call_args.kwargs["cwd"])

    def test_reentrant_stop_hook_does_nothing(self):
        rc, popen = self.run_hook({"stop_hook_active": True, "transcript_path": "/t"})
        self.assertEqual(rc, 0)
        popen.assert_not_called()

    def test_garbage_stdin_is_not_an_error(self):
        for raw in ("", "не json", "{"):
            with self.subTest(raw=raw):
                rc, popen = self.run_hook(raw)
                self.assertEqual(rc, 0)
                popen.assert_not_called()

    def test_spawn_failure_must_not_break_claude_code(self):
        rc, _ = self.run_hook({"cwd": "/w"}, popen_side_effect=OSError("нет прав"))
        self.assertEqual(rc, 0)

    def test_plugin_root_env_is_preferred(self):
        plugin = self.tmp / "plugin"
        (plugin / "bin").mkdir(parents=True)
        (plugin / "bin" / "vox").write_text("#!/bin/sh\n")
        with mock.patch.dict("os.environ", {"CLAUDE_PLUGIN_ROOT": str(plugin)}):
            _, popen = self.run_hook({"cwd": "/w"})
        self.assertEqual(popen.call_args.args[0][0], str(plugin / "bin" / "vox"))

    def test_missing_binary_is_silently_skipped(self):
        with mock.patch.dict("os.environ", {"CLAUDE_PLUGIN_ROOT": str(self.tmp / "empty")}):
            rc, popen = self.run_hook({"cwd": "/w"})
        self.assertEqual(rc, 0)
        popen.assert_not_called()

    def test_hook_returns_quickly_without_waiting_for_vox(self):
        # Popen не должен вызываться с wait/communicate: хук обязан вернуться мгновенно
        proc = mock.Mock()
        rc, _ = self.run_hook({"cwd": "/w"}, popen_side_effect=lambda *a, **k: proc)
        self.assertEqual(rc, 0)
        self.assertEqual(proc.method_calls, [])


if __name__ == "__main__":
    unittest.main()
