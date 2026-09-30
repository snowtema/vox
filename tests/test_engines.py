import io
import json
import os
import subprocess
import sys
import textwrap
import types
import unittest
from unittest import mock

from vox import config
from vox.engines import ENGINES, EngineError, SayEngine, SileroEngine, get
from vox.engines import silero as silero_mod
from tests.support import IsolatedCase


class RegistryTest(unittest.TestCase):
    def test_get_returns_instances(self):
        self.assertIsInstance(get("say"), SayEngine)
        self.assertIsInstance(get("silero"), SileroEngine)
        self.assertEqual(set(ENGINES), {"say", "silero"})

    def test_unknown_engine(self):
        with self.assertRaises(EngineError) as ctx:
            get("nope")
        self.assertIn("неизвестный движок «nope»", str(ctx.exception))
        self.assertIn("say", str(ctx.exception))


# ── say ───────────────────────────────────────────────────────────────────────

class SayEngineTest(unittest.TestCase):
    def setUp(self):
        self.engine = SayEngine()
        self.cfg = config.Config()

    def test_available_requires_say_binary(self):
        with mock.patch("shutil.which", return_value=None):
            ok, hint = self.engine.available()
        self.assertFalse(ok)
        self.assertIn("say", hint)
        with mock.patch("shutil.which", return_value="/usr/bin/say"):
            self.assertEqual(self.engine.available(), (True, ""))

    def test_prepare_strips_stress_marks_only(self):
        self.assertEqual(self.engine.prepare("кл+од и к+од"), "клод и код")
        self.assertEqual(self.engine.prepare("два + два"), "два + два")

    def test_script_has_volume_and_pauses_between_paragraphs(self):
        script = self.engine._script("Раз.\n\nДва.\n\nТри.", self.cfg)
        self.assertEqual(script, "[[volm 0.90]] Раз. [[slnc 380]] Два. [[slnc 380]] Три.")

    def test_script_uses_configured_pause_and_clamps_volume(self):
        self.cfg.pause_ms, self.cfg.volume = 100, 7
        self.assertEqual(self.engine._script("А.\n\nБ.", self.cfg),
                         "[[volm 1.00]] А. [[slnc 100]] Б.")
        self.cfg.volume, self.cfg.pause_ms = -1, -50
        self.assertEqual(self.engine._script("А.\n\nБ.", self.cfg),
                         "[[volm 0.00]] А. [[slnc 0]] Б.")

    def test_script_neutralizes_square_brackets(self):
        script = self.engine._script("Массив [1, 2] тут.", self.cfg)
        self.assertNotIn("[1", script)
        self.assertIn("(1, 2)", script)

    def test_pick_voice_by_language(self):
        with mock.patch.object(SayEngine, "voices", return_value={"Milena", "Samantha", "Yuri"}):
            self.assertEqual(self.engine.pick_voice(self.cfg, "ru"), "Milena")
            self.assertEqual(self.engine.pick_voice(self.cfg, "en"), "Samantha")
            self.cfg.say.voice = "Yuri"
            self.assertEqual(self.engine.pick_voice(self.cfg, "ru"), "Yuri")

    def test_pick_voice_falls_back_when_not_installed(self):
        self.cfg.say.voice = "Удалённый"
        with mock.patch.object(SayEngine, "voices", return_value={"Milena", "Samantha"}):
            with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                self.assertEqual(self.engine.pick_voice(self.cfg, "ru"), "Milena")
        self.assertIn("не установлен", out.getvalue())

    def test_pick_voice_trusts_config_when_voice_list_unavailable(self):
        self.cfg.say.voice = "Custom"
        with mock.patch.object(SayEngine, "voices", return_value=set()):
            self.assertEqual(self.engine.pick_voice(self.cfg, "ru"), "Custom")

    def test_voices_parses_say_output(self):
        fake = types.SimpleNamespace(stdout="Milena   ru_RU  # Привет\nSamantha en_US # Hi\n\n")
        with mock.patch("subprocess.run", return_value=fake):
            self.assertEqual(self.engine.voices(), {"Milena", "Samantha"})
        with mock.patch("subprocess.run", side_effect=OSError):
            self.assertEqual(self.engine.voices(), set())

    def test_speak_pipes_script_to_say_and_reports_child(self):
        proc = mock.Mock()
        seen = []
        with mock.patch.object(SayEngine, "voices", return_value={"Milena"}), \
                mock.patch("subprocess.Popen", return_value=proc) as popen:
            self.engine.speak("Раз.\n\nДва.", self.cfg, "ru", seen.append)
        cmd = popen.call_args.args[0]
        self.assertEqual(cmd, ["say", "-v", "Milena", "-r", "200"])
        self.assertEqual(seen, [proc])
        sent = proc.communicate.call_args.args[0].decode()
        self.assertEqual(sent, "[[volm 0.90]] Раз. [[slnc 380]] Два.")

    def test_speak_survives_broken_pipe_after_stop(self):
        proc = mock.Mock()
        proc.communicate.side_effect = BrokenPipeError
        with mock.patch.object(SayEngine, "voices", return_value={"Milena"}), \
                mock.patch("subprocess.Popen", return_value=proc):
            self.engine.speak("Текст.", self.cfg, "ru", lambda p: None)

    def test_speak_reports_launch_failure(self):
        with mock.patch.object(SayEngine, "voices", return_value={"Milena"}), \
                mock.patch("subprocess.Popen", side_effect=OSError("нет say")):
            with self.assertRaises(EngineError):
                self.engine.speak("Текст.", self.cfg, "ru", lambda p: None)

    def test_to_file(self):
        done = types.SimpleNamespace(returncode=0, stderr=b"")
        with mock.patch.object(SayEngine, "voices", return_value={"Milena"}), \
                mock.patch("subprocess.run", return_value=done) as run:
            self.assertEqual(self.engine.to_file("Текст.", "out.wav", self.cfg, "ru"), "out.wav")
        cmd = run.call_args.args[0]
        self.assertIn("-o", cmd)
        self.assertEqual(cmd[cmd.index("-o") + 1], "out.wav")

    def test_to_file_failure_carries_stderr(self):
        failed = types.SimpleNamespace(returncode=1, stderr="плохой формат".encode())
        with mock.patch.object(SayEngine, "voices", return_value={"Milena"}), \
                mock.patch("subprocess.run", return_value=failed):
            with self.assertRaises(EngineError) as ctx:
                self.engine.to_file("Текст.", "out.wav", self.cfg, "ru")
        self.assertIn("плохой формат", str(ctx.exception))


