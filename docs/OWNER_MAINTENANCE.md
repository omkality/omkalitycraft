# Окно обслуживания владельца

`omk admin maintenance` штатно останавливает **один явно настроенный контейнер**
и позволяет запустить **тот же контейнер** после свежей проверенной холодной копии.
Это закрытая утилита владельца, не команда игрока и не HTTP endpoint.
Аккаунту владельца не нужен OP. Команды доступны на Windows/Linux/macOS при
локальном Linux Docker engine; игровой сервер работает внутри Linux.

Это отдельный шаг подготовки эксплуатации: он не разрешает публикацию новой
версии, запуск staged restore/reset, переключение volumes или вход игроков.
Сброс мира по-прежнему требует собственной приёмки и остаётся inspect-only.

## Настройка

Используются существующие приватные `.omk-admin/operator.toml`, `backups.toml`
и RCON credential JSON. Настройка копий описана в [COLD_BACKUPS.md](COLD_BACKUPS.md).
На Linux: каталог mode 700, TOML/JSON mode 600. Пароль — минимум 16 символов,
только в приватном credential-файле и серверном `server.properties`.
Не передавайте его в аргументах команды, env контейнера, Git или отчёте.

В `operator.toml` у сервера должен быть адаптер `recovery`:

```toml
schema = 1
[servers.dj2]
root = "../servers/dj2"
[servers.dj2.recovery]
adapter = "omk-core112-rcon-v1"
host = "127.0.0.1"
port = 25577
credential_file = "dj2-rcon.json"
```

В `.omk-admin/maintenance.toml` указывается **внутренний** RCON-порт контейнера:

```toml
schema = 1
[servers.dj2]
rcon_container_port = 25575
```

Оба номера — пример. Docker должен публиковать этот внутренний TCP-порт ровно
одним binding `127.0.0.1:<recovery.port>:<rcon_container_port>`. Проверяются
настроенный и активный Docker binding. Внутри `server.properties` нужны
канонические `enable-rcon=true` и `rcon.port=<rcon_container_port>`, без дублей.
RCON не шифруется: открывать его в Интернет нельзя. `network_mode: host`
не принимается этим адаптером.

Адаптер не предоставляет произвольное выполнение RCON-команд. На этой DJ2
обычные `fill`/`tp` через ванильный RCON обращались к миру из `RCON Client`
потока: стенд зафиксировал предупреждения Alfheim и конкурентное сохранение
чанка. Подготовка игровых тестов выполняется через штатную stdin-очередь
сервера; новые операции изменения мира должны иметь адаптер основного потока.
Восстановление аккаунта использует свою прежнюю ограниченную allowlist.

Контейнер/image pin/ownership labels/source и backup volumes берутся из
`backups.toml`. Обязательны `/srv` на named volume без вложенных overlay-mounts,
ограниченные Docker `local` logs и выключенный автоматический restart
(`restart: "no"`). Утилита не меняет эти настройки и не создаёт отсутствующие
volumes. Контейнеры из другого Docker context, remote TCP/SSH engine и
совместно используемые source volumes не допускаются.

## Рабочий порядок

Все `M`, `B` ниже — идентификаторы из JSON предыдущей команды.

```console
uv run omk admin --config .omk-admin/operator.toml maintenance plan --server dj2
uv run omk admin --config .omk-admin/operator.toml maintenance stop --operation M
uv run omk admin --config .omk-admin/operator.toml backups plan --server dj2
uv run omk admin --config .omk-admin/operator.toml backups run --operation B
uv run omk admin --config .omk-admin/operator.toml maintenance start --operation M --backup-operation B
```

`plan` не останавливает сервер: фиксирует immutable container ID, время запуска,
image/volume identities, привязку консоли, хеш runtime и политику ожидания.
Второе активное окно для того же сервера запрещено.

`stop` записывает durable intent, отправляет только штатную `stop`, ожидает
exit 0 без OOM/fatal и проверяет stop log/runtime. Онлайн-игроки отключаются
штатным серверным завершением; их прогресс сохраняет Minecraft.
Force kill, `docker rm`, удаление мира или откат не выполняются.

`start` принимает только завершённую backup-операцию **этой остановки**.
Readonly Linux helper заново проверяет архивы, последнюю копию, полное
совпадение world inventory и runtime. Старый backup, изменение файла после
копии, незавершённый staging и новый контейнер/volume блокируют запуск.
Используется `docker start <frozen ID>`, без `compose up` и замены runtime.
Новый `StartedAt` сопоставляется с предыдущим clean `FinishedAt` **того же
Docker engine**. Время host intent сохраняется только для аудита: часы
хоста и Docker VM могут немного расходиться, особенно на desktop.
В новом boot должны появиться `Done` и рабочий Core RCON adapter; затем
проверяется стабильный период готовности. Это эксплуатационная проверка
сервера, не замена входу реального графического клиента.

