"""Точка входа vox."""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import config, player, textnorm, transcript
from .engines import ENGINES, EngineError, get
from .engines.silero import SileroEngine

SUBCOMMANDS = {"stop", "on", "off", "status", "setup", "config", "doctor"}


def _err(msg: str) -> int:
    print(f"vox: {msg}", file=sys.stderr)
    return 1


# ── сбор текста ───────────────────────────────────────────────────────────────

def _read_files(paths: list[str]) -> tuple[str, str]:
    blocks, names = [], []
    for raw in paths:
        path = Path(raw).expanduser()
        if not path.is_file():
            raise FileNotFoundError(raw)
        blocks.append(path.read_text(encoding="utf-8", errors="replace"))
        names.append(path.name)
    return "\n\n".join(blocks), ", ".join(names)


def _from_transcript(args) -> tuple[str, str]:
    path = (Path(args.transcript) if args.transcript
            else transcript.find_transcript(fallback=args.any_dir))
    if not path or not path.exists():
        hint = "" if args.transcript else " (--any-dir — взять самый свежий из любого проекта)"
        raise FileNotFoundError(f"транскрипт Claude Code для этой директории не найден{hint}")
    text = transcript.last_assistant_text(path, whole_turn=args.turn)
    if not text:
        raise ValueError("в последнем ответе Claude Code нет текста — только вызовы инструментов")
    return text, "ответ Claude Code"


def collect(args) -> tuple[str, str]:
    if args.last or args.turn or args.transcript:
        return _from_transcript(args)
    if args.files:
        return _read_files(args.files)
    if not sys.stdin.isatty():
        data = sys.stdin.read()
        if data.strip():
            return data, "stdin"
    # Без аргументов в интерактивном терминале самое ожидаемое — последний ответ
    return _from_transcript(args)


# ── подкоманды ────────────────────────────────────────────────────────────────

def cmd_stop() -> int:
    print("vox: остановлено" if player.stop() else "vox: сейчас ничего не читается")
    return 0


def cmd_toggle(on: bool) -> int:
    player.set_muted(not on)
    print(f"vox: авторежим {'включён' if on else 'выключен'}")
    return 0


def cmd_status(cfg: config.Config) -> int:
    engine = get(cfg.engine)
    ok, hint = engine.available()
    playing = player.current_pid()
    lines = [
        f"движок     {cfg.engine}" + ("" if ok else f"  ← {hint}"),
        f"голос      {cfg.say.voice if cfg.engine == 'say' else cfg.silero.voice}",
        f"темп       {cfg.rate} слов/мин",
        f"авторежим  {'выключен (vox on — включить)' if player.is_muted() else 'включён' if cfg.auto else 'выключен в конфиге'}",
        f"порог      {cfg.min_chars} символов",
        f"сейчас     {'читает (pid ' + str(playing) + ')' if playing else 'тишина'}",
        f"конфиг     {config.config_dir() / 'config.toml'}",
    ]
    silero_ok, silero_hint = SileroEngine().available()
    lines.append(f"silero     {'установлен' if silero_ok else silero_hint}")
    print("\n".join(lines))
    return 0


def cmd_setup(args) -> int:
    target = (args.files or ["silero"])[0]
    if target != "silero":
        return _err(f"нечего ставить: «{target}». Доступно: silero")
    try:
        SileroEngine().setup()
    except EngineError as exc:
        return _err(str(exc))
    return 0


def cmd_config() -> int:
    path = config.ensure_files() / "config.toml"
    editor = os.environ.get("EDITOR")
    subprocess.run([editor, str(path)] if editor else ["open", "-t", str(path)])
    return 0


def cmd_doctor(cfg: config.Config) -> int:
    say_ok, say_hint = get("say").available()
    path = transcript.find_transcript()
    required = [
        ("движок say", say_ok, say_hint),
        ("транскрипт Claude Code", path is not None,
         "не найден — запусти из папки проекта, где работает Claude Code"),
        ("конфиг", (config.config_dir() / "config.toml").exists(),
         "будет создан при первом запуске"),
    ]
    # Silero необязателен: его отсутствие — не поломка, а не начатая установка
    optional = [
        ("движок silero", *get("silero").available()),
        ("ffmpeg (для --out с silero)", bool(shutil.which("ffmpeg")),
         "не найден — `brew install ffmpeg`"),
    ]

    failed = 0
    for label, ok, hint in required:
        print(f"  {'✓' if ok else '✗'}  {label}" + ("" if ok else f" — {hint}"))
        failed += not ok
    for label, ok, hint in optional:
        print(f"  {'✓' if ok else '·'}  {label}" + ("" if ok else f" — {hint}"))
    if path:
        print(f"\n  транскрипт: {path}")
    return 0 if not failed else 1


# ── основной путь ─────────────────────────────────────────────────────────────

def _discard_inputs(paths: list[str]) -> None:
    for raw in paths:
        Path(raw).expanduser().unlink(missing_ok=True)