# ── silero ────────────────────────────────────────────────────────────────────

# Подменяет настоящий воркер: тот же JSON-протокол, но без torch.
FAKE_WORKER = textwrap.dedent('''\
    import json, sys
    log = sys.argv[1]
    sys.stdout.write(json.dumps({"ready": True}) + "\\n"); sys.stdout.flush()
    for line in sys.stdin:
        req = json.loads(line)
        with open(log, "a") as fh:
            fh.write(req["text"] + "\\n")
        if "FAIL" in req["text"]:
            resp = {"error": "RuntimeError: boom"}
        else:
            open(req["out"], "w").write(req["text"])
            resp = {"ok": True, "path": req["out"]}
        sys.stdout.write(json.dumps(resp) + "\\n"); sys.stdout.flush()
''')


class FakePlayer:
    def __init__(self, cmd, code=0):
        self.cmd, self.code = cmd, code

    def wait(self):
        return self.code


class SileroEngineTest(IsolatedCase):
    def setUp(self):
        super().setUp()
        self.engine = SileroEngine()
        self.cfg = config.Config()
        self.log = self.tmp / "requests.log"
        self.worker = self.write("fake_worker.py", FAKE_WORKER)
        self.spawned: list[tuple] = []
        real_popen = subprocess.Popen
        self.real_popen = real_popen

        self.workers: list[subprocess.Popen] = []
        self.addCleanup(self.reap_workers)

        def spawn(engine_self, speaker, sample_rate, accent):
            self.spawned.append((speaker, sample_rate, accent))
            proc = real_popen(
                [sys.executable, str(self.worker), str(self.log)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, bufsize=1,
            )
            self.workers.append(proc)
            return proc

        patcher = mock.patch.object(SileroEngine, "_spawn_worker", spawn)
        patcher.start()
        self.addCleanup(patcher.stop)

    def reap_workers(self):
        """Движок делает terminate() без wait() — дожимаем сами, чтобы не копить зомби."""
        for proc in self.workers:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)
            for pipe in (proc.stdin, proc.stdout):
                if pipe and not pipe.closed:
                    try:
                        pipe.close()
                    except OSError:
                        pass

    def requested(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []

    def patch_afplay(self, code=0):
        calls = []
        real = self.real_popen

        def popen(cmd, *args, **kwargs):
            if cmd[0] == "afplay":
                calls.append(cmd)
                return FakePlayer(cmd, code)
            return real(cmd, *args, **kwargs)

        return calls, mock.patch("subprocess.Popen", side_effect=popen)

    # available / setup

    def test_available_reports_missing_venv_then_missing_model(self):
        ok, hint = self.engine.available()
        self.assertFalse(ok)
        self.assertIn("vox setup silero", hint)

        silero_mod.venv_python().parent.mkdir(parents=True)
        silero_mod.venv_python().touch()
        ok, hint = self.engine.available()
        self.assertFalse(ok)
        self.assertIn("модель не скачана", hint)

        silero_mod.model_path().touch()
        self.assertEqual(self.engine.available(), (True, ""))

    def test_setup_requires_uv(self):
        with mock.patch("vox.engines.silero.shutil.which", return_value=None):
            with self.assertRaises(EngineError) as ctx:
                self.engine.setup()
        self.assertIn("uv", str(ctx.exception))

    def test_paths_live_in_cache_dir(self):
        self.assertEqual(silero_mod.model_path().parent, self.tmp / "cache" / "vox" / "silero")
        self.assertTrue(silero_mod.worker_script().name == "silero_worker.py")
        self.assertTrue(silero_mod.worker_script().exists())

    # prepare / voices

    def test_prepare_expands_numbers(self):
        self.assertEqual(self.engine.prepare("Прошло 12 строк."), "Прошло двенадцать строк.")

    def test_unknown_speaker_falls_back_to_baya(self):
        self.cfg.silero.voice = "robot"
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(self.engine._speaker(self.cfg), "baya")
        self.assertIn("robot", out.getvalue())
        self.cfg.silero.voice = "aidar"
        self.assertEqual(self.engine._speaker(self.cfg), "aidar")

    # handshake

    def test_await_ready_accepts_ready(self):
        proc = types.SimpleNamespace(stdout=io.StringIO('{"ready": true}\n'))
        self.engine._await_ready(proc)

    def test_await_ready_rejects_dead_worker_garbage_and_not_ready(self):
        for line in ("", "мусор\n", '{"ready": false}\n', '{"x": 1}\n'):
            with self.subTest(line=line):
                proc = types.SimpleNamespace(stdout=io.StringIO(line))
                with self.assertRaises(EngineError):
                    self.engine._await_ready(proc)

    # speak

    def test_speak_plays_every_chunk_in_order_with_paragraph_pauses(self):
        calls, patch_popen = self.patch_afplay()
        seen = []
        self.cfg.volume = 0.5
        with patch_popen, mock.patch("vox.engines.silero.time.sleep") as sleep:
            self.engine.speak("Один.\n\nДва.\n\nТри.\n\nЧетыре.\n\nПять.",
                              self.cfg, "ru", seen.append)

        self.assertEqual(self.requested(), ["Один.", "Два.", "Три.", "Четыре.", "Пять."])
        self.assertEqual([c[-1].rsplit("/", 1)[1] for c in calls],
                         ["0.wav", "1.wav", "2.wav", "3.wav", "4.wav"])
        self.assertTrue(all(c[:3] == ["afplay", "-v", "0.50"] for c in calls))
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [0.38] * 4)
        self.assertEqual(len(seen), 1 + 5)           # воркер + пять проигрывателей
        self.assertEqual(self.spawned, [("baya", 48000, True)])

    def test_speak_passes_voice_and_accent_settings_to_worker(self):
        calls, patch_popen = self.patch_afplay()
        self.cfg.silero.voice, self.cfg.silero.sample_rate = "xenia", 24000
        self.cfg.silero.put_accent = False
        with patch_popen, mock.patch("vox.engines.silero.time.sleep"):
            self.engine.speak("Текст.", self.cfg, "ru", lambda p: None)
        self.assertEqual(self.spawned, [("xenia", 24000, False)])

    def test_speak_cleans_up_temp_files_and_worker(self):
        calls, patch_popen = self.patch_afplay()
        seen = []
        with patch_popen, mock.patch("vox.engines.silero.time.sleep"):
            self.engine.speak("Текст.", self.cfg, "ru", seen.append)
        worker = seen[0]
        worker.wait(timeout=10)
        self.assertIsNotNone(worker.poll())
        wav_dir = os.path.dirname(calls[0][-1])
        self.assertFalse(os.path.exists(wav_dir))

    def test_speak_empty_text_does_nothing(self):
        self.engine.speak("   ", self.cfg, "ru", lambda p: None)
        self.assertEqual(self.spawned, [])

    def test_speak_raises_when_synthesis_fails(self):
        calls, patch_popen = self.patch_afplay()
        with patch_popen, mock.patch("vox.engines.silero.time.sleep"):
            with self.assertRaises(EngineError) as ctx:
                self.engine.speak("Хорошо.\n\nFAIL тут.", self.cfg, "ru", lambda p: None)
        self.assertIn("кусок 2", str(ctx.exception))
        self.assertIn("boom", str(ctx.exception))
        self.assertEqual(len(calls), 1)               # первый кусок успел прозвучать

    def test_speak_raises_when_player_fails(self):
        calls, patch_popen = self.patch_afplay(code=1)
        with patch_popen, mock.patch("vox.engines.silero.time.sleep"):
            with self.assertRaises(EngineError) as ctx:
                self.engine.speak("Текст.", self.cfg, "ru", lambda p: None)
        self.assertIn("afplay", str(ctx.exception))

    # to_file

    def test_to_file_concatenates_chunks_with_ffmpeg(self):
        captured = {}

        def run(cmd, **kwargs):
            captured["cmd"] = cmd
            listfile = cmd[cmd.index("-i") + 1]
            with open(listfile, encoding="utf-8") as fh:
                captured["list"] = fh.read()
            return types.SimpleNamespace(returncode=0, stderr=b"")

        with mock.patch("subprocess.run", side_effect=run):
            result = self.engine.to_file("Раз.\n\nДва.", str(self.tmp / "out.wav"), self.cfg, "ru")

        self.assertEqual(result, str(self.tmp / "out.wav"))
        self.assertEqual(self.requested(), ["Раз.", "Два."])
        self.assertEqual(captured["cmd"][0], "ffmpeg")
        self.assertEqual(captured["list"].count("file '"), 2)
        self.assertEqual(captured["cmd"][-1], str(self.tmp / "out.wav"))

    def test_to_file_reports_ffmpeg_failure(self):
        bad = types.SimpleNamespace(returncode=1, stderr="ffmpeg сломан".encode())
        with mock.patch("subprocess.run", return_value=bad):
            with self.assertRaises(EngineError) as ctx:
                self.engine.to_file("Текст.", str(self.tmp / "o.wav"), self.cfg, "ru")
        self.assertIn("ffmpeg сломан", str(ctx.exception))

    def test_to_file_reports_synthesis_failure(self):
        with self.assertRaises(EngineError):
            self.engine.to_file("FAIL.", str(self.tmp / "o.wav"), self.cfg, "ru")

    def test_to_file_nothing_to_synthesize(self):
        with self.assertRaises(EngineError):
            self.engine.to_file("  ", str(self.tmp / "o.wav"), self.cfg, "ru")


if __name__ == "__main__":
    unittest.main()
