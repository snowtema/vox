"""Извлечение последнего ответа Claude Code из JSONL-транскрипта.

Транскрипты лежат в ~/.claude/projects/<slug>/<session>.jsonl, по одной
JSON-записи на строку. Финальный текст ответа — последняя серия блоков
type="text" подряд идущих assistant-записей.
"""

import json
import os
import re
from pathlib import Path

SCAN_LIMIT = 200      # сколько самых свежих транскриптов просматривать


def projects_dir() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude")
    return Path(base) / "projects"


def _slug(cwd: str) -> str:
    """Имя папки проекта, как его строит Claude Code: всё, кроме букв и цифр, -> «-»."""
    return re.sub(r"[^A-Za-z0-9]", "-", cwd)


def _first_cwd(path: Path) -> str | None:
    """cwd из первой записи транскрипта, где он указан."""
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if '"cwd"' not in line:
                    continue
                try:
                    return json.loads(line).get("cwd")
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return None


TAIL_BYTES = 64 * 1024


def _last_cwd(path: Path) -> str | None:
    """cwd из самой свежей записи: читаем только хвост, транскрипты бывают большими."""
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - TAIL_BYTES))
            tail = fh.read().decode("utf-8", errors="ignore")
    except OSError:
        return None
    for line in reversed(tail.splitlines()):
        if '"cwd"' not in line:
            continue
        try:
            return json.loads(line).get("cwd")
        except json.JSONDecodeError:
            continue          # первая строка хвоста может быть обрезана
    return None


def find_transcript(cwd: str | None = None, *, fallback: bool = False) -> Path | None:
    """Свежий транскрипт для указанной рабочей директории.

    Основной признак — поле cwd внутри записей: правило преобразования пути в
    имя папки недокументировано и может меняться. Сессия могла сменить cwd
    после старта, поэтому сверяем и первый, и последний cwd в файле, а имя
    папки проекта используем как запасной признак.

    Если для директории ничего не нашлось, по умолчанию возвращается None:
    молча озвучить ответ из чужого проекта хуже, чем честно сказать об ошибке.
    fallback=True разрешает взять самый свежий транскрипт из любого проекта.
    """
    cwd = str(Path(cwd or os.getcwd()).resolve())
    root = projects_dir()
    if not root.is_dir():
        return None

    candidates = sorted(root.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    slug = _slug(cwd)
    for path in candidates[:SCAN_LIMIT]:
        if path.parent.name == slug or cwd in (_first_cwd(path), _last_cwd(path)):
            return path
    return candidates[0] if fallback and candidates else None


def _text_blocks(entry: dict) -> list[str]:
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []
    return [
        b["text"]
        for b in content
        if isinstance(b, dict) and b.get("type") == "text" and b.get("text")
    ]


def _has_tool_use(entry: dict) -> bool:
    content = entry.get("message", {}).get("content")
    return isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_use" for b in content
    )


def _is_tool_result(entry: dict) -> bool:
    content = entry.get("message", {}).get("content")
    return isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
    )


def last_assistant_text(path: Path, whole_turn: bool = False) -> str:
    """Финальный текст ответа (по умолчанию) или вся проза последнего хода.

    Блоки thinking и вывод сабагентов (isSidechain) не читаются.
    """
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""

    parts: list[str] = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("isSidechain"):
            continue

        kind = entry.get("type")
        if kind == "assistant":
            blocks = _text_blocks(entry)
            if blocks:
                parts = blocks + parts
            elif _has_tool_use(entry) and parts and not whole_turn:
                break          # дошли до инструментов — финальный ответ собран
        elif kind == "user":
            if _is_tool_result(entry):
                continue       # это часть того же хода ассистента
            break              # настоящая реплика пользователя — граница хода

    return "\n\n".join(p.strip() for p in parts if p.strip())
