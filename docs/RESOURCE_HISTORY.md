# Приватная история ресурсов: Prometheus и Telegraf

Текущий backend — готовые **Prometheus 3.16.0 + Telegraf 1.40.3** в Linux Docker.
Игровые показатели DJ2 предоставляет server-only Prometheus Exporter cpburnz
1.0.0 для Forge 1.12.2. Версии, источники и digest/SHA256 закреплены в
[`artifacts.json`](../deploy/metrics/artifacts.json). Это не допуск всего DJ2 к запуску
игроков: [общая приёмка](LAUNCH_READINESS.md) и #146 остаются открытыми.

Собственные Python sampler/SQLite store/hourly aggregation удалены. Старые
validation и история Git сохранены; на VPS их не разворачивали. Данные аккаунтов
Drasl, его SQLite, диагностика клиентов и миры этим изменением не затронуты.
Core 0.3.8 ещё содержит прежний opt-in JSON producer для совместимости лабораторий;
новому мониторингу он не нужен, `OMK_GAME_METRICS_ENABLED` оставляем `false`.
Не запускаем второй постоянный collector рядом.

## Состав

- Prometheus хранит временные ряды, выполняет PromQL и отдаёт закрытый HTTP API.
- Telegraf собирает CPU/steal, RAM/swap, vmstat, PSI, disk I/O, network counters,
  свободное место проекта и выбранные cgroup v2. `memory.events` даёт настоящий
  `oom_kill`; ограничение доступа к kernel log не превращается в ложный ноль.
- cpburnz экспортирует JVM heap/GC, server tick histogram, игроков и измерения.
  Устанавливается только на сервер, клиентский manifest не меняется.
- `omk/monitoring_config.py` только проверяет частную конфигурацию и создаёт JSON/TOML
  для готовых программ. Сборщика, БД и собственного HTTP exporter в нём нет.

Фоновых сервисов два; `configure` — короткий одноразовый контейнер. У агента нет
Docker socket, host PID, privileged/capabilities, аккаунтов и доступа к содержимому
игрового тома. Только readonly выбранные procfs-файлы, sysfs/cgroup и пустой
filesystem probe на том же диске, где Docker хранит именованные volumes. Внутренний `/host/proc/self/mounts` ссылается на mount table самого агента,
чтобы видеть `/storage/project`; сетевые байты берутся из `/proc/1/net/dev` хоста,
а не из сетевого namespace агента.

## Данные профиля и установка

Копируем [`config.example.json`](../deploy/metrics/config.example.json) в частную
`.omk-admin/metrics.json` (schema 2; прежний SQLite config schema 1 не совместим). Указываем стабильный host ID, cgroup path, private Docker
DNS target и фактическую release каждого сервиса. До 16 сервисов, без pack branches
в GUI. Endpoint имеет форму `host:port`, без URL/логина/пароля. Для cgroup-only сервиса
(API/Drasl и т. п.) задаём `target: null` и пустой `dimension_aliases`: это не создаёт
ложную игровую метрику онлайна и не требует Minecraft exporter от обычного API.

Каждый игровой сервис запускается с собственным **стабильным cgroup parent**.
При cgroupfs это, например, `omk-dj2`; при systemd driver можно использовать
`omkdj2.slice`. Фактический путь надо проверить в `/sys/fs/cgroup` конкретного Docker
host и записать в профиль; container ID не является стабильным именем сервиса.
Пустой parent и `cgroup.events populated=0` отличаются от недоступного источника.

В игре нужен JAR из закреплённого artifact pin. `configure` создаёт для каждого
сервиса `<service>.exporter.cfg`: его подключаем как `config/prometheus_exporter.cfg`
игрового контейнера до старта. Внутренний port берётся из target того же профиля.
Метрики игры не публикуем через host ports. Game и Prometheus разделяют частную
Docker network; имя передаётся через `OMK_METRICS_GAME_NETWORK`.

У cpburnz label `id` означает **DimensionType**, а не всегда реальный dimension ID.
Он сохраняется как `id` и дополнительно подписывается `dimension_type`.
`dimension` добавляется только для явно заданного проверенного one-to-one
`dimension_aliases`. В DJ2 spatial world имеет ID `2`, но тип `-11`.
В примере явно указаны четыре проверенных мира: `0`, `2`, `-9999`, `-18000`.
Неизвестному/общему типу не приписывается выдуманный world ID. Гистограммы времени
таких миров — показатели **типа**, а не независимые данные каждой его копии.
Счётчики типов сохраняются после выгрузки мира; это не список загруженных миров.

`mc_dimension_chunks_loaded` исключён из scrape: разные миры общего типа могут
дать одинаковые labels. В CI два разных значения с такими labels не ломают сбор
общих/JVM/tick метрик. Этой необязательной метрики в прежнем Core collector не было.
Не форкаем JAR и не ограничиваем создание миров. Точная история по world ID для
общих динамических типов остаётся дополнительной приёмкой #146; для текущего
разбора доступен проверенный консольный `forge tps`.

После аудита владельца используем частный env из
[`example.env`](../deploy/metrics/example.env), без коммитов с operational values:

```console
docker compose --env-file /opt/omk/.omk-admin/metrics.env -f deploy/metrics/compose.yaml config --quiet
docker compose --env-file /opt/omk/.omk-admin/metrics.env -f deploy/metrics/compose.yaml up -d --build --force-recreate
```

