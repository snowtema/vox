"""Произношение латиницы русским голосом.

Русские TTS-движки (macOS Milena, Silero) не умеют читать латиницу: либо
проглатывают её, либо читают по русским буквенным правилам. Ответы Claude Code
на 20-30% состоят из английских технических терминов, поэтому латиница
переводится в кириллицу до синтеза.

Значения словаря могут содержать метку ударения «+» перед гласной («кл+од»):
Silero её понимает, а без неё редуцирует безударное «о» в «а» в незнакомых
словах. Движок say метки вырезает.

Три уровня, в порядке приоритета:
  1. TERMS       — словарь известных терминов (Next.js -> «некст джей эс»)
  2. ACRONYMS    — незнакомая аббревиатура CAPS читается по буквам (CDN -> «си ди эн»)
  3. translit()  — фонетическая транслитерация всего остального
"""

import re

# ── 1. Словарь терминов ───────────────────────────────────────────────────────
# Ключи в нижнем регистре. Точки/дефисы/подчёркивания в ключе значимы:
# сопоставление идёт по нормализованной форме слова.
TERMS: dict[str, str] = {
    # языки и рантаймы
    "javascript": "джаваскрипт", "typescript": "тайпскрипт", "python": "питон",
    "node": "нода", "nodejs": "нода", "node.js": "нода", "deno": "дено", "bun": "бан",
    "rust": "раст", "golang": "голанг", "swift": "свифт", "kotlin": "котлин",
    "php": "пи эйч пи", "ruby": "руби", "java": "джава", "sql": "эс кью эль",
    "bash": "баш", "zsh": "зэт шелл", "shell": "шелл", "regex": "регэксп",
    # фреймворки и библиотеки
    "react": "реакт", "nextjs": "некст джей эс", "next.js": "некст джей эс",
    "next": "некст", "vue": "вью", "svelte": "свелт", "sveltekit": "свелткит",
    "angular": "ангуляр", "astro": "астро", "remix": "ремикс", "nuxt": "накст",
    "tailwind": "тейлвинд", "tailwindcss": "тейлвинд си эс эс",
    "express": "экспресс", "fastapi": "фастапи", "django": "джанго",
    "flask": "фласк", "prisma": "призма", "drizzle": "дриззл",
    "shadcn": "шадсиэн", "zod": "зод", "vite": "вит", "webpack": "вебпак",
    "turbopack": "турбопак", "eslint": "и эс линт", "prettier": "приттиер",
    "vitest": "витест", "jest": "джест", "playwright": "плейрайт",
    "puppeteer": "паппетир", "storybook": "сторибук", "redux": "редакс",
    "zustand": "цустанд", "framer": "фреймер", "motion": "моушн",
    # платформы и сервисы
    "vercel": "версель", "cloudflare": "клаудфлер", "netlify": "нетлифай",
    "supabase": "супабейс", "firebase": "файербейс", "aws": "эй дабл-ю эс",
    "github": "гитхаб", "gitlab": "гитлаб", "docker": "докер",
    "kubernetes": "кубернетес", "k8s": "кубернетес", "nginx": "энджин экс",
    "postgres": "постгрес", "postgresql": "постгрес", "mysql": "май эс кью эль",
    "sqlite": "эс кью лайт", "redis": "редис", "mongodb": "монго ди би",
    "stripe": "страйп", "sentry": "сентри", "figma": "фигма",
    "anthropic": "антр+опик", "claude": "кл+од", "code": "к+од",
    "openai": "оупен эй ай",
    "hetzner": "хетцнер", "wrangler": "рэнглер",
    # git и процесс
    "git": "гит", "commit": "коммит", "merge": "мёрдж", "rebase": "ребейз",
    "branch": "бранч", "pull": "пулл", "push": "пуш", "fork": "форк",
    "issue": "ишью", "release": "релиз", "deploy": "деплой",
    "build": "билд", "lint": "линт", "test": "тест", "ci": "си ай",
    "cd": "си ди", "pr": "пи ар", "mr": "эм ар", "diff": "дифф",
    "staging": "стейджинг", "production": "продакшн", "prod": "прод",
    "rollback": "роллбэк", "changelog": "ченджлог", "readme": "ридми",
    # общая терминология
    "api": "эй пи ай", "rest": "рест", "graphql": "граф кью эль",
    "json": "джейсон", "yaml": "ямл", "toml": "томл", "xml": "икс эм эль",
    "csv": "си эс ви", "html": "эйч ти эм эль", "css": "си эс эс",
    "scss": "эс си эс эс", "svg": "эс ви джи", "png": "пинг", "webp": "вебпи",
    "url": "юар эль", "uri": "юар ай", "http": "эйч ти ти пи",
    "https": "эйч ти ти пи эс", "dns": "ди эн эс", "cdn": "си ди эн",
    "ssl": "эс эс эль", "tls": "ти эль эс", "ssh": "эс эс эйч",
    "cli": "си эл ай", "gui": "гуи", "ui": "юай", "ux": "ю экс",
    "ssr": "эс эс эр", "ssg": "эс эс джи", "isr": "и эс эр", "spa": "эс пи эй",
    "csr": "си эс эр", "seo": "сио", "crud": "круд", "orm": "оу эр эм",
    "sdk": "эс ди кей", "npm": "эн пи эм", "pnpm": "пи эн пи эм",
    "yarn": "ярн", "pip": "пип", "uv": "ю ви", "brew": "брю",
    "env": "энв", "config": "конфиг", "cache": "кэш", "cookie": "куки",
    "token": "токен", "auth": "аус", "oauth": "о аус", "jwt": "джей дабл-ю ти",
    "cors": "корс", "csrf": "си эс ар эф", "xss": "икс эс эс",
    "rls": "эр эль эс", "acl": "эй си эль", "rbac": "ар бак",
    "llm": "эль эль эм", "ai": "эй ай", "ml": "эм эль", "rag": "рэг",
    "mcp": "эм си пи", "tts": "ти ти эс", "stt": "эс ти ти",
    "cpu": "си пи ю", "gpu": "джи пи ю", "ram": "рэм", "ssd": "эс эс ди",
    "os": "оу эс", "macos": "макос", "ios": "ай оу эс", "linux": "линукс",
    "windows": "виндоус", "arm": "арм", "x86": "икс восемьдесят шесть",
    # частые слова в ответах
    "true": "тру", "false": "фолс", "null": "налл", "undefined": "андефайнд",
    "async": "асинк", "await": "эвейт", "promise": "промис", "hook": "хук",
    "hooks": "хуки", "props": "пропсы", "state": "стейт", "store": "стор",
    "component": "компонент", "router": "роутер", "route": "роут",
    "middleware": "мидлвар", "server": "сервер", "client": "клиент",
    "bundle": "бандл", "chunk": "чанк", "stream": "стрим", "buffer": "буфер",
    "timeout": "таймаут", "retry": "ретрай", "fallback": "фолбэк",
    "default": "дефолт", "export": "экспорт", "import": "импорт",
    "type": "тайп", "interface": "интерфейс", "enum": "энам",
    "schema": "схема", "migration": "миграция", "query": "квери",
    "mutation": "мутация", "endpoint": "эндпоинт", "payload": "пейлоад",
    "request": "реквест", "response": "респонс", "header": "хедер",
    "log": "лог", "logs": "логи", "debug": "дебаг", "error": "эррор",
    "warning": "варнинг", "patch": "патч", "fix": "фикс", "bug": "баг",
    "feature": "фича", "refactor": "рефактор", "todo": "туду",
    "use": "юз", "effect": "эффект", "useeffect": "юз эффект",
    "usestate": "юз стейт", "usememo": "юз мемо", "useref": "юз реф",
    "render": "рендер", "update": "апдейт", "install": "инсталл",
    "run": "ран", "start": "старт", "add": "адд", "remove": "ремув",
    "delete": "делит", "create": "криэйт", "file": "файл", "folder": "фолдер",
    "function": "функция", "class": "класс", "method": "метод",
    "value": "вэлью", "key": "кей", "name": "нейм", "list": "лист",
    "array": "эррей", "object": "обджект", "string": "стринг",
    "number": "намбер", "boolean": "булеан", "index": "индекс",
    "page": "пейдж", "layout": "лейаут", "app": "апп", "src": "сорс",
    "lib": "либ", "utils": "ютилс", "dist": "дист", "public": "паблик",
    
    "main": "мейн", "dev": "дев", "preview": "превью", "watch": "вотч",
    "clean": "клин", "check": "чек", "format": "формат", "serve": "сёрв",
    "hero": "х+иро", "plugin": "пл+агин", "plugins": "пл+агины", "root": "рут", "bin": "бин",
    "path": "пэс", "dir": "дир", "home": "хоум", "vox": "вокс",
    "skill": "скилл", "skills": "скиллы", "agent": "+эйджент", "agents": "+эйдженты",
    "subagent": "саб+эйджент", "session": "с+ешн", "prompt": "промпт",
    # формы единственного числа: множественное (tests, files, assets) строит _inflect
    "script": "скрипт", "asset": "ассет", "style": "стайл", "worker": "воркер",
    "tool": "тул", "user": "юзер", "hash": "хэш", "handler": "хендлер",
    "helper": "хелпер", "parser": "парсер", "parse": "парс", "linter": "линтер",
    "logger": "логгер", "package": "пэкидж", "module": "модуль", "version": "версия",
    "doc": "док", "docs": "докс", "repo": "репо", "repository": "репозиторий",
    "setup": "сетап", "workflow": "воркфлоу", "pipeline": "пайплайн",
    "template": "темплейт", "terminal": "терминал", "model": "модель",
    "frontend": "фронтенд", "backend": "бэкенд", "fullstack": "фулстек",
    "database": "датабейс", "db": "ди би", "webhook": "вебхук",
    "websocket": "вебсокет", "snapshot": "снапшот", "mock": "мок", "stub": "стаб",
    "coverage": "коверидж", "cron": "крон", "proxy": "прокси", "chat": "чат",
    "bot": "бот", "web": "веб", "site": "сайт", "link": "линк", "button": "баттон",
    "input": "инпут", "output": "аутпут", "image": "имидж", "video": "видео",
    "audio": "аудио", "mobile": "мобайл", "desktop": "десктоп",
    "browser": "браузер", "id": "ай ди", "ip": "ай пи", "uuid": "ю ю ай ди",
    "process": "процесс", "access": "аксесс", "address": "адрес",
    "ok": "окей", "base": "бейс", "sha": "ша", "utf": "ю ти эф",
    # составные имена и бренды, которые не разбираются по частям
    "tsconfig": "тэ эс конфиг", "vscode": "ви эс к+од", "xcode": "экс к+од",
    "iphone": "айфон", "ipad": "айпад", "npx": "эн пи экс",
    "dockerfile": "докерфайл", "jsonl": "джейсон эл",
    # расширения файлов — читаются в составе имени
    "ts": "тэ эс", "tsx": "тэ эс икс", "js": "джей эс", "jsx": "джей эс икс",
    "py": "пай", "md": "эм ди", "mjs": "эм джей эс", "cjs": "си джей эс",
    "sh": "эс эйч", "txt": "текст", "lock": "лок", "gitignore": "гитигнор",
}

