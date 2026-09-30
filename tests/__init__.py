"""Тесты vox. Запуск: python3 -m unittest discover -s tests -t .  (или pytest)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