Репозиторий сам ничего не устанавливает на VPS. Чужую сеть/данные Compose не создаёт
и не пересоздаёт. Профильные target/cgroup/release меняются в частном JSON, интервалы,
retention, порты, CPU/RAM, query limits и log rotation — в env. Старые
DATABASE_MIB/DETAIL_DAYS/HOURLY_DAYS не читаются; берём новый env example. При обновлении
данных применяем `--force-recreate` к этому Compose, чтобы оба процесса перечитали
сгенерированные файлы; одна запись JSON в volume не является reload Telegraf.
Изменение exporter port требует согласованного применения game config до его старта.

## История, место и перенос

По умолчанию interval 30 секунд, история до **180 дней**, retention blocks **1024 MiB**.
Срабатывает более ранняя граница времени/объёма; 180 дней при любом количестве series
не обещаются. Прежнего разделения 7 дней details / 180 дней hourly SQLite больше нет.
Для длинного периода задаём подходящий `step` в query_range; почасовая выборка не
выдаётся за точный active-only CPU или настоящий p95 всех тиков.

`<compose-project>_tsdb` хранит TSDB, WAL и checkpoints в `/prometheus`; UID 65534
соответствует официальному образу. `<compose-project>_config` содержит только
сгенерированные конфигурации. `<compose-project>_filesystem_probe` — пустой том
для statfs на Docker data filesystem: весь проект/миры/аккаунты ради свободного
места в agent не монтируются. Если game/backup лежат на другом диске, добавляем
пустой probe именно на нём через private Compose override и проверяем layout. Для переноса останавливаем Prometheus и сохраняем весь
TSDB volume с владельцем, а не копируем открытый WAL отдельным файлом. Не применять
`down --volumes` или глобальный prune к рабочей истории.

Retention size **не жёсткая квота всей папки**: WAL/head/compaction требуют места
дополнительно. Для default учитываем не менее 2 GiB общего резерва под TSDB/временные
файлы в storage budget, отдельно Docker logs и общий запас проекта. Большое число
series и реальные размеры проверяются на VPS; включение ещё одной сборки не решаем
по короткому пустому lab. Нет бесконечного application queue: agent buffer ограничен,
ресурсы контейнеров и query concurrency/time/samples ограничены через env.

В одном native замере agent/Prometheus заняли примерно 84/35 MiB RAM, старый collector
около 20 MiB; это краткий замер, не верхняя граница. Limits по умолчанию 128/256 MiB,
CPU по 0.25; значения настраиваются, память под limit не резервируется заранее.

## Приватность и смысл запросов

Prometheus опубликован **только на `127.0.0.1`**, default port 9090. Для удалённого
владельца — SSH tunnel; игроки/лаунчер к нему не обращаются. Agent находится только
во внутренней metrics network. Отдельная admin bridge нужна для loopback publication,
даже когда внешняя game network тоже internal; наружу agent port не публикуется.
Не добавляем маршруты к метрикам в публичный API/ingress.

cpburnz включает player UUID/ник в `mc_player_list`. Это не токены/пароли, но
экспорт TSDB и endpoint остаются приватными. Собственный `omk_game_online` считает
игроков без UUID/ников в label. Не делаем публичный dump raw series.

`up` показывает доступность exporter, а не здоровье игрового потока. Отсутствие
игроков при доступном сервере — 0; недоступный сервер — unknown. Все **текущие**
сводки должны проверять `up`. После перезапуска Prometheus старые raw и recording
series могут оставаться доступными в lookback; это история, не доказательство
работающего источника. Например:

```promql
mem_available and on(job,instance) (up == 1)
rate(cgroup_cpu_stat_usage_usec[90s]) / 1000000 and on(job,instance) (up == 1)
omk_game_online and on(job,instance) (up == 1)
omk_game_tps and on(job,instance) (up == 1)
mc_dimension_tick_seconds_count{dimension="-18000"} and on(job,instance) (up == 1)
```

`omk_game_progress_observed` отличает наблюдавшийся прогресс tick counter от одного
живого HTTP endpoint. Первые окна rate прогреваются. Экспортерная гистограмма даёт
оценки распределения по bucket, не точный прежний Core rolling p95. Minecraft main
thread может зависнуть при доступном HTTP: это нельзя считать нормальным онлайном
по одному `up`. После пропажи input Telegraf удаляет кэш через три интервала;
опросы ОС/игры не являются одним атомарным снимком.

## Проверки

`uv run python -m scripts.check_monitoring` проверяет настоящий promtool, конфигурацию
Telegraf, правила zero/two/offline, TPS/mean, Docker isolation, start/health, сохранность
исторического sample после restart, пропадание и возврат источника. CI запускает этот
небольшой Docker стенд; полной DJ2 в CI нет.

Полная DJ2 проверена отдельно в Linux Docker: 27 условий стенда, два authenticated
non-OP actors, ресурсный мир, источник Core для независимого сравнения, controlled
32 MiB child OOM, pause/recovery, два старта, инвентарь/XP после остановки. Prometheus
сохранил историю после SIGKILL. Graphical client/весь pack и VPS этим не приняты.
Сравнение node_exporter/cAdvisor и ограничения — в
[протоколе](validation/standard-monitoring-2026-11-13.json).

Для будущей Rust TUI используем стандартный private HTTP API Prometheus, не новый
набор omk-команд и не собственный query/storage engine. Корреляция с обслуживанием,
реальные active-interval отчёты и многодневная нагрузка VPS остаются в #146/#38.
Loki/Grafana пока не устанавливаются: задачи ограниченных файловых логов не изменились.
