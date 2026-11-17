# Терминал владельца: первый рабочий срез

`tui/` — native Rust/Ratatui клиент существующих Python services. Открывается
локально на машине владельца или в SSH-терминале на будущем VPS. Отдельный
backend daemon, HTTP API администрирования и scheduler не нужны. Доступ определяется
правами к private operator config; player launcher этого интерфейса не получает.

## Что можно делать

- Видеть CPU/RAM Linux Docker host, занятое место файловой системы проекта.
- Видеть TPS, среднее время tick и число игроков выбранного сервера.
- Смотреть график TPS за последние 5/15 минут, 1/3 часа с обновлением 5 s.
- Запросить `list uuids` и `forge tps` через прежний loopback RCON transport.
- Отправить `save-all flush`, введя `SAVE <server-id>` в диалоге подтверждения.
- Выбрать allowlisted сервер и посмотреть последние live backup/maintenance/restore
  journals: фазу, полный ID и признак завершения workflow.

Показатели берутся из уже реализованных Prometheus + Telegraf + server-only
cpburnz exporter, без второго сборщика и БД. В локальном Docker Desktop host —
Linux VM Docker, а не физическая Windows. Метрики CPU/RAM/диска относятся к этому
host; TPS/MSPT/игроки — к выбранному `service` того же `host`.

Пустой список операций не означает здоровый сервер. Терминальная фаза restore
`staged` не означает promotion/готовность игроков. Старые архивы journals в этот
короткий обзор не включаются; их по-прежнему можно читать через owner status CLI.
Живые записи могут измениться между чтениями: обзор не является atomic snapshot.

## Сборка и запуск

Нужны Rust **1.93.1** с `rustfmt/clippy`, Python **3.14.2** и зависимости проекта.
Для native Windows Rust нужен C++ linker из Visual Studio Build Tools; Linux/macOS
используют свой native toolchain. Из корня репозитория:

```console
uv sync --locked --no-default-groups --group shared --group dev
cargo +1.93.1 build --manifest-path tui/Cargo.toml --locked --release -j 4
```

Linux, запуск на том же owner host, где находятся config и loopback endpoints:

```console
./tui/target/release/omk-tui --repo /opt/omk --python /opt/omk/.venv/bin/python --config /opt/omk/.omk-admin/operator.toml
```

Windows PowerShell, из корня своего checkout:

```powershell
.\tui\target\release\omk-tui.exe --repo "$PWD" --python "$PWD\.venv\Scripts\python.exe" --config "$PWD\.omk-admin\operator.toml"
```

TUI не содержит SSH-клиента. Для VPS сначала входим по SSH и запускаем Linux binary
там: RCON/Prometheus сохраняют loopback binding. Ничего публично не публикуем.

```console
cargo +1.93.1 run --manifest-path tui/Cargo.toml --locked -- --demo
```

В демо используются явно помеченные синтетические данные, команды отключены.
`--snapshot <file.svg>` сохраняет отрисовку настоящих widgets в TestBackend 120×38,
без открытия терминала. С `--config` snapshot читает реальный Python backend;
с `--demo` он остаётся демо. Это не снимок настоящего terminal emulator.

## Частная конфигурация

Для двух небольших постоянно работающих тестовых серверов есть отдельный
[локальный sandbox](../deploy/tui-lab/README.md): `lab-alpha` и `lab-beta`,
с ограниченными периодическими CPU-всплесками и настоящим мониторингом.
Запускается только по явному запросу владельца; автоматического stop/cleanup нет.

Прежний `operator.toml`: allowlist `[servers.<id>]`, корень и `[servers.<id>.recovery]`
с loopback портом и `credential_file`. Формат RCON credential: `{"password":"…"}`,
как в существующих owner services. Для save нужны именно права консоли владельца;
игровой OP игрокам не требуется. Пароль не передаётся в argv/Rust и не печатается.

Необязательная `.omk-admin/tui.json`, mode 600 на Unix:

```json
{"schema":1,"prometheus_origin":"http://127.0.0.1:9090","host":"omk-pl"}
```

`host` должен совпадать с `metrics.json`, `service` игрового scrape — с server ID.
Допускается только явный loopback HTTP origin с port 1024..65535. Redirects и
environment proxies выключены. Исходные exporter endpoints остаются в частной
Docker network. Нет файла — «мониторинг не подключён»; нет series/экспортера —
«нет данных». Нули показываются только при настоящем свежем измерении.

Запрос Prometheus ограничен 3 s / 64 KiB / 128 series. `up == 1` обязателен;
samples старше 90 s, отрицательные/NaN/Inf или неоднозначные labels не становятся
числом. CPU берётся по `cpu-total`, диск — `/storage/project`. Изменение инфраструктуры
отражаем в private monitoring config, не подставляем другие узлы автоматически.

## Управление и ошибки

`←/→` — сервер, `↑/↓` — операция, `1` — игроки, `2` — Forge TPS, `3` — сохранение,
`r` — чтение обзора, `q`/`Ctrl+C` — выход. Минимальное окно 84×28. Диалог save
закрывается по `Esc`, `PgUp/PgDn` прокручивают ответ консоли. Автообновление
обзора и графика каждые 5 s не отправляет команды. `t` открывает выбор периода:
`↑/↓`, затем `Enter`; `Esc` отменяет выбор. Период сохраняется при переключении
серверов в этой сессии. `--window 5m|15m|1h|3h` задаёт начальный период (default 5m).
`F1` открывает карточку проекта;
`F1`/`Esc` закрывает её и возвращает к графику.

