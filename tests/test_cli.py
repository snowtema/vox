import argparse
import io
import json
import os
import signal
import subprocess
import time
import unittest
from pathlib import Path
from unittest import mock

from vox import cli, config, player
from tests.support import FakeEngine, IsolatedCase, run_main

LONG = "Слово. " * 120          # заведомо длиннее порога авторежима (600)


def assistant_entry(text: str) -> str:
    return json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})


class CliCase(IsolatedCase):
    def setUp(self):
        super().setUp()
        self.engine = FakeEngine()
        for patcher in (
            mock.patch("vox.cli.get", return_value=self.engine),
            mock.patch("vox.player.signal.signal"),      # не трогаем обработчики сигналов раннера
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def md(self, text: str, name: str = "doc.md") -> str:
        return str(self.write(name, text))


class CollectTest(CliCase):
    def parse(self, *argv: str) -> argparse.Namespace:
        return cli.build_parser().parse_args(list(argv))

    def test_files_are_joined_and_named(self):
        a, b = self.md("Первый", "a.md"), self.md("Второй", "b.md")
        self.assertEqual(cli.collect(self.parse(a, b)), ("Первый\n\nВторой", "a.md, b.md"))

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            cli.collect(self.parse(str(self.tmp / "нет.md")))

    def test_tilde_is_expanded(self):
        self.write("home/note.md", "Заметка")
        self.assertEqual(cli.collect(self.parse("~/note.md"))[0], "Заметка")

    def test_stdin(self):
        with mock.patch("sys.stdin", io.StringIO("текст из пайпа")):
            self.assertEqual(cli.collect(self.parse()), ("текст из пайпа", "stdin"))

    def test_explicit_transcript(self):
        path = self.write("t.jsonl", json.dumps({"type": "user", "message": {"content": "q"}}) + "\n"
                          + assistant_entry("Ответ из транскрипта") + "\n")
        text, source = cli.collect(self.parse("--transcript", str(path)))
        self.assertEqual((text, source), ("Ответ из транскрипта", "ответ Claude Code"))

    def test_last_flag_beats_files(self):
        path = self.write("t.jsonl", assistant_entry("из транскрипта") + "\n")
        doc = self.md("из файла")
        text, _ = cli.collect(self.parse("--last", "--transcript", str(path), doc))
        self.assertEqual(text, "из транскрипта")

    def test_empty_stdin_falls_back_to_transcript_and_reports_absence(self):
        with mock.patch("sys.stdin", io.StringIO("  \n")):
            with self.assertRaises(FileNotFoundError):
                cli.collect(self.parse())

    def test_transcript_with_only_tool_calls(self):
        entry = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "x"}]}}
        path = self.write("t.jsonl", json.dumps(entry) + "\n")
        with self.assertRaises(ValueError):
            cli.collect(self.parse("--transcript", str(path)))


