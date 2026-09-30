"""Движок на системном macOS `say`.

Задержка почти нулевая: `say` сам стримит синтез в динамики, поэтому текст
скармливается целиком, без нарезки. Паузы между абзацами ставятся встроенными
командами речи вида [[slnc 380]].
"""

import re
import shutil
import subprocess

from .base import Engine, EngineError, OnChild


class SayEngine(Engine):
    name = "say"

    def available(self) -> tuple[bool, str]:
        if not shutil.which("say"):
            return False, "команда `say` не найдена — движок доступен только на macOS"
        return True, ""

    def voices(self) -> set[str]:
        try:
            out = subprocess.run(
                ["say", "-v", "?"], capture_output=True, text=True, timeout=10
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return set()
        return {line.split()[0] for line in out.splitlines() if line.strip()}

    def pick_voice(self, cfg, lang: str) -> str:
        wanted = cfg.say.voice if lang == "ru" else cfg.say.voice_en
        installed = self.voices()
        if installed and wanted not in installed:
            # Голос мог быть удалён в системных настройках — не падаем молча
            fallback = "Milena" if lang == "ru" else "Samantha"
            if fallback in installed:
                print(f"vox: голос «{wanted}» не установлен, беру {fallback}")
                return fallback
        return wanted

    def prepare(self, text: str) -> str:
        # Метки ударения «кл+од» нужны Silero; say прочёл бы «+» вслух
        return re.sub(r"\+(?=[аеёиоуыэюяАЕЁИОУЫЭЮЯ])", "", text)

    def _script(self, text: str, cfg) -> str:
        """Текст -> вход для say с расставленными паузами."""
        # Квадратные скобки в тексте say примет за команду речи
        clean = text.replace("[", "(").replace("]", ")")
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", clean) if p.strip()]
        pause = f" [[slnc {max(0, int(cfg.pause_ms))}]] "
        volume = max(0.0, min(1.0, float(cfg.volume)))
        return f"[[volm {volume:.2f}]] " + pause.join(paragraphs)

    def speak(self, text: str, cfg, lang: str, on_child: OnChild) -> None:
        cmd = ["say", "-v", self.pick_voice(cfg, lang), "-r", str(int(cfg.rate))]
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        except OSError as exc:
            raise EngineError(f"не удалось запустить say: {exc}") from exc
        on_child(proc)
        try:
            proc.communicate(self._script(text, cfg).encode("utf-8"))
        except BrokenPipeError:
            pass

    def to_file(self, text: str, out: str, cfg, lang: str) -> str:
        cmd = [
            "say", "-v", self.pick_voice(cfg, lang), "-r", str(int(cfg.rate)),
            "-o", out, "--data-format=LEI16@22050",
        ]
        proc = subprocess.run(cmd, input=self._script(text, cfg).encode("utf-8"),
                              capture_output=True)
        if proc.returncode != 0:
            raise EngineError(proc.stderr.decode("utf-8", "replace").strip() or "say не справился")
        return out
