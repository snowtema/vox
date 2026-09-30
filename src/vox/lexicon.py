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
    "hetzner": "хетцнер", "wrangler": "рэнглер", "workers": "воркерс",
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
    "assets": "ассетс", "styles": "стайлс", "scripts": "скриптс",
    "main": "мейн", "dev": "дев", "preview": "превью", "watch": "вотч",
    "clean": "клин", "check": "чек", "format": "формат", "serve": "сёрв",
    "hero": "х+иро", "plugin": "пл+агин", "plugins": "пл+агины", "root": "рут", "bin": "бин",
    "path": "пас", "dir": "дир", "home": "хоум", "vox": "вокс",
    "skill": "скилл", "skills": "скиллы", "agent": "+эйджент", "agents": "+эйдженты",
    "subagent": "саб+эйджент", "session": "с+ешн", "prompt": "промпт",
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

    # Немая конечная «e»: use -> us, name -> nam (но не в коротких словах)
    if len(src) > 3 and src.endswith("e") and src[-2] not in _VOWELS:
        src = src[:-1]

    prefix = ""
    # Начальные гласные звучат иначе, чем в середине слова
    if src.startswith("e"):
        prefix, src = "э", src[1:]
    elif src.startswith("u"):
        prefix, src = "ю", src[1:]

    suffix = ""
    for tail, repl in _SUFFIXES:
        if len(src) > len(tail) + 1 and src.endswith(tail):
            suffix, src = repl, src[: -len(tail)]
            break

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


def _render_word(word: str) -> str:
    key = word.lower()
    if key in TERMS:
        return TERMS[key]
    # Аббревиатура из заглавных: читаем по буквам
    if 1 <= len(word) <= 5 and word.isupper() and word.isalpha():
        return spell_out(word)
    # Составное имя: бьём на части и обрабатываем каждую отдельно
    parts = [p for p in _CAMEL.split(word) if p]
    if len(parts) > 1:
        return " ".join(_render_word(p) for p in parts)
    return translit(word)


_LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[._-][A-Za-z0-9]+)*")


def latinize(text: str, mode: str = "dict+translit") -> str:
    """Заменяет латинские фрагменты на кириллическое произношение.

    mode="dict"            — только известные термины, остальное как есть
    mode="dict+translit"   — плюс транслитерация незнакомых слов
    mode="off"             — без изменений
    """
    if mode == "off":
        return text

    def repl(m: re.Match[str]) -> str:
        token = m.group(0)
        key = token.lower()
        if key in TERMS:
            return TERMS[key]
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

    return _LATIN_RUN.sub(repl, text)


def add_terms(extra: dict[str, str]) -> None:
    """Подмешивает пользовательский словарь из ~/.config/vox/lexicon.toml."""
    TERMS.update({k.lower(): v for k, v in extra.items()})