def run_speak(args, cfg: config.Config) -> int:
    try:
        raw, source = collect(args)
    except (FileNotFoundError, ValueError) as exc:
        return _err(str(exc))
    finally:
        # Временный файл от --detach нужен ровно до прочтения
        if args.delete_input:
            _discard_inputs(args.files)

    if args.auto:
        if player.is_muted() or not cfg.auto:
            return 0
        if len(raw) < cfg.min_chars:
            return 0

    text = textnorm.normalize(raw, cfg.text)
    if not text.strip():
        return 0 if args.auto else _err("после очистки текста не осталось — читать нечего")

    try:
        engine = get(args.engine or cfg.engine)
    except EngineError as exc:
        return _err(str(exc))
    text = engine.prepare(text)

    if args.dry_run:
        print(text)
        return 0

    lang = textnorm.detect_lang(raw)
    ok, hint = engine.available()
    if not ok:
        return _err(f"{engine.name}: {hint}")

    if args.out:
        try:
            path = engine.to_file(text, args.out, cfg, lang)
        except EngineError as exc:
            return _err(str(exc))
        print(f"vox: записано в {path}")
        return 0

    if not args.quiet:
        secs = player.estimate_seconds(text, cfg.rate)
        print(f"vox: {source} · {len(text)} симв. · ~{player.fmt_duration(secs)} · "
              f"{engine.name} · vox stop — прервать")

    player.claim()
    try:
        engine.speak(text, cfg, lang, player.track)
    except EngineError as exc:
        return _err(str(exc))
    finally:
        player.release()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="vox",
        description="Озвучка ответов Claude Code и markdown-файлов.",
        epilog=(
            "примеры:\n"
            "  vox --last              прочитать последний ответ Claude Code\n"
            "  vox README.md           прочитать файл\n"
            "  cat notes.md | vox      прочитать со stdin\n"
            "  vox --last --dry-run    показать, что будет прочитано\n"
            "  vox stop                прервать чтение\n"
            "  vox off / vox on        выключить / включить авторежим\n"
            "  vox setup silero        поставить движок получше\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("files", nargs="*", metavar="ФАЙЛ",
                   help="markdown- или текстовые файлы; без них читается stdin")
    p.add_argument("--last", "-l", action="store_true",
                   help="финальный текст последнего ответа Claude Code")
    p.add_argument("--turn", action="store_true",
                   help="весь последний ход, включая реплики между инструментами")
    p.add_argument("--transcript", metavar="ПУТЬ", help="конкретный файл транскрипта")
    p.add_argument("--engine", "-e", choices=sorted(ENGINES), help="движок синтеза")
    p.add_argument("--rate", "-r", type=int, metavar="N", help="темп, слов в минуту")
    p.add_argument("--volume", type=float, metavar="0..1", help="громкость")
    p.add_argument("--voice", "-v", metavar="ИМЯ", help="голос выбранного движка")
    p.add_argument("--out", "-o", metavar="ФАЙЛ", help="записать в аудиофайл вместо чтения")
    p.add_argument("--dry-run", "-n", action="store_true",
                   help="напечатать подготовленный текст и выйти")
    p.add_argument("--auto", action="store_true",
                   help="режим хука: молча выйти, если авторежим выключен или текст короткий")
    p.add_argument("--quiet", "-q", action="store_true", help="без служебных сообщений")
    p.add_argument("--detach", "-d", action="store_true",
                   help="читать в фоне и сразу вернуть управление")
    p.add_argument("--any-dir", action="store_true",
                   help="если для этой директории нет транскрипта — взять самый свежий из любого проекта")
    p.add_argument("--delete-input", action="store_true", help=argparse.SUPPRESS)
    return p


STALE_INPUT_SECONDS = 24 * 3600


def _sweep_stale_inputs() -> None:
    """Подчищает stdin-файлы, которые не удалил фоновый процесс (он мог не запуститься)."""
    cutoff = time.time() - STALE_INPUT_SECONDS
    for path in config.cache_dir().glob("stdin-*.md"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass


def detach(argv: list[str], args) -> int:
    """Перезапускает себя в отдельной сессии и выходит."""
    _sweep_stale_inputs()
    child = [a for a in argv if a not in ("--detach", "-d")]
    tmp: Path | None = None
    # stdin фоновому процессу не достанется — материализуем его во временный файл.
    # Пустой stdin (так бывает внутри слеш-команды) — не ошибка: фоновый vox
    # тогда прочтёт последний ответ, как и без аргументов в терминале.
    reads_stdin = not (args.files or args.last or args.turn or args.transcript)
    if reads_stdin and not sys.stdin.isatty():
        data = sys.stdin.read()
        if data.strip():
            tmp = Path(config.cache_dir()) / f"stdin-{os.getpid()}.md"
            tmp.write_text(data, encoding="utf-8")
            child += [str(tmp), "--delete-input"]

    exe = Path(__file__).resolve().parents[2] / "bin" / "vox"
    cmd = [str(exe), *child] if exe.exists() else [sys.executable, "-m", "vox", *child]
    try:
        subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )
    except OSError as exc:
        if tmp:
            tmp.unlink(missing_ok=True)
        return _err(f"не удалось запустить фоновое чтение: {exc}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    config.ensure_files()
    cfg = config.load()

    # Подкоманды мгновенные — --detach им не нужен (его приписывает /say ко всему)
    plain = [a for a in argv if a not in ("--detach", "-d")]
    if plain and plain[0] in SUBCOMMANDS:
        name, rest = plain[0], plain[1:]
        if name == "stop":
            return cmd_stop()
        if name in ("on", "off"):
            return cmd_toggle(name == "on")
        if name == "status":
            return cmd_status(cfg)
        if name == "config":
            return cmd_config()
        if name == "doctor":
            return cmd_doctor(cfg)
        if name == "setup":
            return cmd_setup(build_parser().parse_args(rest))

    args = build_parser().parse_args(argv)
    if args.detach:
        if detach(argv, args) != 0:
            return 1
        print("vox: читаю в фоне · vox stop — прервать")
        return 0
    if args.rate:
        cfg.rate = args.rate
    if args.volume is not None:
        cfg.volume = args.volume
    if args.voice:
        if (args.engine or cfg.engine) == "silero":
            cfg.silero.voice = args.voice
        else:
            cfg.say.voice = args.voice
    return run_speak(args, cfg)
