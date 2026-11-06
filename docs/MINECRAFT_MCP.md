# MCMCP для лабораторной DJ2

Пилот 6 ноября 2026: MCMCP управляет настоящим Windows-клиентом DJ2 2.23.4,
подключённым к свежему Linux Forge-серверу в Docker. Это инструмент владельца,
не часть пользовательского лаунчера или публичного сервера. Рабочий профиль,
существующие миры и подписанные player manifests не менялись.

Focused unit: Windows и отдельный Linux Docker по **47 passed** (23 MCP transport/
ownership и 24 portable-session regression), Ruff/Black. Это mocked wire/lifecycle,
а не запуск Minecraft на Linux desktop/macOS. Настоящие игровые прогоны ниже
проведены отдельно от unit-тестов.

## Что установлено

[Закреплённый BOM](../profiles/lab/mcmcp.json) содержит официальный release
2026.11.02, источник, commit, размеры, SHA-256 JAR/Windows Orchestrator и лицензию.
SHA архива и JAR сверены с digest GitHub release assets, затем с локальными байтами.
Из архива сохранены EXE, README.md и LICENSE.txt. Старое утверждение README
об отсутствии releases не соответствует фактически опубликованному release.
Orchestrator сообщает версию `26.11.20`; это строка официального бинарника,
а не другой самостоятельно собранный выпуск.

Локальная установка: `.local/tooling/mcmcp-2026.11.02.jar`,
`.local/tooling/mcmcp-orchestrator/`, `.local/tooling/MCMCP/` (исходники),
`.local/tooling/mcmcp-orchestrator-state/mcmcp-orchestrator/` (состояние).
Последняя папка содержит roster, журнал вызовов, cache и policy; её нельзя
публиковать вместе с сырыми лабораторными данными. Это не OS credential store.

## Подключение Codex

Официальный Orchestrator — stdio MCP server; MCMCP в игре соединяется с ним
обратным loopback-соединением. Каталог доступен даже при закрытой игре, после
первого успешного подключения он сохраняет 64 игровых + 6 собственных инструментов.
HTTP endpoint оставлен только для независимой диагностики.

В локальных `.codex/config.toml` корня workspace и репозитория добавлен
`mcp_servers.omk_dj2_lab`. Файлы локальные и не коммитятся. Шаблон для другой машины:

```toml
[mcp_servers.omk_dj2_lab]
command = "C:/absolute/path/mcmcp-orchestrator.exe"
args = ["--state-dir", "C:/absolute/path/isolated-state", "--link-port", "25680", "serve"]
enabled = true
required = false
startup_timeout_sec = 60
tool_timeout_sec = 90
supports_parallel_tool_calls = false
```