# ── 2. Буквы для незнакомых аббревиатур ───────────────────────────────────────
LETTER_NAMES = {
    "a": "эй", "b": "би", "c": "си", "d": "ди", "e": "и", "f": "эф",
    "g": "джи", "h": "эйч", "i": "ай", "j": "джей", "k": "кей", "l": "эль",
    "m": "эм", "n": "эн", "o": "оу", "p": "пи", "q": "кью", "r": "ар",
    "s": "эс", "t": "ти", "u": "ю", "v": "ви", "w": "дабл-ю", "x": "икс",
    "y": "уай", "z": "зед",
}

# ── 3. Фонетическая транслитерация ────────────────────────────────────────────
# Диграфы проверяются раньше одиночных букв.
_DIGRAPHS = [
    ("sch", "ш"), ("tch", "ч"), ("igh", "ай"),
    ("sh", "ш"), ("ch", "ч"), ("th", "з"), ("ph", "ф"), ("wh", "в"),
    ("ck", "к"), ("ng", "нг"), ("qu", "кв"), ("kh", "х"), ("zh", "ж"),
    ("ee", "и"), ("ea", "и"), ("oo", "у"), ("ou", "ау"), ("ow", "оу"),
    ("oa", "оу"), ("ai", "эй"), ("ay", "эй"), ("ey", "эй"), ("oi", "ой"),
    ("oy", "ой"), ("au", "о"), ("aw", "о"), ("ie", "и"), ("ue", "ю"),
    ("ya", "я"), ("yu", "ю"), ("yo", "ё"), ("ts", "ц"), ("js", "джс"),
]
_SINGLES = {
    "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф", "g": "г",
    "h": "х", "i": "и", "j": "дж", "k": "к", "l": "л", "m": "м", "n": "н",
    "o": "о", "p": "п", "q": "к", "r": "р", "s": "с", "t": "т", "u": "у",
    "v": "в", "w": "в", "x": "кс", "y": "й", "z": "з",
}