По выбору владельца используется вариант Б: при высоте окна от 34 строк в шапке
показывается плоская квадратная руда без подписи, без перспективы куба. Исходная текстура
32×32 извлечена без перерисовки из локального DivineRPG 1.7.1;
[происхождение и SHA256](../tui/assets/provenance.json). В шапке она занимает
16 столбцов × 8 строк half-block cells; большая карточка — 32 × 16. Физические
пропорции зависят от шрифта терминала. PNG лаунчера прежний. Генератор
`scripts/tui_branding.py` сохраняет пиксельный рисунок через nearest resampling,
CI сверяет Rust cells с PNG. `--compact-header` отключает руду в шапке;
`--about` открывает карточку сразу. На меньшей высоте шапка компактная автоматически.

Rust запускает не более **одного одновременно** дочернего Python CLI с явными argv:
обзор, затем историю TPS выбранного сервера. stdin закрыт, stderr
не показывается. Вызов ограничен 15 s и 256 KiB stdout; timeout/выход дожидается
своего процесса. Tempfile вместо pipe исключает зависший reader из-за открытого
stdout. Private stdout не сохраняется после закрытия. Неизвестная версия/поля,
нарушенные инварианты, неверный server/command или противоречивый exit code
отклоняются. Последние показания при ошибке остаются явно устаревшими.

`ok` у консольной команды означает полученный читаемый ответ, **не** независимую
проверку сохранения/backup. При отправке save его effect остаётся `unknown`:
потеря ответа не позволяет доказать, выполнил ли Minecraft команду. Повторной
отправки автоматически нет. `save-all flush` не заменяет cold backup.

## Контракты и проверки

`omk admin --config <path> overview [--server <id>]` выдаёт отдельный
`owner.overview` schema 1; [JSON schema](contracts/owner-overview-v1.schema.json).
Не меняет прежний [owner result v1](OWNER_RESULT.md): его 15 действий и запрет
unsupported actions сохранены. `--result-version 1 overview` возвращает отказ.
Обзор читает максимум 2000 entries каждого из трёх live каталогов и проецирует
не более 128 последних записей. `skipped/truncated` видны в TUI. Не читает миры,
не запускает Docker, не берёт owner lock и не пишет audit/credentials.

`omk admin --config <path> console --server <id> --command players|tps|save`
возвращает `owner.console` schema 1. Для save обязателен `--confirm-save`.
Произвольных shell/RCON команд в этом интерфейсе нет.

`omk admin --config <path> tps-history --server <id> [--window 5m|15m|1h|3h]` возвращает отдельный
`owner.tps-history` schema 1; [JSON schema](contracts/owner-tps-history-v1.schema.json).
Это чтение `query_range` существующего Prometheus, без нового sampler/БД. Диапазон
по умолчанию 300 s; доступны также 900/3600/10800 s. Шаг соответственно 5/15/60/180 s,
максимум 61 точка, значения 0..20; правый край округляется вниз на сетку 5 s. В длинных
диапазонах берётся минимум за каждый интервал, не разреженные мгновенные значения:
короткие просадки между точками сохраняются. Интервал минимума подписан под графиком.
Если сбор данных начался позже левого края, ранние точки остаются пустыми. Проверяются
server/host, порядок и точная сетка времени, конечность значений и единственность
series. `up == 1` и свежесть проверяются в каждой исторической точке. Отсутствующие
измерения дают `null` и разрыв линии, настоящий ноль остаётся нулём. Ошибка чтения
не стирает уже полученную кривую того же сервера и периода: она приглушается и помечается
устаревшей, а правый край оси подписывается «последний ответ». При смене сервера
чужая кривая не показывается. `--result-version 1 tps-history` отклоняется;
прежние overview/console и 15 действий owner result v1 сохраняют свои схемы.

```console
uv run --no-sync python scripts/check_owner_tui.py
uv run --no-sync pytest tests/unit/test_owner_tps_history.py tests/unit/test_owner_overview.py tests/unit/test_owner_metrics.py tests/unit/test_owner_console.py tests/unit/test_recovery_console.py tests/unit/test_owner_result.py -q -n 4 --dist=loadfile
```

Rust проверяет Python examples, строгий разбор, корреляцию, пустые/устаревшие данные,
resize, timeout/oversize/exit и настоящий CLI с временным config. Native CI строит
Linux/Windows/macOS binary и хранит его как семидневный workflow artifact,
не player release. Python покрывает HTTP/redirect/fault и отсутствие автоповтора.
Реальный minimal Forge/exporter/Prometheus/Telegraf и Linux PTY проверены в
изолированном стенде: [протокол](validation/owner-tui-2026-11-17.json).
График и квадратная руда отдельно проверены на работающих alpha/beta: 111 focused
Python, 9 Rust tests, 16 native PTY условий, включая настоящее обновление,
все четыре периода, переключение, console, F1 и отмену save без отправки:
[протокол](validation/tui-tps-history-2026-11-17.json).

Следующие полезные срезы: journal-backed maintenance controls; JVM/cgroup RAM/CPU,
disk bytes и графики остальных показателей. Они не объявлены готовыми
в 0.1. Произвольная консоль, права OP и публичная админка не добавлены. Календарный
scheduler остаётся на паузе, полный ручной аудит перед VPS сохранён. Трекер: #240.