Существующий механизм `backups` остаётся единственным writer этого сценария.
Новое расписание/второй бэкапер не добавлены; FTB backups эта команда сама
не перенастраивает. Выбор и проверка одного периодического writer остаются
отдельной задачей #33 перед production.

## Если утилита прервалась

```console
uv run omk admin --config .omk-admin/operator.toml maintenance status --operation M
uv run omk admin --config .omk-admin/operator.toml maintenance reconcile --operation M
```

Журналы находятся **рядом с приватным operator config**:
`.omk-admin/maintenance/<operation>.json`; общий CLI-аудит —
`.omk-admin/audit.jsonl`. Password, game tokens, Docker Env/Args и содержимое
`server.properties` в них не выводятся. Общая блокировка `backups.lock`
не даёт параллельно менять состояние через owner backup/restore/reset CLI.

| Stage | Действие владельца |
| --- | --- |
| `planned` | `stop` в пределах TTL или `cancel` без остановки |
| `stop-requested` | Проверить контейнер и вызвать `reconcile`: подтвердить уже завершённую штатную остановку |
| `stopped` | Сделать backup и `start`, либо `cancel`, оставив сервер выключенным |
| `start-requested` | Проверить контейнер/logs и `reconcile`: подтвердить уже начатый запуск |
| `complete` / `cancelled` | Операция закрыта, новое обслуживание требует нового плана |

`reconcile` не повторяет `stop`/`start` и не делает ещё одну копию.
Если процесс погиб **до отправки** lifecycle-команды, или сервер завершился
аварийно, intent останется неподтверждённым. Нужна проверка владельца через
консоль/Docker; не редактируйте JSON ради обхода проверки. Автоматического
force kill, отмены неопределённого intent или rollback после failed start нет.
Изменившиеся config/контейнер/volume также требуют разбирательства.

Утилита координирует собственные команды. Она не блокирует сторонний Docker
CLI, редактирование файлов или посторонний scheduler; их надо исключить
на время обслуживания. При обнаруженном изменении операция отказывает.

## Настраиваемые пределы

| Переменная | По умолчанию | Диапазон |
| --- | ---: | ---: |
| `OMK_MAINTENANCE_PLAN_TTL_SECONDS` | 3600 | 60–86400 |
| `OMK_MAINTENANCE_STOP_TIMEOUT_SECONDS` | 120 | 10–600 |
| `OMK_MAINTENANCE_START_TIMEOUT_SECONDS` | 600 | 10–1800 |
| `OMK_MAINTENANCE_READY_STABLE_SECONDS` | 15 | 5–120 |
| `OMK_MAINTENANCE_POLL_MILLISECONDS` | 500 | 100–5000 |
| `OMK_MAINTENANCE_JOURNAL_COUNT` | 128 | 8–1000 |

Политика фиксируется в плане. Timeout не считается успешной остановкой или
готовностью. Старые terminal-журналы владелец архивирует отдельно; при лимите
новый план отказывает, история незавершённых операций не удаляется.
Readonly helper наследует CPU/RAM/timeout/объёмные пределы `OMK_BACKUP_*`.
Настройки не требуют коммитов, пароль не является env override.

## Проверенная область — 11 ноября 2026

Полная DJ2 2.23.4 / Forge 1.12.2 в Linux Docker: 34 native и 60 независимых
условий, три clean старта/stop, два Drasl-аккаунта и две копии. После возврата
того же контейнера игроки входят с прежними UUID, Inventory и XP. Независимый
аудит читает фактические ZIP/TAR и проверяет все файлы/CRC/SHA, а не только
успешный JSON команды. Прерывания после stop/start, старая копия, повторное
окно и cancel проверены отдельно. Прогресс сохранялся сервером, графический
клиент этим опытом не аттестуется.

51 synthetic тестов дополняют game-проход отказами конфигурации/портов,
изменением runtime/world/архива, ошибкой Docker после start, поздним fatal и
неустойчивой готовностью. Есть отдельный real Docker + fake RCON контроль.
Пять ранних непринятых прогонов и пределы сохранившихся доказательств отражены
в [протоколе](validation/dj2-owner-maintenance-2026-11-11.json).
