"""Долгоживущий процесс синтеза Silero.

Модель грузится один раз и остаётся в памяти: прогрев занимает несколько
секунд, а синтез одного куска — десятки миллисекунд, поэтому воркер держится
открытым на всю озвучку.

Протокол — JSON по строке на stdin/stdout:
    ->  {"text": "...", "out": "/путь/chunk.wav"}
    <-  {"ok": true, "path": "..."} | {"error": "..."}
"""

import json
import sys


def main() -> int:
    model_path, speaker, sample_rate, put_accent = sys.argv[1:5]

    import torch

    torch.set_num_threads(max(1, (torch.get_num_threads() or 4)))
    model = torch.package.PackageImporter(model_path).load_pickle("tts_models", "model")
    model.to(torch.device("cpu"))

    sys.stdout.write(json.dumps({"ready": True}) + "\n")
    sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            model.save_wav(
                text=req["text"],
                speaker=speaker,
                sample_rate=int(sample_rate),
                audio_path=req["out"],
                put_accent=put_accent == "1",
                put_yo=put_accent == "1",
            )
            resp = {"ok": True, "path": req["out"]}
        except Exception as exc:                      # noqa: BLE001 — любой сбой синтеза
            resp = {"error": f"{type(exc).__name__}: {exc}"}
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