# Окончания, которые в английском читаются не по буквам
_SUFFIXES = [("tion", "шн"), ("sion", "жн"), ("ture", "чер"), ("ous", "ус"),
             ("ble", "бл"), ("cle", "кл"), ("tle", "тл"), ("dge", "дж")]
_VOWELS = set("aeiouy")


def translit(word: str) -> str:
    """Фонетическая транслитерация латинского слова в кириллицу."""
    src = word.lower()

    # Суффикс раньше «немой e»: иначе ture/dge/ble не дожили бы до проверки
    suffix = ""
    for tail, repl in _SUFFIXES:
        if len(src) > len(tail) + 1 and src.endswith(tail):
            suffix, src = repl, src[: -len(tail)]
            break
    else:
        # Немая конечная «e»: use -> us, name -> nam (но не в коротких словах)
        if len(src) > 3 and src.endswith("e") and src[-2] not in _VOWELS:
            src = src[:-1]

    prefix = ""
    # Начальные гласные звучат иначе, чем в середине слова
    if src.startswith("e"):
        prefix, src = "э", src[1:]
    elif src.startswith("u"):
        prefix, src = "ю", src[1:]

    out, i = [prefix], 0
    while i < len(src):
        for pair, repl in _DIGRAPHS:
            if src.startswith(pair, i):
                out.append(repl)
                i += len(pair)
                break
        else:
            out.append(_SINGLES.get(src[i], src[i]))
            i += 1
    return "".join(out) + suffix


