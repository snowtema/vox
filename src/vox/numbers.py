"""Числа -> русские слова.

Silero не читает цифры: «Прошло 12 строк» он произносит как «Прошло строк».
Поэтому для него числа разворачиваются в слова заранее. Системный say цифры
читает сам и лучше (с согласованием), ему это не нужно.
"""

import re

_ONES_M = ["ноль", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_ONES_F = ["ноль", "одна", "две"] + _ONES_M[3:]
_TEENS = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать",
          "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
_TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят",
         "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
_HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот",
             "шестьсот", "семьсот", "восемьсот", "девятьсот"]
_SCALES = [
    (10**9, ("миллиард", "миллиарда", "миллиардов"), False),
    (10**6, ("миллион", "миллиона", "миллионов"), False),
    (10**3, ("тысяча", "тысячи", "тысяч"), True),
]
_FRACTIONS = {
    1: ("десятая", "десятых", "десятых"),
    2: ("сотая", "сотых", "сотых"),
    3: ("тысячная", "тысячных", "тысячных"),
}


def form(n: int, forms: tuple[str, str, str]) -> str:
    """Форма слова после числа: 1 строка / 2 строки / 5 строк."""
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return forms[1]
    return forms[2]


def _triad(n: int, fem: bool) -> list[str]:
    words = []
    if n >= 100:
        words.append(_HUNDREDS[n // 100])
        n %= 100
    if 10 <= n < 20:
        words.append(_TEENS[n - 10])
        return words
    if n >= 20:
        words.append(_TENS[n // 10])
        n %= 10
    if n:
        words.append((_ONES_F if fem else _ONES_M)[n])
    return words


def int_words(n: int, fem: bool = False) -> str:
    if n == 0:
        return "ноль"
    words = []
    for scale, forms, scale_fem in _SCALES:
        if n >= scale:
            head = n // scale
            if not (head == 1 and scale == 10**3):
                words += _triad(head, scale_fem)
            words.append(form(head, forms))
            n %= scale
    if n:
        words += _triad(n, fem)
    return " ".join(words)


def decimal_words(whole: str, frac: str) -> str:
    """2.4 -> «две целых четыре десятых»."""
    if len(frac) > 3:
        return f"{int_words(int(whole))} точка " + " ".join(_ONES_M[int(d)] for d in frac)
    w, f = int(whole), int(frac)
    return (f"{int_words(w, fem=True)} {form(w, ('целая', 'целых', 'целых'))} "
            f"{int_words(f, fem=True)} {form(f, _FRACTIONS[len(frac)])}")


def _is_feminine_next(n: int, next_word: str) -> bool:
    """Род нужен только для 1 и 2. Эвристика по окончанию следующего слова:
    1 строка / 1 файл, 2 строки / 2 файла."""
    w = next_word.lower()
    if not w:
        return False
    if n % 10 == 1 and n % 100 != 11:
        return w[-1] in "ая"
    if n % 10 == 2 and n % 100 != 12:
        return w[-1] in "иы"
    return False


# единица -> (формы, женский род). Однобуквенные через пробел — только перед
# знаком препинания или концом строки, иначе «сравнил 5 с 6» стало бы секундами.
_UNITS: dict[str, tuple[tuple[str, str, str], bool]] = {
    "мс": (("миллисекунда", "миллисекунды", "миллисекунд"), True),
    "сек": (("секунда", "секунды", "секунд"), True),
    "с": (("секунда", "секунды", "секунд"), True),
    "мин": (("минута", "минуты", "минут"), True),
    "ч": (("час", "часа", "часов"), False),
    "кб": (("килобайт", "килобайта", "килобайт"), False),
    "мб": (("мегабайт", "мегабайта", "мегабайт"), False),
    "гб": (("гигабайт", "гигабайта", "гигабайт"), False),
    "тб": (("терабайт", "терабайта", "терабайт"), False),
    "пкс": (("пиксель", "пикселя", "пикселей"), False),
}
_TIGHT_ONLY = {"с", "ч"}

_THOUSANDS_SEP = re.compile(r"(?<=\d)[ \u00a0\u202f](?=\d{3}(?!\d))")
_VERSION = re.compile(r"(?<![\d.])(\d+(?:\.\d+){2,})(?!\d)")
_PERCENT = re.compile(r"(?<![\d.,])(\d+)(?:[.,](\d+))?\s*%")
_NUMBER = re.compile(
    r"(?<![\d.,])(\d+)(?:[.,](\d+)(?![.,]?\d))?([ \t]*)([а-яёА-ЯЁ]*)"
)


def _digits(s: str) -> str:
    return " ".join(_ONES_M[int(d)] for d in s)


def expand(text: str) -> str:
    text = _THOUSANDS_SEP.sub("", text)

    # 0.1.1 -> «ноль точка один точка один»
    text = _VERSION.sub(
        lambda m: " точка ".join(int_words(int(p)) for p in m.group(1).split(".")), text
    )

    def percent(m: re.Match[str]) -> str:
        if m.group(2):
            return decimal_words(m.group(1), m.group(2)) + " процента"
        n = int(m.group(1))
        return f"{int_words(n)} {form(n, ('процент', 'процента', 'процентов'))}"

    text = _PERCENT.sub(percent, text)

    def number(m: re.Match[str]) -> str:
        whole, frac, gap, word = m.groups()
        unit = _UNITS.get(word.lower())
        if unit and gap and word.lower() in _TIGHT_ONLY:
            # «2 с.» — секунды, «5 с 6» / «5 с ним» — предлог
            rest = m.string[m.end():].lstrip(" \t")
            if rest and rest[0].isalnum():
                unit = None

        if len(whole) > 12:                    # телефон, хеш — по цифрам
            spoken = _digits(whole)
            return f"{spoken}{gap or (' ' if word else '')}{word}"

        if frac is not None:
            spoken = decimal_words(whole, frac)
            if unit:
                return f"{spoken} {unit[0][1]}"       # «две целых четыре десятых секунды»
            return f"{spoken}{gap or (' ' if word else '')}{word}"

        n = int(whole)
        if unit:
            forms, fem = unit
            return f"{int_words(n, fem=fem)} {form(n, forms)}"
        spoken = int_words(n, fem=_is_feminine_next(n, word))
        return f"{spoken}{gap or (' ' if word else '')}{word}"

    return _NUMBER.sub(number, text)
