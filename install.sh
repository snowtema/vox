#!/bin/sh
# Установка vox одной командой после клонирования:
#
#   sh install.sh               CLI в PATH, алиас /say, плагин Claude Code, движок Silero
#   sh install.sh --no-silero   то же без Silero (останется системный say)
#
# Скрипт идемпотентен: повторный запуск ничего не ломает и обновляет плагин.

set -eu

root=$(cd "$(dirname "$0")" && pwd)
with_silero=1
for arg in "$@"; do
    case $arg in
        --no-silero) with_silero=0 ;;
        -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
        *) echo "install.sh: неизвестный аргумент $arg" >&2; exit 2 ;;
    esac
done

say()  { printf '\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  ✓  %s\n' "$*"; }
warn() { printf '  !  %s\n' "$*"; }
die()  { printf '  ✗  %s\n' "$*" >&2; exit 1; }

# ── 1. окружение ─────────────────────────────────────────────────────────────
say "Проверяю окружение"
[ "$(uname -s)" = Darwin ] || warn "не macOS: движок say и afplay недоступны, останется только --out"

command -v python3 >/dev/null || die "нужен python3 3.11+ — brew install python"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
    || die "python3 старше 3.11 ($(python3 --version 2>&1)) — brew install python"
ok "python3 $(python3 -c 'import platform; print(platform.python_version())')"

# ── 2. CLI в PATH ────────────────────────────────────────────────────────────
say "Ставлю CLI"
mkdir -p "$HOME/.local/bin"
ln -sf "$root/bin/vox" "$HOME/.local/bin/vox"
ok "~/.local/bin/vox → $root/bin/vox"
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) warn "~/.local/bin не в PATH — добавь в ~/.zshrc:  export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

# ── 3. алиас /say (команда плагина называется /vox:say) ──────────────────────
mkdir -p "$HOME/.claude/commands"
sed 's|\${CLAUDE_PLUGIN_ROOT}/bin/vox|$HOME/.local/bin/vox|' "$root/commands/say.md" \
    > "$HOME/.claude/commands/say.md"
ok "~/.claude/commands/say.md (алиас /say)"

# ── 4. плагин Claude Code: Stop-хук и /vox:say ───────────────────────────────
say "Регистрирую плагин Claude Code"
if command -v claude >/dev/null; then
    if claude plugin marketplace add "$root" >/dev/null 2>&1; then
        ok "маркетплейс vox-local добавлен"
    else
        claude plugin marketplace update vox-local >/dev/null 2>&1 && ok "маркетплейс vox-local обновлён" \
            || warn "не удалось добавить маркетплейс: claude plugin marketplace add $root"
    fi
    if claude plugin install vox@vox-local >/dev/null 2>&1; then
        ok "плагин vox установлен"
    else
        warn "не удалось поставить плагин: claude plugin install vox@vox-local"
    fi
    # install на уже стоящем плагине — no-op: новую версию из кеша подтягивает только update
    claude plugin update vox@vox-local >/dev/null 2>&1 \
        && ok "плагин vox обновлён до $(python3 -c "import json;print(json.load(open('$root/.claude-plugin/plugin.json'))['version'])")" \
        || warn "не удалось обновить плагин: claude plugin update vox@vox-local"
    warn "перезапусти Claude Code, чтобы хук и /say подхватились"
else
    warn "claude не найден в PATH — плагин поставь позже:"
    warn "  claude plugin marketplace add $root && claude plugin install vox@vox-local"
fi

# ── 5. Silero ────────────────────────────────────────────────────────────────
if [ "$with_silero" = 1 ]; then
    say "Ставлю движок Silero (torch в отдельном venv, ~700 МБ)"
    if ! command -v uv >/dev/null; then
        if command -v brew >/dev/null; then
            brew install uv
        else
            die "нужен uv (brew install uv) или поставь без Silero: sh install.sh --no-silero"
        fi
    fi
    "$root/bin/vox" setup silero
    cfg="${XDG_CONFIG_HOME:-$HOME/.config}/vox/config.toml"
    # setup выше уже создал конфиг; переключаем движок, только если стоит say
    sed -i '' 's/^engine *= *"say"/engine    = "silero"/' "$cfg"
    ok "engine = \"silero\" в $cfg"
else
    say "Silero пропущен (--no-silero) — работает системный say"
fi

# ── 6. итог ──────────────────────────────────────────────────────────────────
say "Проверка"
"$root/bin/vox" doctor || true
echo
echo "Готово. Попробуй:  vox README.md   или в Claude Code:  /say"
