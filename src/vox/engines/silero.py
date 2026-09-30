"""Движок Silero TTS — заметно живее системного голоса, но требует torch.

Изоляция: torch ставится в отдельный venv под управлением uv (Python 3.12),
чтобы не трогать системный Python. Ставится по требованию: `vox setup silero`.

Синтез конвейерный. Пока afplay проигрывает кусок N, воркер синтезирует N+1,
поэтому звук начинается через долю секунды после прогрева модели, а не после
обработки всего текста.

Текст уходит в модель как SSML: темп и высота голоса — через <prosody>, пауза
после абзаца — через <break> в конце куска. Пауза попадает в сам звук, поэтому
между кусками нет слышимого стыка.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

from .. import chunker, numbers
from ..config import cache_dir
from .base import Engine, EngineError, OnChild

MODEL_URL = "https://models.silero.ai/models/tts/ru/v4_ru.pt"
SPEAKERS = {"aidar", "baya", "kseniya", "xenia", "eugene"}
DEFAULT_SPEAKER = "aidar"

# Именованные значения из самой модели (rate2value / pitch2value). Числовые
# проценты в <prosody> Silero молча игнорирует, поэтому только они.
RATES = {"x-slow": 0.5, "slow": 0.8, "medium": 1.0, "fast": 1.2, "x-fast": 1.5}
PITCHES = ("x-low", "low", "medium", "high", "x-high", "robot")
DEFAULT_PITCH = "medium"
BASE_WPM = 200      # темп «medium» ≈ 200 слов/мин — совпадает с rate по умолчанию


def _home() -> Path:
    return cache_dir() / "silero"


def venv_python() -> Path:
    return _home() / "venv" / "bin" / "python"


def model_path() -> Path:
    return _home() / "v4_ru.pt"


def worker_script() -> Path:
    return Path(__file__).resolve().parents[3] / "scripts" / "silero_worker.py"


def prosody_rate(wpm: int) -> str:
    """Темп в словах/мин -> ближайшее именованное значение Silero."""
    factor = wpm / BASE_WPM
    return min(RATES, key=lambda name: abs(RATES[name] - factor))


def build_ssml(text: str, rate_wpm: int, pitch: str, pause_ms: int = 0) -> str:
    """Один кусок текста -> SSML с темпом, высотой и паузой в конце."""
    tail = f'<break time="{int(pause_ms)}ms"/>' if pause_ms > 0 else ""
    return (f'<speak><prosody rate="{prosody_rate(rate_wpm)}" pitch="{pitch}">'
            f"{escape(text)}</prosody>{tail}</speak>")


class SileroEngine(Engine):
    name = "silero"

    def available(self) -> tuple[bool, str]:
        if not venv_python().exists():
            return False, "движок не установлен — запусти `vox setup silero`"
        if not model_path().exists():
            return False, "модель не скачана — запусти `vox setup silero`"
        return True, ""

    # ── установка ─────────────────────────────────────────────────────────────

    def setup(self) -> None:
        if not shutil.which("uv"):
            raise EngineError(
                "нужен uv для изолированного окружения с torch.\n"
                "  Поставь: brew install uv\n"
                "  Затем повтори: vox setup silero"
            )
        home = _home()
        home.mkdir(parents=True, exist_ok=True)

        if not venv_python().exists():
            print("vox: создаю окружение (Python 3.12)…")
            self._run(["uv", "venv", "--python", "3.12", str(home / "venv")])

        if self._torch_ok():
            print("vox: torch уже стоит")
        else:
            print("vox: ставлю torch — это разово, несколько минут…")
            self._run([
                "uv", "pip", "install", "--python", str(venv_python()),
                "torch>=2.1,<3", "numpy",
            ])

        if not model_path().exists():
            print("vox: качаю модель v4_ru (~60 МБ)…")
            tmp = model_path().with_suffix(".part")
            self._run(["curl", "-fL", "--progress-bar", "-o", str(tmp), MODEL_URL])
            tmp.rename(model_path())

        print("vox: прогреваю модель…")
        proc = self._spawn_worker(DEFAULT_SPEAKER, 48000, True)
        self._await_ready(proc)
        proc.stdin.close()
        proc.wait(timeout=30)
        print("vox: Silero готов. Включить по умолчанию — engine = \"silero\" в конфиге.")

    @staticmethod
    def _run(cmd: list[str]) -> None:
        proc = subprocess.run(cmd)
        if proc.returncode != 0:
            raise EngineError(f"команда не выполнилась: {' '.join(cmd)}")

    @staticmethod
    def _torch_ok() -> bool:
        try:
            return subprocess.run(
                [str(venv_python()), "-c", "import torch, numpy"],
                capture_output=True, timeout=60,
            ).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    # ── синтез ────────────────────────────────────────────────────────────────

    def prepare(self, text: str) -> str:
        # Silero молча выбрасывает цифры — разворачиваем их в слова
        return numbers.expand(text)

    def _spawn_worker(self, speaker: str, sample_rate: int, accent: bool) -> subprocess.Popen:
        cmd = [
            str(venv_python()), str(worker_script()),
            str(model_path()), speaker, str(sample_rate), "1" if accent else "0",
        ]
        try:
            return subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, bufsize=1,
            )
        except OSError as exc:
            raise EngineError(f"не удалось запустить воркер Silero: {exc}") from exc

    @staticmethod
    def _await_ready(proc: subprocess.Popen) -> None:
        line = proc.stdout.readline()
        if not line:
            raise EngineError("воркер Silero умер при загрузке модели — переустанови: vox setup silero")
        try:
            if not json.loads(line).get("ready"):
                raise EngineError(f"воркер Silero ответил неожиданно: {line.strip()}")
        except json.JSONDecodeError:
            raise EngineError(f"воркер Silero ответил мусором: {line.strip()[:200]}") from None

    def _speaker(self, cfg) -> str:
        speaker = cfg.silero.voice
        if speaker not in SPEAKERS:
            print(f"vox: голос «{speaker}» неизвестен, беру {DEFAULT_SPEAKER} "
                  f"({', '.join(sorted(SPEAKERS))})")
            return DEFAULT_SPEAKER
        return speaker

    def _pitch(self, cfg) -> str:
        pitch = cfg.silero.pitch
        if pitch not in PITCHES:
            print(f"vox: высота «{pitch}» неизвестна, беру {DEFAULT_PITCH} ({', '.join(PITCHES)})")
            return DEFAULT_PITCH
        return pitch

    def _pieces(self, text: str, cfg) -> list[str]:
        """Нормализованный текст -> список SSML-кусков с паузами внутри."""
        pitch = self._pitch(cfg)
        return [
            build_ssml(chunk, cfg.rate, pitch, pause_ms)
            for chunk, pause_ms in chunker.chunks(text, pause_ms=cfg.pause_ms)
        ]

    def speak(self, text: str, cfg, lang: str, on_child: OnChild) -> None:
        pieces = self._pieces(text, cfg)
        if not pieces:
            return

        proc = self._spawn_worker(self._speaker(cfg), cfg.silero.sample_rate,
                                  cfg.silero.put_accent)
        on_child(proc)
        tmpdir = tempfile.mkdtemp(prefix="vox-")
        try:
            self._await_ready(proc)
            self._pipeline(proc, pieces, tmpdir, cfg, on_child)
        finally:
            if proc.poll() is None:
                try:
                    proc.stdin.close()
                except OSError:
                    pass
                proc.terminate()
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _request(self, proc: subprocess.Popen, ssml: str, path: str) -> None:
        proc.stdin.write(json.dumps({"ssml": ssml, "out": path}) + "\n")
        proc.stdin.flush()

    def _pipeline(self, proc, pieces: list[str], tmpdir, cfg, on_child: OnChild) -> None:
        """Держим два куска в работе: один играет, следующий синтезируется."""
        lookahead = 2
        for i in range(min(lookahead, len(pieces))):
            self._request(proc, pieces[i], os.path.join(tmpdir, f"{i}.wav"))

        for i in range(len(pieces)):
            line = proc.stdout.readline()
            if not line:
                raise EngineError("воркер Silero прервался на середине текста")
            resp = json.loads(line)
            if "error" in resp:
                raise EngineError(f"Silero не синтезировал кусок {i + 1}: {resp['error']}")

            nxt = i + lookahead
            if nxt < len(pieces):
                self._request(proc, pieces[nxt], os.path.join(tmpdir, f"{nxt}.wav"))

            player = subprocess.Popen(
                ["afplay", "-v", f"{max(0.0, min(1.0, float(cfg.volume))):.2f}", resp["path"]]
            )
            on_child(player)
            if player.wait() != 0:
                raise EngineError("afplay не смог проиграть синтезированный кусок")

    def to_file(self, text: str, out: str, cfg, lang: str) -> str:
        pieces = self._pieces(text, cfg)
        if not pieces:
            raise EngineError("нечего синтезировать")
        if not shutil.which("ffmpeg"):
            # Проверяем до прогрева модели: иначе ffmpeg упадёт только в самом конце
            raise EngineError("для записи в файл нужен ffmpeg: brew install ffmpeg")

        proc = self._spawn_worker(self._speaker(cfg), cfg.silero.sample_rate,
                                  cfg.silero.put_accent)
        tmpdir = tempfile.mkdtemp(prefix="vox-")
        try:
            self._await_ready(proc)
            parts = []
            for i, ssml in enumerate(pieces):
                path = os.path.join(tmpdir, f"{i}.wav")
                self._request(proc, ssml, path)
                resp = json.loads(proc.stdout.readline() or "{}")
                if "error" in resp:
                    raise EngineError(f"Silero не синтезировал кусок {i + 1}: {resp['error']}")
                parts.append(path)

            listfile = os.path.join(tmpdir, "list.txt")
            Path(listfile).write_text(
                "".join(f"file '{p}'\n" for p in parts), encoding="utf-8"
            )
            merge = subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy", out],
                capture_output=True,
            )
            if merge.returncode != 0:
                raise EngineError(merge.stderr.decode("utf-8", "replace")[-400:])
            return out
        finally:
            if proc.poll() is None:
                proc.terminate()
            shutil.rmtree(tmpdir, ignore_errors=True)
