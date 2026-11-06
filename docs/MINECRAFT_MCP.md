# MCMCP для лабораторной DJ2

## Постоянная установка и повторяемый стенд

После первого пилота установлен официальный desktop Orchestrator 26.11.20 в
`.local/tooling/mcmcp-desktop/` (installer и оба EXE закреплены в BOM ниже).
В пользовательском `~/.codex/config.toml` и локальных project configs зарегистрирован
`omk_dj2_lab` через **shim**, а не отдельный `serve` для каждого чата. Проверены два
одновременных shim: каждый видит 70 tools, оба завершаются с exit 0, приложение
продолжает работать. Состояние остаётся внутри проекта. Автозапуск при входе в
Windows отдельно не включался; официальный shim поднимает приложение по требованию.
`.local/tooling/` — постоянная установка, её нельзя удалять вместе с отдельными
завершёнными `mcmcp-client-*` scopes. После переноса проекта нужно обновить абсолютные
пути в Codex config.

Финальный повторяемый worker прошёл один Linux server start и два Windows client
start: настоящая K открыла квесты на чистых настройках, после редактирования только
остановленных lab-файлов сохранились F10/F8 и Circle/grid. Настоящая F10 снова
открыла GUI. UUID/7 изумрудов/12 уровней подтверждены клиентом и независимым reader
сохранённого NBT. Оба exit 0, по 55 секунд без новых reports; Linux stop 0/OOM=false,
свои volume/auth/разрешения MCP очищены. K/F12 и Square/no-grid восстановлены только
в остановленном lab после проверки; рабочие пользовательские файлы не менялись.
[Санитизированный протокол](validation/dj2-persistent-mcmcp-2026-11-06.json).

`omk lab dj2-mcp --help` описывает постоянную команду стенда. Нужны явные пути к
проверенному подписанному release-dir/публичным ключам и его ожидаемый digest,
server-source, approved player mods, private Core, authlib-injector, MCMCP JAR,
Orchestrator CLI и отдельному state-dir внутри `.local`. Пример для этого workspace:

```powershell
python -m omk lab dj2-mcp `
  --release-dir .local/dj2-update-b7bf0b8afca6/content/releases/dj2/windows-x64 `
  --trusted-public-keys .local/dj2-update-b7bf0b8afca6/trusted-public-keys.json `
  --expected-release-sha256 d93a7b974de0434be24e03f9b7edbfc5c0925df19d12a6faeb1d5866363f2084 `
  --server-source .local/dj2-target-core028-d78c2856f5/server `
  --mods-json .local/dj2-rendered-c2e79626ea/approved-real-client-mods.json `
  --core ../omkalitycore/build/OmkalityCore-0.2.9.jar `
  --agent data/content/releases/dj2/windows-x64/files/agent/authlib-injector-1.2.8.jar `
  --mcmcp-jar .local/tooling/mcmcp-2026.11.02.jar `
  --orchestrator-cli C:/Users/omka/Projects/minecraft_server/omkalitycraft/.local/tooling/mcmcp-desktop/mcmcp-orchestrator.exe `
  --orchestrator-state C:/Users/omka/Projects/minecraft_server/omkalitycraft/.local/tooling/mcmcp-orchestrator-state `
  --client-defaults profiles/client-defaults/dj2.json
