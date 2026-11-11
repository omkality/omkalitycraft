# Учёт места владельцем

Для всех настроенных серверов и общих auth/CDN/diagnostic volumes появился
отдельный [проектный отчёт `storage estate`](PROJECT_STORAGE.md). Интерфейс ниже
сохраняет прежний per-server scope и не требует нового реестра.

```console
uv run omk admin --config .omk-admin/operator.toml storage inspect --server dj2
```

Команда читает явно настроенные Linux Docker volumes и возвращает JSON. Она
не удаляет файлы, не меняет мир и не создаёт расписание резервного копирования.
В лаунчере и игровых командах этого интерфейса нет. Нужны приватный operator
config, доступ к **локальному** Linux Docker engine и
[backups.toml](COLD_BACKUPS.md). Drasl-пароль или management token не требуются.

## Что попадает в отчёт

Source и backup store обязательны. Если для сервера настроены
`resource-resets.toml` и/или `restores.toml`, учитываются также эти targets.
Отсутствующий или потерявший ownership label настроенный volume вызывает отказ;
он не создаётся автоматически. Имена, labels и даты создания проверяются до и
после helper. Другие серверы из operator allowlist используют свои настройки.

Внутри source данные разделяются по назначению:

| Категория | Содержимое |
| --- | --- |
| `active_world` | Каталог активного мира, включая его измерения и player/FTB данные |
| `retained_world_generations` | Вся `.omk-cutovers`, включая предыдущие, отклонённые и частичные копии |
| `game_logs` | Корневой `logs` |
| `crash_reports` | Корневой `crash-reports` |
| `pack_backups` | Корневой `backups`, даже если старый FTB writer уже выключен |
| `runtime_and_other` | Все остальные файлы и каталоги source; неизвестные данные не пропускаются |

Для store/reset/restore считается всё содержимое, включая pending-файлы и
runtime кандидата. Известная или неизвестная структура журнала не даёт права
считать каталог мусором. Отчёт не предлагает автоматическое удаление поколений.

Каждая категория содержит число файлов/каталогов, `apparent_bytes` — сумму
длин файлов, `allocated_bytes` — Linux allocated blocks файлов и каталогов.
У sparse-файла эти значения могут существенно различаться. Здесь нет оценки
сжатия/дедупликации на уровне самого хранилища провайдера.

`filesystems` объединяет mounts с одним Linux device: общий свободный объём не
складывается повторно для source/store/targets на одном разделе. Для каждого
раздела показываются total, минимальный наблюдавшийся `available_bytes` и
`below_reserve` относительно `OMK_BACKUP_RESERVE_BYTES` (по умолчанию 16 ГиБ).
Это предупреждение владельцу, без очистки и выключения сервера.

## Настройки и пределы

| Переменная | По умолчанию | Допустимый диапазон |
| --- | --- | --- |
| `OMK_STORAGE_MAX_ENTRIES` | 200000 | 1–1000000 файлов и каталогов суммарно |
| `OMK_STORAGE_MAX_DEPTH` | 64 | 1–128 уровней внутри mount |

CPU, RAM и timeout helper берутся из текущих `OMK_BACKUP_HELPER_CPUS`,
`OMK_BACKUP_HELPER_MEMORY_MIB`, `OMK_BACKUP_TIMEOUT_SECONDS`; значения и диапазоны
описаны в [руководстве копирования](COLD_BACKUPS.md). Обход учитывает метаданные,
а не читает содержимое файлов. Это ограничивает нагрузку и не выводит
server.properties, NBT, чат, пароли или имена файлов в отчёт.

Все mounts read-only с `volume-nocopy`, rootfs read-only, сеть выключена,
capabilities удалены, Docker socket не монтируется. Helper закреплён прежним
Python image SHA. При превышении лимита, symlink/hardlink, special file,
вложенном другом filesystem или обнаруженном изменении метаданных сканирование
отклоняется целиком. Частичный результат не выдаётся за полный.

Лучше выполнять сканирование в тихом окне. После обхода ещё раз сверяются
inode/size/mode/mtime/ctime; появление, удаление или изменение файла может
потребовать повторить запрос. Это **не атомарный снимок** работающего сервера и
не доказательство целостности backup (`atomic_snapshot=false`,
`backup_integrity_verified=false`). Проверку архивов выполняет отдельный backup
интерфейс.

`host_disk_complete=false`: отчёт классифицирует только текущие настроенные
volumes. Он не перечисляет все старые/orphan volumes, Docker images/build cache,
container logs, Drasl storage, host-журналы и другие проекты. Их место влияет на
свободный резерв filesystem, но для общего бюджета VPS потребуется отдельный
учёт. Также пока нет автоматической ротации retained worlds, off-host copy и
единого периодического scheduler. FTB и managed расписания не включаются вместе.

## Проверка

В Linux Docker CLI проверена на четырёх свежих volumes с копиями принятых DJ2
экспортов: 5324 файла, включая 632 retained world-файла, два backup и sealed
candidate. 16 условий: размеры/число файлов сверены с независимыми архивными
inventories, общий filesystem показан один раз, все байты до/после прежние.
Четыре собственных тома удалены после проверки. Minecraft в этом опыте не
запускался; исходный игровой прогон описан в
[world-cutovers](OWNER_WORLD_CUTOVERS.md).

31 новый synthetic случай проверяет sandbox/allowlist/identity drift/потерю
ответа, лимиты, sparse-файлы, ссылки, изменение во время обхода и минимум
свободного места. Последний случай воспроизведён red/green: низкое значение до
обхода второго mount тоже должно сохраняться в общей сводке.
