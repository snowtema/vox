"""Markdown / вывод Claude Code -> текст, пригодный для чтения вслух.

Дословное чтение ответа Claude Code невыносимо: бэктики, пути, ссылки,
таблицы и простыни кода. Здесь текст переписывается так, чтобы его было
приятно слушать, и при этом не терялся смысл.

Результат — абзацы, разделённые пустой строкой. Пустая строка означает
паузу; как её озвучить, решает движок.
"""

import re
import unicodedata

from . import lexicon

# ── вспомогательное ───────────────────────────────────────────────────────────

_CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")
_LATIN = re.compile(r"[a-zA-Z]")

_EMOJI = re.compile(
    "[\U0001f000-\U0001faff\U00002190-\U000021ff\U00002300-\U000023ff"
    "\U00002500-\U00002bff\U0000fe00-\U0000fe0f\U0001f1e6-\U0001f1ff]+"
)
_ANSI = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_BOX = re.compile(r"[│├└┌┐┘─┬┴┼╭╮╯╰▶▼►✓✗✔✘•·]")
_DASH = re.compile(r"[ \t]*[—–][ \t]*")


def _dash_to_pause(m: re.Match[str]) -> str:
    """Тире -> запятая, но не второй подряд знак: «чтение, — добавлю»."""
    before = m.string[: m.start()].rstrip()
    return " " if before and before[-1] in ",.;:!?—–(" else ", "


def detect_lang(text: str) -> str:
    """Грубое определение языка документа по соотношению алфавитов."""
    ru, lat = len(_CYRILLIC.findall(text)), len(_LATIN.findall(text))
    if ru == 0 and lat == 0:
        return "ru"
    return "ru" if ru * 3 >= lat else "en"


def plural_ru(n: int, one: str, few: str, many: str) -> str:
    """Согласование числительного: 1 строка / 2 строки / 5 строк."""
    if n % 10 == 1 and n % 100 != 11:
        form = one
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        form = few
    else:
        form = many
    return f"{n} {form}"


# ── блочные конструкции ───────────────────────────────────────────────────────

_FENCE = re.compile(r"^([ \t]*)(`{3,}|~{3,})([^\n]*)\n(.*?)(?:^\1\2[ \t]*$|\Z)",
                    re.M | re.S)


def _strip_fences(md: str, mode: str) -> str:
    """Блоки кода: объявить, выбросить или прочитать целиком."""

    def repl(m: re.Match[str]) -> str:
        if mode == "read":
            return "\n\n" + m.group(4) + "\n\n"
        if mode == "skip":
            return "\n\n"
        lines = [ln for ln in m.group(4).splitlines() if ln.strip()]
        lang = (m.group(3) or "").strip().split()[:1]
        what = "код" if not lang else f"код на {lexicon.latinize(lang[0])}"
        return f"\n\nДалее {what}, {plural_ru(len(lines), 'строка', 'строки', 'строк')}.\n\n"

    return _FENCE.sub(repl, md)


_TABLE_SEP = re.compile(r"^[ \t]*\|?[ \t:|-]*-[ \t:|-]*\|?[ \t]*$")


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _strip_tables(md: str, mode: str) -> str:
    """Таблицы: озвучивание построчно либо краткое объявление."""
    out, lines, i = [], md.split("\n"), 0
    while i < len(lines):
        is_table = (
            lines[i].lstrip().startswith("|")
            and i + 1 < len(lines)
            and _TABLE_SEP.match(lines[i + 1])
            and "|" in lines[i + 1]
        )
        if not is_table:
            out.append(lines[i])
            i += 1
            continue

        header = _split_row(lines[i])
        j = i + 2
        rows = []
        while j < len(lines) and lines[j].lstrip().startswith("|"):
            rows.append(_split_row(lines[j]))
            j += 1

        if mode == "skip":
            out.append("")
        elif mode == "read":
            out.append("")
            for row in rows:
                cells = [
                    f"{header[k]}: {v}" if k < len(header) and header[k] else v
                    for k, v in enumerate(row)
                    if v and v not in {"-", "—"}
                ]
                if cells:
                    out.append("; ".join(cells) + ".")
            out.append("")
        else:
            out.append("")
            out.append(
                f"Далее таблица, {plural_ru(len(rows), 'строка', 'строки', 'строк')}."
            )
            out.append("")
        i = j
    return "\n".join(out)


# ── строчные конструкции ──────────────────────────────────────────────────────

_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"!\[[^\]]*\]\([^)]*\)"), ""),                  # картинки
    (re.compile(r"\[([^\]]+)\]\([^)]*\)"), r"\1"),               # ссылки
    (re.compile(r"\[([^\]]+)\]\[[^\]]*\]"), r"\1"),              # ref-ссылки
    (re.compile(r"<https?://[^>]+>"), "ссылка"),
    (re.compile(r"https?://\S+"), "ссылка"),
    (re.compile(r"<[^>\n]{1,80}>"), ""),                         # html-теги
    (re.compile(r"~~([^~]+)~~"), r"\1"),                         # зачёркнутое
    (re.compile(r"\*\*\*([^*]+)\*\*\*"), r"\1"),
    (re.compile(r"\*\*([^*]+)\*\*"), r"\1"),
    (re.compile(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])"), r"\1"),
    (re.compile(r"(?<![\w_])__([^_]+)__(?![\w_])"), r"\1"),
    (re.compile(r"(?<![\w_])_([^_\n]+)_(?![\w_])"), r"\1"),
]