```

Это Windows x64 client + Linux Docker server; другие графические ОС не объявляются
готовыми. MCP порты задаются `--client-port`, `--link-port`, `--bridge-port`;
Minecraft/Drasl используют существующий contract стенда 25576/25586. При занятом
порту чужой процесс не останавливается. `--duration-minutes` ограничивает сессию
(default 90, максимум 180); превышение времени — незавершённый, а не успешный тест.

Новый worker всегда делает свежую установку/мир/auth, явно добавляя test-only
MCMCP overlay. Необязательный `--client-defaults` — отдельный тестовый override с
SHA в отчёте; исходная подпись не изменяется и такой overlay нельзя выдавать игрокам.
Пол строится до первого входа, структуры включены. Рабочие миры не копируются.

Последний scope указан в `.local/mcmcp-client-latest.json`; отчёт —
`native-validation.json`, endpoint — `instance_endpoint` из него. До управления
проверять roster и фактические PID/path/name. `scripts/mcmcp_lab_doctor.py` сверяет
HTTP endpoint с собственным процессом. Секреты только в game cfg/состоянии shim.
Endpoint появляется раньше завершения Forge loading: перед игровыми действиями
нужны worldLoaded/playerPresent и ожидаемый GUI. Таймаут main-thread задачи во время
первоначальной загрузки сам по себе не является крашем.

Управление worker: JSON `native-control.json` в его lab, `action=console` и массив
`commands` (1–24 коротких строки), либо `action=restart-client` **после** штатного
`client_quit` и наблюдаемого exit 0. Restart сохраняет тот же тестовый мир/аккаунт,
снова применяет defaults, поэтому годится для проверки личных настроек.
`native-finish` принимает только штатно закрытые клиенты; перед ним отдельно
проверять логи/постусловия и выдерживать окно наблюдения. `native-stop` означает
незавершённую проверку. Cleanup останавливает только свои server/auth, экспортирует
мир и удаляет свой volume лишь после успешного clean export.

Desktop Orchestrator этого выпуска не перечитывает CLI policy во время работы.
Поэтому worker проверяет отсутствие подключённых игр, точные hashes обоих EXE,
PID обоих loopback listeners и state/port environment, затем обновляет **только
бездействующее управляющее приложение**. Перед остановкой roster проверяется
повторно. Это не атомарная блокировка появления стороннего клиента; проверки
снижают риск гонки, но не дают такой гарантии. Игра/сервер этой операцией не
останавливаются. При обнаружении другого активного мира операция отказывает.
После cleanup удаляется точный trusted-root и policy этого lab переводится в Deny,
затем то же обновление делает отказ действующим. Ошибка cleanup не считается успехом.

JSONL reader использует неблокирующий pipe Python 3.14 с timeout и лимитом 16 МиБ:
закрытие фонового reader-потока при перезапуске приложения могло зависать.
Источник поведения pipes: [Python os.set_blocking](https://docs.python.org/3.14/library/os.html#os.set_blocking).

## Первый пилот: границы исходной проверки

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

В локальных `.codex/config.toml` корня workspace, репозитория и пользовательском
config зарегистрирован `mcp_servers.omk_dj2_lab`. Они не коммитятся. Текущий шаблон:

```toml
[mcp_servers.omk_dj2_lab]
command = "C:/absolute/path/mcmcp-orchestrator.exe"
args = ["--state-dir", "C:/absolute/path/isolated-state", "shim", "--mcp-port", "25681"]
enabled = true
required = false
startup_timeout_sec = 60
tool_timeout_sec = 90
supports_parallel_tool_calls = false

[mcp_servers.omk_dj2_lab.env]
MCMCP_ORCHESTRATOR_HOME = "C:/absolute/path/isolated-state"
MCMCP_LINK_PORT = "25680"
MCMCP_MCP_PORT = "25681"
```

`codex mcp get omk_dj2_lab` проверяет, что конфигурация обнаружена. Project config
читается только для доверенного проекта: [официальная документация Codex](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
В текущем чате набор инструментов уже был создан до изменения config:
обращение к новому серверу через resource discovery вернуло `unknown MCP server`.
Поэтому пилот выполнен настоящими MCP JSON-RPC вызовами по HTTP и stdio из Python,
но вызов инструмента из **нового native Codex tool namespace пока не подтверждён**.
После следующего открытия/переподключения чата сначала проверить `mcmcp_instances`.
Не перезапускать приложение Codex автоматически ради такой проверки.

Один desktop Orchestrator владеет link/bridge ports; несколько официальных shim
подключаются к нему одновременно. Не запускать старый `serve` на том же порту.
При добавлении config через CLI обнаружена нормализация чужой node_repl-записи;
её исходные настройки восстановлены побайтно из приватной копии. Финальная запись
добавлена без изменения остальных настроек Codex; конфигурационные backup не в Git.

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