`codex mcp get omk_dj2_lab` проверяет, что конфигурация обнаружена. Project config
читается только для доверенного проекта: [официальная документация Codex](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
В текущем чате набор инструментов уже был создан до изменения config:
обращение к новому серверу через resource discovery вернуло `unknown MCP server`.
Поэтому пилот выполнен настоящими MCP JSON-RPC вызовами по HTTP и stdio из Python,
но вызов инструмента из **нового native Codex tool namespace пока не подтверждён**.
После следующего открытия/переподключения чата сначала проверить `mcmcp_instances`.
Не перезапускать приложение Codex автоматически ради такой проверки.

Запускать только один Orchestrator на его link port. Диагностический пилот
останавливается перед запуском процесса Codex; два `serve` на одном порту конфликтуют.
Не менять настройки других MCP servers и не включать GUI Orchestrator параллельно.

## Ограничение доступа

В Forge `config/mcmcp.cfg` пилота: loopback HTTP `25685`, port fallback выключен,
случайный 64-hex bearer только в этом файле; reverse link включён на `25680`.
Server endpoint, companion и world-edit инструменты выключены. На Linux-сервере
MCMCP не установлен. OP выдан только одноразовому тестовому аккаунту, чтобы команды
`give`, `tp`, creative и смена измерения были обычными игровыми действиями.

В headless Orchestrator используется upstream trust-on-first-use на отдельном
loopback-порту. Это **не криптографическое подтверждение пути/PID**: их сверяем
независимо с собственным процессом и lab metadata. На этой машине все три класса
вызовов по умолчанию Deny; Allow задан только точному endpoint пилота.
Для destructive обязателен явный instance. Новый lab ID нужно отдельно проверить
и разрешить, старый Allow не должен расширяться на все будущие клиенты.

```powershell
& $mcpExe --state-dir $mcpState policy --class read-only --rule deny
& $mcpExe --state-dir $mcpState policy --class mutating --rule deny
& $mcpExe --state-dir $mcpState policy --class destructive --rule deny
& $mcpExe --state-dir $mcpState policy --require-explicit-instance true
# Только после сверки собственного UUID instance/PID/path:
& $mcpExe --state-dir $mcpState policy --instance $labEndpoint --class read-only --rule allow
& $mcpExe --state-dir $mcpState policy --instance $labEndpoint --class mutating --rule allow
& $mcpExe --state-dir $mcpState policy --instance $labEndpoint --class destructive --rule allow
```

Испытанный `serve --strict-approval` не позволил bootstrap нового клиента:
клиент виден как pending, но CLI `approve` отвергает ещё неизвестный ID; strict
снова спрашивает даже для approved. В этом выпуске не полагаемся на описанную
в upstream README процедуру headless approval. GUI approval не проверена.
Не добавлялись широкие trusted roots и не патчился upstream.

Для каждой последовательности: roster → сверка точного lab → явный `instance`
во всех вызовах → проверка постусловия. Не считать focus постоянным. Не направлять
инструменты на аккаунты игроков. Управляющий MCP и токен не отправляются на VPS.

Дополнительный `python scripts/mcmcp_lab_doctor.py` — **read-only Windows lab**
cross-check: bounded metadata, ownership marker, реальный Java path/PID, loopback,
отключённые системные HTTP proxies/redirects, MCP initialize/session и сверка
endpoint PID/name до дальнейших чтений. Он не запускает игру и не создаёт lab.
Требует приватные `.local/mcmcp-client-latest.json`, `mcp-connection.json`,
`native-validation.json` и marker, которые создавал локальный pilot worker.
При закрытой игре завершится отказом. Это диагностический прототип, не общий
инсталлятор/production CLI и не замена платформенной проверки трёх ОС.

## Что реально проверено

Два свежих клиента, два отдельных Linux server/auth scope; Core 0.2.9, сервер
4 CPU / 6 ГиБ container / 4 ГиБ heap, Temurin 8u504. Клиент установлен из
проверенного подписанного кандидата плюс явно обозначенный **test-only overlay**
MCMCP: production manifest/список разрешённых пользовательских модов не ослаблялись.

- HTTP initialize, 64 client tool schemas, PID/name, чтение игрока и инвентаря.
- Official stdio initialize, 70 инструментов, exact-instance GUI/commands/state.
- Настоящий GuiChest, инвентарь, пауза, controls, русский список 30 глав квестов;
  custom BQ widgets читаются как textFields, координатный click берётся из свежего PNG.
- Выдача предметов/XP, bedrock fixture, полёт, переход 0 → 420 (Эдем) → 0.
  Во втором прогоне структуры включены; клиент показал острова/существ, сервер
  отдельно подтвердил dimension 420 и моментальный TPS 20. Это короткая проба,
  не нагрузочный/длительный тест или приёмка всех данжей.
- GUI disconnect/rejoin: тот же UUID, 7 изумрудов и 12 уровней в сохранённом состоянии.
  Во втором прогоне большой radius ожидания вернул timeout; после него GUI уже none,
  мир загружен, позиция/XP правильные. Не засчитано как успешный readiness ответ MCP.
- Оба `client_quit` дали настоящий Java exit 0 **до** cleanup; 55 секунд наблюдения
  без новых/перезаписанных crash reports и task/fatal markers. Linux stop exit 0,
  OOM=false; свои volumes/auth удалены после world export.
- После закрытия игры roster сообщает knownButNotRunning, каталог сохраняется,
  игровой вызов отвергается. Это проверено также при следующем запуске Orchestrator.

При закрытии stdio stdin официальный Orchestrator в пилоте и повторном startup
check завершился с кодом 1; сохранено в evidence как ограничение upstream.
Это отдельный процесс управления, не exit игры: оба клиента и Linux-сервера
завершились с кодом 0. GUI lifecycle Orchestrator и Linux/macOS клиенты не проверены.

Санитизированный [протокол](validation/dj2-mcmcp-2026-11-06.json) хранит SHA сырого
evidence. Полные запросы/PNG/логи/экспорты лежат только в `.local/mcmcp-client-<run>/`
и `.local/tooling/mcmcp-orchestrator-state/`. Там могут быть чат, NBT и квестовые
тексты; не публиковать их целиком. Журналы MCMCP не заменяют серверную диагностику.
Пока нет автоматического общего retention этих **lab** артефактов: очищать только
свои завершённые lab по согласованному storage plan, не чужие volumes/миры.

## Найденные ограничения и продолжение плана

1. Конфликт K BetterQuesting/Galacticraft: после снятия очков через controls
   обычная K открывает книгу. MCP binding/raw K всё равно не создают эквивалентное
   событие; одной клавишей нельзя доказывать отсутствие GUI. #86 — исправление
   initial defaults с сохранением личных привязок. В пилоте менялся только lab.
2. `client_run_commands` может вернуть `isError=false` с per-command error/no_reply.
   Смена измерения не всегда пишет ответ; посторонний AFK-чат не доказывает успех.
   Проверять GUI, координаты/инвентарь и независимо сервер. `fill air` на уже пустом
   месте может считаться ошибкой; строить пол **перед** телепортацией.
3. `/mcmcp restart` не зарегистрирована на клиенте remote-server, это серверная
   команда. Для смены reverse config нужен перезапуск клиента.
4. Первый command-fixture имел `generate-structures=false`, поэтому второй прогон
   выполнен на свежем мире с true. Recurrent Complex всё равно пишет о population
   в Эдеме и compatibility mode; это не crash и не доказанная потеря структур.
   Проверку обязательных структур внести в #37 **до** массовой предгенерации.
   Пустые колонки сами по себе нормальны для летающих островов: stopped MCA первого
   мира подтвердил реально непустые секции в других чанках.
5. #85 — ограниченная сценарная регрессия прогрессии и база собственных заметок.
   Начать с малого пилота, затем оценить цену; не обещать полное покрытие квестов,
   машин/дюпов. Выданный предмет не подтверждает рецепт или пройденный сюжетный gate.
6. #32 — ресурсный мир и команда TP с теми же настройками КД/warmup, что `/spawn`.
   #37 — ресурсный и согласованные постоянные миры в **финальной** предгенерации;
   массовая генерация сейчас не запускалась. #35/#29/#49 и остальные P0 остаются.
