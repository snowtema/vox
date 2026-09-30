"""Движки синтеза речи."""

from .base import Engine, EngineError
from .mac_say import SayEngine
from .silero import SileroEngine

ENGINES: dict[str, type[Engine]] = {
    "say": SayEngine,
    "silero": SileroEngine,
}


def get(name: str) -> Engine:
    try:
        return ENGINES[name]()
    except KeyError:
        known = ", ".join(ENGINES)
        raise EngineError(f"неизвестный движок «{name}». Доступны: {known}") from None


__all__ = ["Engine", "EngineError", "SayEngine", "SileroEngine", "ENGINES", "get"]
