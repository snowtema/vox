#!/usr/bin/env python3
"""Stop-хук: озвучивает длинный ответ Claude Code.

Хук обязан возвращать управление мгновенно — Claude Code ждёт его завершения.
Поэтому здесь только запуск vox в отдельной сессии; все решения (выключен ли
авторежим, достаточно ли длинный ответ) принимает сам vox по флагу --auto.
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    if payload.get("stop_hook_active"):
        return 0

    root = os.environ.get("CLAUDE_PLUGIN_ROOT") or str(Path(__file__).resolve().parents[1])
    vox = Path(root) / "bin" / "vox"
    if not vox.exists():
        return 0

    cmd = [str(vox), "--last", "--auto", "--quiet"]
    if transcript := payload.get("transcript_path"):
        cmd += ["--transcript", transcript]

    try:
        subprocess.Popen(
            cmd,
            cwd=payload.get("cwd") or None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        pass          # озвучка не должна ломать работу Claude Code
    return 0


if __name__ == "__main__":
    sys.exit(main())
