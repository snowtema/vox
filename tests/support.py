"""Общая обвязка: изолированное окружение и поддельный движок."""

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vox import lexicon
from vox.engines.base import Engine

ROOT = Path(__file__).resolve().parents[1]


class IsolatedCase(unittest.TestCase):
    """Каждый тест живёт в своём XDG/HOME и не трогает реальный конфиг и состояние."""

    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        env = {
            "XDG_CONFIG_HOME": str(self.tmp / "config"),
            "XDG_STATE_HOME": str(self.tmp / "state"),
            "XDG_CACHE_HOME": str(self.tmp / "cache"),
            "CLAUDE_CONFIG_DIR": str(self.tmp / "claude"),
            "HOME": str(self.tmp / "home"),
        }
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        # add_terms мутирует глобальный словарь — возвращаем как было
        terms = mock.patch.dict(lexicon.TERMS)
        terms.start()
        self.addCleanup(terms.stop)

    def write(self, name: str, content: str) -> Path:
        path = self.tmp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path


class FakeEngine(Engine):
    """Запоминает вызовы вместо синтеза речи."""

    name = "fake"

    def __init__(self, available: tuple[bool, str] = (True, "")):
        self._available = available
        self.spoken: list[tuple[str, object, str]] = []
        self.files: list[tuple[str, str]] = []

    def available(self):
        return self._available

    def speak(self, text, cfg, lang, on_child):
        self.spoken.append((text, cfg, lang))

    def to_file(self, text, out, cfg, lang):
        self.files.append((text, out))
        return out


def run_main(argv: list[str], stdin: str | None = None) -> tuple[int, str, str]:
    """Вызывает vox.cli.main и возвращает (код, stdout, stderr)."""
    from vox import cli

    out, err = io.StringIO(), io.StringIO()
    stack = contextlib.ExitStack()
    with stack:
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(err))
        if stdin is not None:
            stack.enter_context(mock.patch("sys.stdin", io.StringIO(stdin)))
        rc = cli.main(argv)
    return rc, out.getvalue(), err.getvalue()
