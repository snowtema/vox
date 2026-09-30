"""Общий интерфейс движков синтеза."""

from collections.abc import Callable
from subprocess import Popen


class EngineError(RuntimeError):
    """Движок недоступен или не смог синтезировать речь."""


# Колбэк, которым движок отдаёт запущенный процесс наружу, чтобы
# проигрыватель мог его прервать по сигналу.
OnChild = Callable[[Popen], None]


class Engine:
    name: str = "base"

    def available(self) -> tuple[bool, str]:
        """(готов ли к работе, что сделать если нет)."""
        raise NotImplementedError

    def prepare(self, text: str) -> str:
        """Подгонка нормализованного текста под особенности движка."""
        return text

    def speak(self, text: str, cfg, lang: str, on_child: OnChild) -> None:
        """Синтезирует и проигрывает текст. Блокирует до конца воспроизведения."""
        raise NotImplementedError

    def to_file(self, text: str, out: str, cfg, lang: str) -> str:
        """Синтезирует в аудиофайл, возвращает путь."""
        raise NotImplementedError