def spell_out(word: str) -> str:
    """Читает слово по буквам: CDN -> «си ди эн»."""
    return " ".join(LETTER_NAMES.get(ch, ch) for ch in word.lower() if ch.isalnum())


# camelCase -> camel Case, чтобы транслитерировать по морфемам
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

# ── окончания: tests -> «тесты», caching -> «кэшинг» ─────────────────────────
# Слова на -s, которые не множественное число: для незнакомой основы не режем.
_NOT_PLURAL = {
    "always", "perhaps", "sometimes", "towards", "besides", "afterwards", "nowadays",
    "this", "his", "its", "yes", "does", "goes", "says", "was", "has", "plus", "minus",
    "focus", "bonus", "status", "canvas", "bias", "chaos", "pros", "cons", "news",
    "series", "species", "means", "lens", "perhaps", "across", "unless", "whereas",
}
_ES_PLURAL = ("ches", "shes", "xes", "zes", "sses")
_NO_S_STEM = ("ss", "us", "is", "os", "as")
_RU_VOWELS = "аеёиоуыэюя"
_SIBILANTS = "кгхжшчщ"


def _plural(ru: str) -> str:
    """Русское окончание множественного числа к заимствованному слову."""
    if " " in ru or not ru:
        return ru                        # «эй пи ай», «ай ди» — не склоняются
    last = ru[-1]
    if last in "ья":
        return ru[:-1] + "и"             # модуль -> модули, версия -> версии
    if last == "а":
        return ru[:-1] + ("и" if ru[-2:-1] in _SIBILANTS else "ы")   # фича -> фичи
    if last in _RU_VOWELS or last == "й":
        return ru                        # кофе, кей: оставляем как есть
    return ru + ("и" if last in _SIBILANTS else "ы")


