"""Извлечение последнего ответа Claude Code из JSONL-транскрипта.

Транскрипты лежат в ~/.claude/projects/<slug>/<session>.jsonl, по одной
JSON-записи на строку. Финальный текст ответа — последняя серия блоков
type="text" подряд идущих assistant-записей.
"""

import json
import os
from pathlib import Path


def projects_dir() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude")
    return Path(base) / "projects"


def find_transcript(cwd: str | None = None) -> Path | None:
    """Свежий транскрипт для указанной рабочей директории.

    Матчим по полю cwd внутри записей, а не по имени папки: правило
    преобразования пути в slug недокументировано и может меняться.
    """
    cwd = str(Path(cwd or os.getcwd()).resolve())
    root = projects_dir()
    if not root.is_dir():
        return None

    candidates = sorted(root.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    newest = None
    for path in candidates[:60]:
        try:
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    if '"cwd"' not in line:
                        continue
                    try:
                        entry_cwd = json.loads(line).get("cwd")
                    except json.JSONDecodeError:
                        continue
                    if entry_cwd == cwd:
                        return path
                    break
        except OSError:
            continue
        newest = newest or path
    return newest


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