class SpeakTest(CliCase):
    def test_dry_run_prints_normalized_text_and_does_not_speak(self):
        doc = self.md("# Заголовок\n\nЗапусти pnpm.")
        rc, out, _ = run_main([doc, "--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("Заголовок.", out)
        self.assertIn("пи эн пи эм", out)
        self.assertEqual(self.engine.spoken, [])

    def test_speaks_and_announces_source(self):
        doc = self.md("Привет, мир.")
        rc, out, _ = run_main([doc])
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.engine.spoken), 1)
        text, cfg, lang = self.engine.spoken[0]
        self.assertEqual((text, lang), ("Привет, мир.", "ru"))
        self.assertIn("doc.md", out)
        self.assertIn("vox stop", out)

    def test_quiet_suppresses_banner(self):
        _, out, _ = run_main([self.md("Привет."), "--quiet"])
        self.assertEqual(out, "")

    def test_english_document_uses_en(self):
        run_main([self.md("Hello there, this is a fairly long English sentence.")])
        self.assertEqual(self.engine.spoken[0][2], "en")

    def test_engine_prepare_is_applied(self):
        with mock.patch.object(FakeEngine, "prepare", lambda self, t: t.upper()):
            run_main([self.md("тихо.")])
        self.assertEqual(self.engine.spoken[0][0], "ТИХО.")

    def test_unavailable_engine_is_reported(self):
        self.engine._available = (False, "нужен пакет")
        rc, _, err = run_main([self.md("Текст.")])
        self.assertEqual(rc, 1)
        self.assertIn("fake: нужен пакет", err)
        self.assertEqual(self.engine.spoken, [])

    def test_out_writes_file_instead_of_speaking(self):
        rc, out, _ = run_main([self.md("Текст."), "--out", "речь.wav"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.engine.files, [("Текст.", "речь.wav")])
        self.assertEqual(self.engine.spoken, [])
        self.assertIn("записано в речь.wav", out)

    def test_nothing_left_after_cleanup(self):
        rc, _, err = run_main([self.md("***\n" * 10)])
        self.assertEqual(rc, 1)
        self.assertIn("читать нечего", err)

    def test_missing_file_is_a_clean_error(self):
        rc, _, err = run_main([str(self.tmp / "нет.md")])
        self.assertEqual(rc, 1)
        self.assertIn("vox:", err)

    def test_unknown_engine_in_config(self):
        self.write("config/vox/config.toml", 'engine = "nope"\n')
        with mock.patch("vox.cli.get", side_effect=cli.EngineError("неизвестный движок «nope»")):
            rc, _, err = run_main([self.md("Текст.")])
        self.assertEqual(rc, 1)
        self.assertIn("неизвестный движок", err)

    def test_engine_flag_rejects_unknown_names(self):
        with self.assertRaises(SystemExit) as ctx, mock.patch("sys.stderr", io.StringIO()):
            run_main(["--engine", "nope", self.md("Текст.")])
        self.assertEqual(ctx.exception.code, 2)

    def test_engine_error_during_speech_is_reported_and_slot_released(self):
        def boom(*args):
            raise cli.EngineError("синтез упал")

        with mock.patch.object(FakeEngine, "speak", side_effect=boom):
            rc, _, err = run_main([self.md("Текст.")])
        self.assertEqual(rc, 1)
        self.assertIn("синтез упал", err)
        self.assertFalse(player.pid_file().exists())

    def test_slot_is_released_after_speech(self):
        run_main([self.md("Текст.")])
        self.assertFalse(player.pid_file().exists())

    def test_max_chars_from_config_is_respected(self):
        self.write("config/vox/config.toml", "[text]\nmax_chars = 30\n")
        run_main([self.md("Слово " * 50)])
        self.assertTrue(self.engine.spoken[0][0].endswith("дальше пропущено."))

    def test_code_blocks_mode_from_config(self):
        self.write("config/vox/config.toml", '[text]\ncode_blocks = "skip"\n')
        run_main([self.md("До.\n\n```py\nprint(1)\n```\n\nПосле.")])
        self.assertNotIn("Далее код", self.engine.spoken[0][0])


class OverridesTest(CliCase):
    def test_rate_volume_voice_for_say(self):
        run_main([self.md("Текст."), "--rate", "150", "--volume", "0.5", "--voice", "Yuri"])
        cfg = self.engine.spoken[0][1]
        self.assertEqual((cfg.rate, cfg.volume, cfg.say.voice), (150, 0.5, "Yuri"))
        self.assertEqual(cfg.silero.voice, "aidar")

    def test_voice_goes_to_silero_when_engine_is_silero(self):
        run_main([self.md("Текст."), "--engine", "silero", "--voice", "aidar"])
        cfg = self.engine.spoken[0][1]
        self.assertEqual(cfg.silero.voice, "aidar")
        self.assertEqual(cfg.say.voice, "Milena")

    def test_voice_follows_engine_from_config(self):
        self.write("config/vox/config.toml", 'engine = "silero"\n')
        run_main([self.md("Текст."), "--voice", "xenia"])
        self.assertEqual(self.engine.spoken[0][1].silero.voice, "xenia")

    def test_zero_volume_is_a_valid_override(self):
        run_main([self.md("Текст."), "--volume", "0"])
        self.assertEqual(self.engine.spoken[0][1].volume, 0.0)


class AutoModeTest(CliCase):
    def auto(self, text: str) -> int:
        rc, out, err = run_main([self.md(text), "--auto", "--quiet"])
        self.assertEqual((out, err), ("", ""))          # хук обязан молчать
        return rc

    def test_long_text_is_spoken(self):
        self.assertEqual(self.auto(LONG), 0)
        self.assertEqual(len(self.engine.spoken), 1)

    def test_short_text_is_skipped(self):
        self.assertEqual(self.auto("Коротко."), 0)
        self.assertEqual(self.engine.spoken, [])

    def test_threshold_comes_from_config(self):
        self.write("config/vox/config.toml", "min_chars = 5\n")
        self.auto("Длиннее пяти.")
        self.assertEqual(len(self.engine.spoken), 1)

    def test_muted(self):
        player.set_muted(True)
        self.assertEqual(self.auto(LONG), 0)
        self.assertEqual(self.engine.spoken, [])

    def test_disabled_in_config(self):
        self.write("config/vox/config.toml", "auto = false\n")
        self.assertEqual(self.auto(LONG), 0)
        self.assertEqual(self.engine.spoken, [])

    def test_explicit_call_ignores_mute_and_threshold(self):
        player.set_muted(True)
        run_main([self.md("Коротко.")])
        self.assertEqual(len(self.engine.spoken), 1)

    def test_nothing_to_read_is_not_an_error_in_auto_mode(self):
        rc, out, err = run_main([self.md("***\n" * 200), "--auto", "--quiet"])
        self.assertEqual((rc, out, err), (0, "", ""))
        self.assertEqual(self.engine.spoken, [])


class SubcommandsTest(CliCase):
    def test_stop_with_nothing_playing(self):
        rc, out, _ = run_main(["stop"])
        self.assertEqual(rc, 0)
        self.assertIn("ничего не читается", out)

    def test_stop_interrupts_speaker(self):
        proc = subprocess.Popen(["sleep", "60"])
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        player.pid_file().write_text(str(proc.pid))
        _, out, _ = run_main(["stop"])
        self.assertIn("остановлено", out)
        self.assertEqual(proc.wait(timeout=10), -signal.SIGTERM)

    def test_on_off(self):
        _, out, _ = run_main(["off"])
        self.assertTrue(player.is_muted())
        self.assertIn("выключен", out)
        _, out, _ = run_main(["on"])
        self.assertFalse(player.is_muted())
        self.assertIn("включён", out)

    def test_detach_flag_is_ignored_by_subcommands(self):
        rc, out, _ = run_main(["stop", "--detach"])
        self.assertEqual(rc, 0)
        self.assertIn("vox:", out)

    def test_status(self):
        rc, out, _ = run_main(["status"])
        self.assertEqual(rc, 0)
        for label in ("движок", "голос", "темп", "авторежим", "порог", "сейчас", "silero"):
            self.assertIn(label, out)
        self.assertIn("включён", out)
        self.assertIn("тишина", out)

    def test_status_reflects_mute_and_unavailable_engine(self):
        player.set_muted(True)
        self.engine._available = (False, "не готов")
        _, out, _ = run_main(["status"])
        self.assertIn("vox on", out)
        self.assertIn("не готов", out)

    def test_status_shows_current_speaker(self):
        proc = subprocess.Popen(["sleep", "60"])
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        player.pid_file().write_text(str(proc.pid))
        _, out, _ = run_main(["status"])
        self.assertIn(f"pid {proc.pid}", out)

    def test_setup_rejects_unknown_target(self):
        rc, _, err = run_main(["setup", "piper"])
        self.assertEqual(rc, 1)
        self.assertIn("нечего ставить", err)

    def test_setup_silero_runs_installer_and_reports_failure(self):
        with mock.patch("vox.cli.SileroEngine") as silero:
            rc, _, _ = run_main(["setup", "silero"])
            silero.return_value.setup.assert_called_once()
            self.assertEqual(rc, 0)
            silero.return_value.setup.side_effect = cli.EngineError("нужен uv")
            rc, _, err = run_main(["setup"])
        self.assertEqual(rc, 1)
        self.assertIn("нужен uv", err)

    def test_config_opens_editor(self):
        with mock.patch.dict(os.environ, {"EDITOR": "nano"}), \
                mock.patch("vox.cli.subprocess.run") as run:
            run_main(["config"])
        self.assertEqual(run.call_args.args[0],
                         ["nano", str(config.config_dir() / "config.toml")])
        self.assertTrue((config.config_dir() / "config.toml").exists())

    def test_config_falls_back_to_open(self):
        env = {k: v for k, v in os.environ.items() if k != "EDITOR"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("vox.cli.subprocess.run") as run:
            run_main(["config"])
        self.assertEqual(run.call_args.args[0][:2], ["open", "-t"])

    def test_doctor_all_good(self):
        transcript = self.write("claude/projects/p/s.jsonl",
                                json.dumps({"cwd": str(Path.cwd().resolve())}) + "\n")
        with mock.patch("vox.cli.shutil.which", return_value="/usr/bin/ffmpeg"):
            rc, out, _ = run_main(["doctor"])
        self.assertEqual(rc, 0)
        self.assertNotIn("✗", out)
        self.assertIn(str(transcript), out)

    def test_doctor_fails_without_transcript_or_engine(self):
        rc, out, _ = run_main(["doctor"])
        self.assertEqual(rc, 1)
        self.assertIn("✗  транскрипт Claude Code", out)

        self.engine._available = (False, "нет say")
        _, out, _ = run_main(["doctor"])
        self.assertIn("✗  движок say — нет say", out)

    def test_doctor_ffmpeg_is_optional_but_reported(self):
        self.write("claude/projects/p/s.jsonl", json.dumps({"cwd": str(Path.cwd().resolve())}) + "\n")
        with mock.patch("vox.cli.shutil.which", return_value=None):
            rc, out, _ = run_main(["doctor"])
        self.assertEqual(rc, 0)
        self.assertIn("·  ffmpeg (для --out с silero) — не найден", out)
        with mock.patch("vox.cli.shutil.which", return_value="/usr/bin/ffmpeg"):
            _, out, _ = run_main(["doctor"])
        self.assertIn("✓  ffmpeg", out)

    def test_doctor_treats_silero_as_optional(self):
        self.write("claude/projects/p/s.jsonl", json.dumps({"cwd": str(Path.cwd().resolve())}) + "\n")
        real = {"say": FakeEngine(), "silero": FakeEngine((False, "не установлен"))}
        with mock.patch("vox.cli.get", side_effect=lambda name: real[name]):
            rc, out, _ = run_main(["doctor"])
        self.assertEqual(rc, 0)
        self.assertIn("·  движок silero — не установлен", out)


class DetachTest(CliCase):
    def test_detach_respawns_without_flag_in_new_session(self):
        doc = self.md("Текст.")
        with mock.patch("vox.cli.subprocess.Popen") as popen:
            rc, out, _ = run_main([doc, "--detach", "--rate", "180"])
        self.assertEqual(rc, 0)
        self.assertIn("читаю в фоне", out)
        cmd = popen.call_args.args[0]
        self.assertTrue(cmd[0].endswith(os.path.join("bin", "vox")))
        self.assertEqual(cmd[1:], [doc, "--rate", "180"])
        kwargs = popen.call_args.kwargs
        self.assertTrue(kwargs["start_new_session"])
        for stream in ("stdin", "stdout", "stderr"):
            self.assertEqual(kwargs[stream], subprocess.DEVNULL)
        self.assertEqual(self.engine.spoken, [])            # сам процесс ничего не читает

    def test_short_flag(self):
        with mock.patch("vox.cli.subprocess.Popen") as popen:
            run_main([self.md("Текст."), "-d"])
        self.assertNotIn("-d", popen.call_args.args[0])

    def test_stdin_is_materialized_for_the_child(self):
        with mock.patch("vox.cli.subprocess.Popen") as popen:
            run_main(["--detach"], stdin="Прочти это")
        cmd = popen.call_args.args[0]
        self.assertEqual(cmd[-1], "--delete-input")         # ребёнок сам уберёт за собой
        tmp_file = Path(cmd[-2])
        self.assertEqual(tmp_file.parent, config.cache_dir())
        self.assertEqual(tmp_file.read_text(encoding="utf-8"), "Прочти это")

    def test_empty_stdin_means_last_answer(self):
        with mock.patch("vox.cli.subprocess.Popen") as popen:
            run_main(["--detach"], stdin="")
        self.assertEqual(popen.call_args.args[0][1:], [])

    def test_failed_launch_removes_temp_file_and_reports(self):
        with mock.patch("vox.cli.subprocess.Popen", side_effect=OSError("нет прав")):
            rc, _, err = run_main(["--detach"], stdin="Прочти это")
        self.assertEqual(rc, 1)
        self.assertIn("нет прав", err)
        self.assertEqual(list(config.cache_dir().glob("stdin-*.md")), [])

    def test_stale_temp_files_are_swept_on_detach(self):
        cache = config.cache_dir()
        old, fresh, other = cache / "stdin-1.md", cache / "stdin-2.md", cache / "keep.md"
        for path in (old, fresh, other):
            path.write_text("x")
        two_days_ago = time.time() - 2 * 24 * 3600
        os.utime(old, (two_days_ago, two_days_ago))
        os.utime(other, (two_days_ago, two_days_ago))
        with mock.patch("vox.cli.subprocess.Popen"):
            run_main([self.md("Текст."), "--detach"])
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())
        self.assertTrue(other.exists())             # чужие файлы не трогаем

    def test_stdin_not_consumed_when_source_is_explicit(self):
        doc = self.md("Текст.")
        with mock.patch("vox.cli.subprocess.Popen") as popen:
            run_main([doc, "--detach"], stdin="лишнее")
        self.assertEqual(popen.call_args.args[0][1:], [doc])


class DeleteInputTest(CliCase):
    def test_input_is_deleted_after_speaking(self):
        doc = self.md("Текст.")
        run_main([doc, "--delete-input", "--quiet"])
        self.assertEqual(len(self.engine.spoken), 1)
        self.assertFalse(Path(doc).exists())

    def test_input_is_deleted_even_when_there_is_nothing_to_read(self):
        doc = self.md("***\n" * 10)
        rc, _, _ = run_main([doc, "--delete-input"])
        self.assertEqual(rc, 1)
        self.assertFalse(Path(doc).exists())

    def test_input_is_deleted_on_dry_run_and_when_auto_mode_skips_it(self):
        for extra in (["--dry-run"], ["--auto"]):
            with self.subTest(extra=extra):
                doc = self.md("Коротко.")
                run_main([doc, "--delete-input", *extra])
                self.assertFalse(Path(doc).exists())

    def test_without_the_flag_user_files_are_never_deleted(self):
        doc = self.md("Текст.")
        run_main([doc])
        self.assertTrue(Path(doc).exists())

    def test_flag_is_hidden_from_help(self):
        self.assertNotIn("--delete-input", cli.build_parser().format_help())


class AnyDirTest(CliCase):
    def test_no_transcript_for_directory_is_an_error_with_hint(self):
        self.write("claude/projects/p/s.jsonl",
                   json.dumps({"cwd": "/другой/проект"}) + "\n" + assistant_entry("Чужой ответ") + "\n")
        rc, _, err = run_main(["--last"])
        self.assertEqual(rc, 1)
        self.assertIn("для этой директории не найден", err)
        self.assertIn("--any-dir", err)
        self.assertEqual(self.engine.spoken, [])

    def test_any_dir_takes_newest_transcript_from_any_project(self):
        self.write("claude/projects/p/s.jsonl",
                   json.dumps({"cwd": "/другой/проект"}) + "\n" + assistant_entry("Чужой ответ") + "\n")
        rc, _, _ = run_main(["--last", "--any-dir"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.engine.spoken[0][0], "Чужой ответ.")

    def test_own_directory_is_found_without_the_flag(self):
        self.write("claude/projects/p/s.jsonl",
                   json.dumps({"cwd": str(Path.cwd().resolve())}) + "\n"
                   + assistant_entry("Свой ответ") + "\n")
        run_main(["--last"])
        self.assertEqual(self.engine.spoken[0][0], "Свой ответ.")

    def test_explicit_transcript_error_has_no_any_dir_hint(self):
        rc, _, err = run_main(["--transcript", str(self.tmp / "нет.jsonl")])
        self.assertEqual(rc, 1)
        self.assertNotIn("--any-dir", err)


class ParserTest(unittest.TestCase):
    def test_defaults(self):
        args = cli.build_parser().parse_args([])
        self.assertEqual(args.files, [])
        self.assertIsNone(args.engine)
        self.assertIsNone(args.rate)
        for flag in ("last", "turn", "dry_run", "auto", "quiet", "detach"):
            self.assertFalse(getattr(args, flag), flag)

    def test_short_flags(self):
        args = cli.build_parser().parse_args(
            ["-l", "-n", "-q", "-d", "-e", "silero", "-r", "170", "-v", "kseniya", "-o", "x.wav"])
        self.assertTrue(args.last and args.dry_run and args.quiet and args.detach)
        self.assertEqual((args.engine, args.rate, args.voice, args.out),
                         ("silero", 170, "kseniya", "x.wav"))

    def test_subcommand_names(self):
        self.assertEqual(cli.SUBCOMMANDS,
                         {"stop", "on", "off", "status", "setup", "config", "doctor"})


if __name__ == "__main__":
    unittest.main()