_LIST_MARKER = re.compile(r"^(\s*)(?:[-*+]|\d{1,3}[.)])\s+(?:\[([ xX])\]\s*)?(.+)$")
_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+(.*?)[ \t]*#*[ \t]*$", re.M)
_HR = re.compile(r"^[ \t]*([-*_=])\1{2,}[ \t]*$", re.M)
_QUOTE = re.compile(r"^[ \t]*>[ \t]?", re.M)
_FOOTNOTE = re.compile(r"\[\^[^\]]+\]")

# file.ts:42 -> file.ts, строка 42
_FILE_LINE = re.compile(r"\b([\w.-]+\.\w{1,5}):(\d+)(?::\d+)?\b")
# три и более сегмента пути -> только имя файла
_LONG_PATH = re.compile(r"(?<![\w/~.])(?:~|\.{1,2})?/?(?:[\w.@-]+/){2,}([\w.-]+)")
# ${CLAUDE_PLUGIN_ROOT}, $HOME -> имя переменной без обвязки
_ENV_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Z_][A-Z0-9_]+)\b")
# PR #12 -> «номер 12»
_HASH_NUM = re.compile(r"(?<![\w&])#(\d+)")
# «a + b» — плюс, а не метка ударения
_PLUS = re.compile(r"(?<=\s)\+(?=\s)")


def _unwrap_lists(text: str) -> str:
    """Снимает маркеры списка; каждый пункт становится отдельным предложением."""
    out = []
    for line in text.split("\n"):
        m = _LIST_MARKER.match(line)
        if not m:
            out.append(line)
            continue
        check, body = m.group(2), m.group(3).strip()
        if check is not None:
            body = ("сделано: " if check.lower() == "x" else "не сделано: ") + body
        if body and body[-1] not in ".!?:;":
            body += "."
        out.append(body)
    return "\n".join(out)


def _speak_inline_code(text: str) -> str:
    """Содержимое `бэктиков`: убираем сами бэктики, сокращаем пути."""

    def repl(m: re.Match[str]) -> str:
        inner = m.group(1).strip()
        if not inner:
            return ""
        if len(inner) > 90:           # не код, а вставленная простыня
            return "фрагмент кода"
        inner = _LONG_PATH.sub(r"\1", inner)
        return inner

    return re.sub(r"`+([^`]*)`+", repl, text)


def normalize(md: str, cfg) -> str:
    """Полный конвейер: markdown -> абзацы для синтеза."""
    text = md.replace("\r\n", "\n")
    text = _ANSI.sub("", text)
    text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)   # frontmatter

    text = _strip_fences(text, cfg.code_blocks)
    text = _strip_tables(text, cfg.tables)
    text = _ENV_VAR.sub(lambda m: m.group(1) or m.group(2), text)
    text = _HASH_NUM.sub(r"номер \1", text)
    text = _PLUS.sub("плюс", text)

    text = _HR.sub("", text)
    text = _HEADING.sub(lambda m: f"\n{m.group(1).rstrip('.:')}.\n", text)
    text = _QUOTE.sub("", text)
    text = _unwrap_lists(text)
    text = _FOOTNOTE.sub("", text)

    text = _speak_inline_code(text)
    for pattern, repl in _RULES:
        text = pattern.sub(repl, text)

    text = _FILE_LINE.sub(r"\1, строка \2", text)
    text = _LONG_PATH.sub(r"\1", text)

    text = _EMOJI.sub("", text)
    text = _DASH.sub(_dash_to_pause, text)
    text = _BOX.sub(" ", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")

    if detect_lang(md) == "ru":
        text = lexicon.latinize(text, cfg.latin)

    # Сборка абзацев: одиночные переводы строк склеиваем, пустые — граница паузы
    paragraphs = []
    for block in re.split(r"\n\s*\n", text):
        joined = " ".join(ln.strip() for ln in block.splitlines() if ln.strip())
        joined = re.sub(r"[ \t]{2,}", " ", joined).strip()
        joined = re.sub(r"\s+([,.;:!?])", r"\1", joined)
        joined = re.sub(r"([,.;:!?])[ \t]*([,.;:])", r"\1", joined)
        joined = joined.strip("|# \t")
        if not joined:
            continue
        if joined[-1] not in ".!?:;,":
            joined += "."
        paragraphs.append(joined)

    result = "\n\n".join(paragraphs)
    if cfg.max_chars and len(result) > cfg.max_chars:
        cut = result.rfind(" ", 0, cfg.max_chars)
        result = result[: cut if cut > 0 else cfg.max_chars] + " … дальше пропущено."
    return result
