"""Конфиг vox: ~/.config/vox/config.toml + пользовательский словарь."""

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

from . import lexicon


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "vox"


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state")
    d = Path(base) / "vox"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
    d = Path(base) / "vox"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class TextCfg:
    code_blocks: str = "announce"   # announce | skip | read
    tables: str = "announce"        # announce | skip | read
    latin: str = "dict+translit"    # dict+translit | dict | off
    max_chars: int = 6000


@dataclass
class SayCfg:
    voice: str = "Milena"
    voice_en: str = "Samantha"


@dataclass
class SileroCfg:
    voice: str = "aidar"            # aidar | baya | kseniya | xenia | eugene
    pitch: str = "medium"           # x-low | low | medium | high | x-high
    sample_rate: int = 48000        # 8000 | 24000 | 48000
    put_accent: bool = True


@dataclass
class Config:
    engine: str = "say"             # say | silero
    auto: bool = True               # озвучивать ответы Claude Code автоматически
    min_chars: int = 600            # порог «простыни» для авторежима
    rate: int = 200                 # темп речи, слов в минуту
    volume: float = 0.9
    pause_ms: int = 380             # пауза между абзацами
    text: TextCfg = field(default_factory=TextCfg)
    say: SayCfg = field(default_factory=SayCfg)
    silero: SileroCfg = field(default_factory=SileroCfg)


def _fill(obj, data: dict) -> None:
    known = {f.name: f.type for f in fields(obj)}
    for key, value in data.items():
        if key not in known:
            continue
        current = getattr(obj, key)
        if hasattr(current, "__dataclass_fields__") and isinstance(value, dict):
            _fill(current, value)
        else:
            setattr(obj, key, value)


def load() -> Config:
    cfg = Config()
    path = config_dir() / "config.toml"
    if path.exists():
        try:
            _fill(cfg, tomllib.loads(path.read_text(encoding="utf-8")))
        except (tomllib.TOMLDecodeError, OSError) as exc:
            print(f"vox: не читается {path}: {exc}", flush=True)

    lex = config_dir() / "lexicon.toml"
    if lex.exists():
        try:
            data = tomllib.loads(lex.read_text(encoding="utf-8"))
            lexicon.add_terms(data.get("terms", data))
        except (tomllib.TOMLDecodeError, OSError) as exc:
            print(f"vox: не читается {lex}: {exc}", flush=True)
    return cfg


DEFAULT_CONFIG = """\
# Конфиг vox — озвучка ответов Claude Code и markdown-файлов.
# Полная справка: vox --help

engine    = "say"      # say (macOS Milena, мгновенно) | silero (лучше качество)
auto      = true       # читать длинные ответы Claude Code автоматически
min_chars = 600        # ответ короче — не озвучивается
rate      = 200        # темп речи, слов в минуту (silero: 200 = medium, 160 = slow, 240 = fast)
volume    = 0.9
pause_ms  = 380        # пауза между абзацами

[text]
code_blocks = "announce"   # announce | skip | read
tables      = "announce"   # announce | skip | read
latin       = "dict+translit"  # как читать латиницу: dict+translit | dict | off
max_chars   = 6000         # предохранитель на одну озвучку

[say]
voice    = "Milena"        # русский голос macOS
voice_en = "Samantha"      # голос для англоязычных документов

[silero]
voice       = "aidar"      # aidar | baya | kseniya | xenia | eugene
pitch       = "medium"     # x-low | low | medium | high | x-high
sample_rate = 48000        # 8000 | 24000 | 48000 — выше = лучше
put_accent  = true         # автоматические ударения и ё
"""

DEFAULT_LEXICON = """\
# Свои варианты произношения. Ключ — слово латиницей, значение — как читать.
# Перебивает встроенный словарь vox.

[terms]
# myapp = "майапп"
# hetzner   = "хетцнер"
"""


def ensure_files() -> Path:
    """Создаёт конфиг и словарь при первом запуске."""
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    for name, content in (("config.toml", DEFAULT_CONFIG), ("lexicon.toml", DEFAULT_LEXICON)):
        path = d / name
        if not path.exists():
            path.write_text(content, encoding="utf-8")
    return d