def _inflect(word: str) -> str | None:
    """Слово с окончанием -s/-es/-ies/-ing/-ed по известной основе, иначе None."""
    if re.fullmatch(r"[A-Z]{2,5}s", word):
        return _render_word(word[:-1])   # APIs -> «эй пи ай», UIs -> «юай»
    w = word.lower()
    if not w.isalpha():
        return None

    if len(w) >= 3 and w.endswith("s"):
        stems = [w[:-1]]
        if w.endswith(_ES_PLURAL):
            stems.append(w[:-2])
        if w.endswith("ies"):
            stems.append(w[:-3] + "y")
        for stem in stems:
            if stem in TERMS:
                return _plural(TERMS[stem])
        # Основы нет в словаре — транслитерируем её, но только для очевидных случаев
        if len(w) >= 5 and w not in _NOT_PLURAL and not w.endswith(_NO_S_STEM):
            return _plural(translit(stems[-1]))
        return None

    for ending, ru in (("ing", "инг"), ("ed", "ед")):
        if len(w) >= len(ending) + 2 and w.endswith(ending):
            base = w[: -len(ending)]
            tries = [(base, ""), (base + "e", "")]
            if len(base) >= 3 and base[-1] == base[-2]:       # running -> run + н
                tries.append((base[:-1], translit(base[-1])))
            for stem, extra in tries:
                if stem in TERMS:
                    return TERMS[stem] + extra + ru
    return None


def _render_word(word: str) -> str:
    key = word.lower()
    if key in TERMS:
        return TERMS[key]
    inflected = _inflect(word)
    if inflected is not None:
        return inflected
    # Аббревиатура из заглавных: читаем по буквам
    if 1 <= len(word) <= 5 and word.isupper() and word.isalpha():
        return spell_out(word)
    # Составное имя: бьём на части и обрабатываем каждую отдельно
    parts = [p for p in _CAMEL.split(word) if p]
    if len(parts) > 1:
        return " ".join(_render_word(p) for p in parts)
    return translit(word)


# ── буквы с цифрами: S3, EC2, v2, HTTP2 ──────────────────────────────────────
_LETTERS_DIGITS = re.compile(r"([A-Za-z]+)(\d+)")


def _render_letters(letters: str) -> str:
    key = letters.lower()
    if key in TERMS:
        return TERMS[key]
    if len(letters) == 1:
        return LETTER_NAMES[key]
    if len(letters) <= 3 and (letters.isupper() or letters.islower()):
        return spell_out(letters)         # EC2 -> «и си два», mp3 -> «эм пи три»
    return _render_word(letters)


