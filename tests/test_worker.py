"""Протокол воркера Silero, проверенный на настоящем scripts/silero_worker.py.

Вместо torch подкладывается заглушка: модель «синтезирует» в файл описание
запроса. Так проверяется всё, что делает сам воркер: рукопожатие, JSON-строки,
пропуск пустых строк, ответы об ошибках.
"""

import json
import os
import subprocess
import sys
import textwrap
import unittest

from tests.support import IsolatedCase, ROOT

FAKE_TORCH = textwrap.dedent('''\
    import json, types

    def set_num_threads(n): pass
    def get_num_threads(): return 2
    def device(name): return name

    class _Model:
        def to(self, dev): return self
        def save_wav(self, text=None, ssml_text=None, speaker=None, sample_rate=None,
                     audio_path=None, put_accent=None, put_yo=None):
            if "FAIL" in (text or ssml_text):
                raise RuntimeError("boom")
            with open(audio_path, "w") as fh:
                json.dump(dict(text=text, ssml_text=ssml_text, speaker=speaker,
                               sample_rate=sample_rate, put_accent=put_accent, put_yo=put_yo), fh)

    class _Importer:
        def __init__(self, path): self.path = path
        def load_pickle(self, package, name):
            assert (package, name) == ("tts_models", "model")
            return _Model()

    package = types.SimpleNamespace(PackageImporter=_Importer)
''')


class WorkerProtocolTest(IsolatedCase):
    def run_worker(self, lines: list[str], accent: str = "1", speaker: str = "baya",
                   rate: str = "48000") -> tuple[int, list[dict]]:
        stub = self.tmp / "stub"
        stub.mkdir(exist_ok=True)
        (stub / "torch.py").write_text(FAKE_TORCH, encoding="utf-8")
        env = dict(os.environ, PYTHONPATH=str(stub))
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "silero_worker.py"),
             "model.pt", speaker, rate, accent],
            input="\n".join(lines) + "\n", capture_output=True, text=True,
            env=env, timeout=60,
        )
        replies = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        return proc.returncode, replies

    def request(self, text: str, name: str = "a.wav") -> str:
        return json.dumps({"text": text, "out": str(self.tmp / name)})

    def test_handshake_then_synthesis(self):
        code, replies = self.run_worker([self.request("Привет.")])
        self.assertEqual(code, 0)
        self.assertEqual(replies[0], {"ready": True})
        self.assertEqual(replies[1], {"ok": True, "path": str(self.tmp / "a.wav")})
        saved = json.loads((self.tmp / "a.wav").read_text())
        self.assertEqual(saved, {"text": "Привет.", "ssml_text": None, "speaker": "baya",
                                 "sample_rate": 48000, "put_accent": True, "put_yo": True})

    def test_ssml_request_goes_to_ssml_text(self):
        ssml = '<speak><prosody rate="medium" pitch="medium">Привет.</prosody></speak>'
        code, replies = self.run_worker([json.dumps({"ssml": ssml, "out": str(self.tmp / "s.wav")})])
        self.assertEqual(code, 0)
        self.assertTrue(replies[1]["ok"])
        saved = json.loads((self.tmp / "s.wav").read_text())
        self.assertEqual(saved["ssml_text"], ssml)
        self.assertIsNone(saved["text"])

    def test_speaker_rate_and_accent_come_from_argv(self):
        self.run_worker([self.request("Текст.")], accent="0", speaker="aidar", rate="24000")
        saved = json.loads((self.tmp / "a.wav").read_text())
        self.assertEqual(saved["speaker"], "aidar")
        self.assertEqual(saved["sample_rate"], 24000)
        self.assertFalse(saved["put_accent"])
        self.assertFalse(saved["put_yo"])

    def test_one_reply_per_request_in_order(self):
        code, replies = self.run_worker([
            self.request("Раз.", "1.wav"), self.request("Два.", "2.wav"),
            self.request("Три.", "3.wav"),
        ])
        self.assertEqual([r["path"] for r in replies[1:]],
                         [str(self.tmp / f"{i}.wav") for i in (1, 2, 3)])

    def test_blank_lines_are_ignored(self):
        _, replies = self.run_worker(["", "   ", self.request("Текст.")])
        self.assertEqual(len(replies), 2)

    def test_synthesis_error_is_reported_and_worker_keeps_going(self):
        code, replies = self.run_worker([
            self.request("FAIL тут.", "bad.wav"), self.request("Дальше.", "ok.wav"),
        ])
        self.assertEqual(code, 0)
        self.assertEqual(replies[1], {"error": "RuntimeError: boom"})
        self.assertEqual(replies[2]["ok"], True)

    def test_malformed_json_is_reported_not_fatal(self):
        code, replies = self.run_worker(["{не json", self.request("Жив.")])
        self.assertEqual(code, 0)
        self.assertIn("error", replies[1])
        self.assertTrue(replies[2]["ok"])

    def test_request_without_fields_is_reported(self):
        _, replies = self.run_worker(['{"text": "без out"}'])
        self.assertIn("KeyError", replies[1]["error"])


if __name__ == "__main__":
    unittest.main()
