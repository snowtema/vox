"""Управление воспроизведением: один голос за раз, мгновенная остановка.

Новая озвучка прерывает предыдущую — иначе при авторежиме ответы Claude Code
наложились бы друг на друга. Текущий процесс vox отмечается pid-файлом,
`vox stop` шлёт ему SIGTERM, а обработчик сигнала убивает дочерний say/afplay.
"""

import errno
import os
import signal
import subprocess
from pathlib import Path

from .config import state_dir

_children: list[subprocess.Popen] = []


def pid_file() -> Path:
    return state_dir() / "speaking.pid"


def mute_file() -> Path:
    return state_dir() / "muted"


# ── авторежим ─────────────────────────────────────────────────────────────────

def is_muted() -> bool:
    return mute_file().exists()


def set_muted(value: bool) -> None:
    if value:
        mute_file().touch()
    else:
        mute_file().unlink(missing_ok=True)


# ── текущее воспроизведение ───────────────────────────────────────────────────

def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError as exc:
        return exc.errno == errno.EPERM
    return True


def current_pid() -> int | None:
    try:
        pid = int(pid_file().read_text().strip())
    except (OSError, ValueError):
        return None
    return pid if pid != os.getpid() and _alive(pid) else None


def stop() -> bool:
    """Прерывает чужую озвучку. True, если было что прерывать."""
    pid = current_pid()
    if pid is None:
        pid_file().unlink(missing_ok=True)
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    pid_file().unlink(missing_ok=True)
    return True


def _kill_children() -> None:
    for proc in _children:
        if proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
    _children.clear()


def _on_signal(signum, _frame):
    _kill_children()
    pid_file().unlink(missing_ok=True)
    raise SystemExit(130 if signum == signal.SIGINT else 143)


def track(proc: subprocess.Popen) -> None:
    """Колбэк для движков: запомнить процесс, чтобы уметь его прервать."""
    _children.append(proc)


def claim() -> None:
    """Забирает слот воспроизведения: глушит предыдущую озвучку."""
    stop()
    pid_file().write_text(str(os.getpid()))
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(sig, _on_signal)
        except (ValueError, OSError):
            pass       # не главный поток — не критично


def release() -> None:
    _kill_children()
    try:
        if pid_file().read_text().strip() == str(os.getpid()):
            pid_file().unlink(missing_ok=True)
    except OSError:
        pass


def estimate_seconds(text: str, rate: int) -> int:
    """Грубая оценка длительности: rate — слов в минуту, слово ≈ 7 символов."""
    return max(1, round(len(text) * 60 / max(60, rate * 7)))


def fmt_duration(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"
