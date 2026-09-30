# vox

Reads Claude Code answers and markdown files aloud with local TTS engines.
Nothing leaves the machine: synthesis runs entirely on device.

Built for Russian speech: the voices are Russian, and the text pipeline
rewrites the Latin-heavy output of a coding assistant into something a Russian
voice can pronounce. English documents are detected and read with an English
system voice.

```
/say                    read the last Claude Code answer
/say README.md          read a file
/say stop               interrupt
vox notes.md            the same from the terminal
```

Long answers (600+ characters by default) are read automatically, short ones
are not.

## Why a separate tool

You cannot feed a Claude Code answer straight into a synthesizer: you get
"backtick es er see slash app slash page dot tee es ex backtick". Most of what
vox does is rewriting markdown so it is pleasant to listen to:

| In the text | What you hear |
|---|---|
| ` ```ts … ``` ` (12 lines) | «Далее код на тэ эс, 12 строк» — "code in ts follows, 12 lines" |
| a 5-row table | «Далее таблица, 5 строк» — "a table follows, 5 rows" (or row by row) |
| `src/app/components/Hero.tsx` | «Хиро тэ эс икс» — just the file name |
| `next.config.mjs:12` | «некст конфиг эм джей эс, строка 12» — "…, line 12" |
| `[docs](https://…)` | the link text only |
| `- [x] Done` | «сделано: Done» — "done: …" |
| `**SSR**`, `CDN`, `pnpm` | «эс эс эр», «си ди эн», «пи эн пи эм» — spelled out |

Latin script is converted to Cyrillic because Russian voices cannot read it:
first a dictionary of ~250 technical terms, then letter-by-letter spelling for
unknown acronyms, and phonetic transliteration for whatever is left.

## Engines

| | `say` (default) | `silero` |
|---|---|---|
| quality | average | noticeably more natural |
| time to first sound | ~50 ms | ~3 s (model warm-up) |
| dependencies | none | torch in its own venv, ~700 MB |
| voices | Milena, Samantha (English) | aidar (default), baya, kseniya, xenia, eugene |
| rate / pitch | `rate` | `rate` → slow/medium/fast, `pitch` in config |

`say` streams synthesis itself, so audio starts instantly. Silero synthesizes
in chunks: while chunk N plays, chunk N+1 is being generated, so a long answer
starts sounding almost immediately instead of after the whole text is
processed. Text goes to Silero as SSML: rate and pitch through `<prosody>`,
paragraph pauses through `<break>` inside the audio, so there are no seams
between chunks. Silero only understands named rate values, so `rate` is
rounded: 100 → x-slow, 160 → slow, 200 → medium, 240 → fast, 300 → x-fast.

Install Silero: `vox setup silero` (needs `uv`: `brew install uv`).
Switch: `engine = "silero"` in the config or the `--engine silero` flag.

**Install the enhanced macOS voice.** The stock Milena is old and robotic.
System Settings → Accessibility → Spoken Content → System Voice → Manage
Voices → Russian → **Milena (Enhanced)**. The difference is large.

## Commands

```
vox                        the last Claude Code answer
vox FILE…                  markdown or text files
cat x.md | vox             from stdin
vox --last / --turn        final text / all prose of the last turn
vox --any-dir              no session in this folder — take the newest from any project
vox --dry-run              print what would be read and exit
vox --out speech.wav       write to a file instead of speaking
vox --engine silero -r 180 one-off engine and rate override
vox stop                   interrupt
vox on / vox off           enable / disable auto-reading
vox status                 what is configured and what is playing
vox doctor                 environment check
vox config                 open the config in an editor
```

Only one thing is read at a time: a new reading silences the previous one.

The answer is taken from the Claude Code session running in the current
folder (or one that started in a parent folder and `cd`'d into it). vox never
silently reads another project's session — only with `--any-dir`.

## Config

`~/.config/vox/config.toml` — engine, voice, rate, auto-read threshold, what to
do with code blocks and tables (`announce` | `skip` | `read`). Silero-specific:
`pitch` (`x-low` … `x-high`, there is even `robot`), `sample_rate` (48000 is the
best quality and the default) and `put_accent` (automatic stress marks and ё).

`~/.config/vox/lexicon.toml` — your own pronunciations, override the built-in
dictionary:

```toml
[terms]
myapp = "майапп"
hetzner   = "хетцнер"
```

## How it works

```
hooks/stop-speak.py   Stop hook: launches vox in the background and exits (~50 ms)
commands/say.md       slash command /vox:say (the /say alias lives in ~/.claude/commands)
bin/vox               CLI, works without Claude Code too
src/vox/textnorm.py   markdown -> speakable text
src/vox/lexicon.py    term dictionary and transliteration
src/vox/chunker.py    splitting into chunks for streaming synthesis
src/vox/engines/      say and silero
src/vox/player.py     one voice at a time, stop by signal
```

Every decision about reading (is auto mode off, is the text long enough) is
made by `vox --auto`, not by the hook — so the hook stays trivial and fast.

The CLI has no dependencies, only the Python 3.11+ standard library.

## Tests

```sh
python3 -m unittest discover -s tests -t .     # stdlib, no dependencies
python3 -m pytest -q                           # works too
```

Tests are isolated: each gets its own `XDG_*` and `HOME`; the real config,
state and cache are never touched. No audio is played and torch is not needed
— the Silero worker is tested against a stub.

## Install and update

One command after cloning:

```sh
git clone git@github.com:snowtema/vox.git ~/Develop/vox
sh ~/Develop/vox/install.sh              # or --no-silero if the system say is enough
```

The script installs the CLI into `~/.local/bin`, the `/say` alias, the Claude
Code plugin, and then Silero: `uv` (via brew if missing), a venv with torch
(~700 MB) and the model (~60 MB). Requires only macOS and python3 3.11+.
Re-running is safe and updates the plugin. `vox doctor` shows the result.

The same by hand:

```sh
ln -sf ~/Develop/vox/bin/vox ~/.local/bin/vox     # CLI in PATH
claude plugin marketplace add ~/Develop/vox       # plugin: /vox:say and the Stop hook
claude plugin install vox@vox-local
vox setup silero                                  # optional
```

Plugin commands get a prefix, so inside the plugin the command is `/vox:say`.
The short `/say` is a separate user-level alias, `~/.claude/commands/say.md`,
with the same content as `commands/say.md` but calling `$HOME/.local/bin/vox`
instead of `${CLAUDE_PLUGIN_ROOT}/bin/vox`.

Claude Code copies the plugin into its cache, keyed by version. After changing
code, bump `version` in `.claude-plugin/plugin.json` and `marketplace.json`,
then:

```sh
claude plugin marketplace update vox-local
claude plugin update vox@vox-local                 # and restart Claude Code
```

The terminal `vox` runs through a symlink and picks up changes immediately,
no update needed. The config and lexicon live outside the plugin
(`~/.config/vox/`), so editing them requires no update either.

Turn it off entirely: `claude plugin disable vox` — or `vox off` to silence
only the automatic reading.