# ── апострофы: it's, don't, Claude's ─────────────────────────────────────────
CONTRACTIONS = {
    "it's": "итс", "that's": "затс", "there's": "зэрс", "here's": "хиэрс",
    "what's": "уотс", "let's": "летс", "he's": "хиз", "she's": "шиз", "who's": "хуз",
    "don't": "донт", "doesn't": "дазнт", "didn't": "диднт", "isn't": "изнт",
    "aren't": "арнт", "wasn't": "уознт", "weren't": "вернт", "can't": "кэнт",
    "won't": "воунт", "couldn't": "куднт", "shouldn't": "шуднт", "wouldn't": "вуднт",
    "haven't": "хэвнт", "hasn't": "хэзнт", "hadn't": "хэднт",
    "i'm": "айм", "i'll": "айл", "i've": "айв", "i'd": "айд",
    "you're": "юр", "you'll": "юл", "you've": "юв", "you'd": "юд",
    "we're": "виар", "we'll": "вил", "we've": "вив", "we'd": "вид",
    "they're": "зэр", "they'll": "зейл", "they've": "зейв", "they'd": "зейд",
}

# ── сокращения: e.g., i.e., etc ──────────────────────────────────────────────
_ABBREVIATIONS = [
    (re.compile(r"\be\.\s?g\.", re.I), "например"),
    (re.compile(r"\bi\.\s?e\.", re.I), "то есть"),
    (re.compile(r"\betc\b"), "и так далее"),
    (re.compile(r"\bvs\b"), "против"),       # без re.I: «VS Code» — не «против»
]


def _expand_abbreviations(text: str) -> str:
    for pattern, spoken in _ABBREVIATIONS:
        text = pattern.sub(
            lambda m, spoken=spoken: spoken.capitalize() if m.group(0)[0].isupper() else spoken,
            text,
        )
    return text


# ── токены ───────────────────────────────────────────────────────────────────
_LATIN_RUN = re.compile(
    r"[A-Za-z][A-Za-z0-9]*(?:[._-][A-Za-z0-9]+)*(?:['’][A-Za-z]{1,3})?"
)


def _render_token(token: str, mode: str) -> str:
    key = token.lower()
    if key in TERMS:
        return TERMS[key]

    m = _LETTERS_DIGITS.fullmatch(token)
    if m:
        letters, digits = m.groups()
        if mode == "dict" and letters.lower() not in TERMS:
            return token
        return f"{_render_letters(letters)} {digits}"

    # Составные вроде next.js или my-app: пробуем целиком, потом по частям
    parts = re.split(r"[._-]", token)
    if len(parts) > 1 and "_" in token and token.isupper():
        # SCREAMING_SNAKE_CASE — это слова, записанные капсом
        parts = [p.lower() for p in parts]
    if len(parts) > 1:
        rendered = [TERMS.get(p.lower()) for p in parts]
        if mode == "dict" and not any(rendered):
            return token
        return " ".join(
            r if r else (_render_word(p) if mode == "dict+translit" else p)
            for p, r in zip(parts, rendered)
            if p
        )
    if mode == "dict":
        return token
    return _render_word(token)


def latinize(text: str, mode: str = "dict+translit") -> str:
    """Заменяет латинские фрагменты на кириллическое произношение.

    mode="dict"            — только известные термины, остальное как есть
    mode="dict+translit"   — плюс транслитерация незнакомых слов
    mode="off"             — без изменений
    """
    if mode == "off":
        return text

    def repl(m: re.Match[str]) -> str:
        token = m.group(0).replace("’", "'")
        base, apostrophe, _ = token.partition("'")
        if not apostrophe:
            return _render_token(token, mode)
        if token.lower() in CONTRACTIONS:
            return CONTRACTIONS[token.lower()]
        return _render_token(base, mode)      # Claude's -> «кл+од»: притяжательное без звука

    return _LATIN_RUN.sub(repl, _expand_abbreviations(text))


def add_terms(extra: dict[str, str]) -> None:
    """Подмешивает пользовательский словарь из ~/.config/vox/lexicon.toml."""
    TERMS.update({k.lower(): v for k, v in extra.items()})
