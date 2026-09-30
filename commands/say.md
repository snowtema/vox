---
description: Озвучить последний ответ Claude Code или указанный файл
argument-hint: [файл.md | stop | on | off | status]
allowed-tools: Bash(sh:*)
disable-model-invocation: true
---

!`sh "${CLAUDE_PLUGIN_ROOT}/bin/vox" --detach $ARGUMENTS`

Команда уже выполнена — вывод выше. Ответь одной короткой строкой: что
озвучивается (или что остановлено / переключено). Ничего не пересказывай,
никаких инструментов не вызывай.
