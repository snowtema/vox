"""Нарезка нормализованного текста на куски для потокового синтеза.

Нужна движкам, которые синтезируют файл целиком (Silero): пока играет кусок N,
синтезируется N+1, поэтому звук начинается почти сразу, а не после обработки
всей простыни. Размер куска — компромисс между задержкой старта и
естественностью интонации.
"""

import re

_SENTENCE = re.compile(r"(?<=[.!?…])\s+(?=[^\s])")
_CLAUSE = re.compile(r"(?<=[,;:])\s+(?=[^\s])")


def _split_long(sentence: str, limit: int) -> list[str]:
    """Слишком длинное предложение режем по запятым, затем по словам."""
    if len(sentence) <= limit:
        return [sentence]

    out, buf = [], ""
    for piece in _CLAUSE.split(sentence):
        if buf and len(buf) + len(piece) + 1 > limit:
            out.append(buf)
            buf = piece
        else:
            buf = f"{buf} {piece}".strip()
    if buf:
        out.append(buf)

    final = []
    for part in out:
        while len(part) > limit:
            cut = part.rfind(" ", 0, limit)
            cut = cut if cut > limit // 2 else limit
            final.append(part[:cut].strip())
            part = part[cut:].strip()
        if part:
            final.append(part)
    return final


def chunks(text: str, limit: int = 340, pause_ms: int = 380) -> list[tuple[str, int]]:
    """Возвращает [(кусок, пауза после него в мс)].

    Куски не пересекают границу предложения; после последнего куска абзаца
    ставится пауза.
    """
    result: list[tuple[str, int]] = []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    for par in paragraphs:
        pieces: list[str] = []
        for sentence in _SENTENCE.split(par):
            pieces.extend(_split_long(sentence.strip(), limit))

        buf = ""
        par_chunks: list[str] = []
        for piece in pieces:
            if buf and len(buf) + len(piece) + 1 > limit:
                par_chunks.append(buf)
                buf = piece
            else:
                buf = f"{buf} {piece}".strip()
        if buf:
            par_chunks.append(buf)

        for idx, chunk in enumerate(par_chunks):
            last = idx == len(par_chunks) - 1
            result.append((chunk, pause_ms if last else 0))

    if result:
        result[-1] = (result[-1][0], 0)
    return result
