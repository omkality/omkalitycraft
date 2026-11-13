# Административная копия остановленного сервера

`omk admin backups` создаёт проверенную копию мира из явно настроенного Linux Docker
volume. Это локальная утилита владельца с правами Docker, без HTTP/игровой команды
и без интерфейса в лаунчере. Пароль Drasl не требуется: аварийное резервирование
не зависит от доступности авторизации. Доступ к приватному конфигу и Docker daemon
даёт полномочия владельца; Docker labels защищают от случайного выбора чужого
ресурса, а не от администратора того же Docker daemon.

Linux worker использует `linux-server` path policy и новый owner schema 2, чтобы
сохранять FTB-файлы вроде `con.dat`. Portable defaults прежние. Существующие store
не мигрируются/не усыновляются автоматически; их policy должна совпадать с reader.
[Совместимость, Linux staging и приёмка CON](LINUX_SERVER_PATHS.md).

## Подготовка

Для проверенной остановки и возврата **того же** контейнера используйте
[окно обслуживания `omk admin maintenance`](OWNER_MAINTENANCE.md). Оно не добавляет
расписание: копию создаёт существующая команда `backups`, запуск требует её
завершённого результата и повторной сверки текущих данных.

1. Использовать контейнерную среду с данными на Linux FS, именованными source/store
   volumes и уникальными ownership labels. Для будущего VPS понадобится штатное
   provision этих ресурсов; существующие нелабораторные данные автоматически
   не принимаются и не переносятся. Source и store обязаны быть разными томами;
   разные серверы также требуют отдельных container/source/store имён. Общий
   backup volume для нескольких серверов отвергается конфигурацией.
2. Добавить сервер в `.omk-admin/operator.toml`, а параметры контейнера/томов — в
   отдельный `.omk-admin/backups.toml` по [шаблону](../deploy/backups.example.toml).
   Каталог mode 700, файлы mode 600 на Linux/macOS. Конфиги/журналы/копии вне CDN и Git.
3. Запускать CLI на том же хосте, что локальный Linux Docker engine: Unix socket
   на VPS/Linux, Docker Desktop named pipe на Windows. Для VPS сначала подключиться
   по SSH, затем запускать CLI там. Remote TCP/SSH Docker context отвергается.
4. Штатно остановить сервер и отключить автоматический restart на период холодной
   операции. Контейнер должен остаться существующим в состоянии exited/exit 0,
   OOM=false; root data mount — `/srv`, без вложенных подменяющих mounts.
   Docker logging: `local`, `max-size` до 16m, `max-file` до 4; журнал остановки
   обязан быть доступен, ограничен и без фатальных Forge-маркеров.

CLI проверяет точный pinned image, container ID/start/finish/restart count,
labels/даты создания volumes и отсутствие работающих контейнеров с source volume.
Новый том вместо исчезнувшего при проверке не создаётся. В контейнере helper нет
Docker socket, сети, дополнительных capabilities; rootfs/source readonly,
запись только в выбранный backup volume. Python helper закреплён по SHA-256.

## Команды

```text
omk admin --config .omk-admin/operator.toml backups plan --server dj2
omk admin --config .omk-admin/operator.toml backups run --operation OPERATION_ID
omk admin --config .omk-admin/operator.toml backups status --operation OPERATION_ID
omk admin --config .omk-admin/operator.toml backups list --server dj2
```

`list` и предварительная nightly-инспекция монтируют store только для чтения.
В Linux `BackupStore.inspect` берёт shared flock через rb-descriptor; publisher
берёт exclusive lock. Проверка не требует права записи в volume и не пропускает
параллельного писателя. Windows portable inspection сохраняет прежний byte-range
lock. Readonly regression для уже созданного store воспроизведена и проверена
в Docker; [протокол и отдельная DJ2-копия](validation/nightly-cycle-2026-11-12.json).

План показывает источник, точную остановку, inventory/hash/объём мира, fingerprint
JAR/mods/libraries/config/scripts/groovy/resources/local, текущую историю и политику.
`release` — заданное владельцем название; фактический fingerprint рассчитывается
отдельно. Исходные пароли/токены или содержимое server.properties в journal не входят.
Перед run проверить конкретный план. Изменившиеся конфиг/env/runtime/мир/история,
другой container/volume или истёкший TTL требуют нового плана.

Операция разделена:

1. Под межпроцессной блокировкой записывается durable journal этапа `preparing`.
2. В Linux вычисляется независимый полный inventory мира, пишется закрытый ZIP,
   проверяются CRC/байты/SHA и повторный inventory/fingerprint источника.
3. **До публикации** хост повторяет проверку исходного container checkpoint. Если
   контейнер стартовал даже с теми же файлами — архив остаётся staging, публикации нет.
   После завершённой согласованной подготовки дальнейший запуск источника уже не
   меняет байты закрытого архива. Не переключать Docker context и не менять ресурсы
   вручную во время операции; это не защита от администратора того же хоста.
4. `BackupStore` публикует проверенную новую копию через fsync/rename и лишь затем
   ротирует старые. Новая и непосредственно предшествующая копии сохраняются;
   нехватка бюджета под обе приводит к отказу.
5. Linux receipt и journal согласуются, известный staging удаляется, этап становится
   `complete`. Контейнер исходного сервера остаётся остановленным до штатного запуска
   владельцем. Запись в исходный мир/его замена не выполняются этой командой.

## Обрыв и повтор

Не повторять run вслепую. Уже начатая операция отвергает повтор, незавершённая
блокирует новые планы. Lock-файл не удалять: блокировка ОС сама освобождается
при смерти процесса. `status` читает journal, не объявляет потерянный ответ успехом.

```text
omk admin --config .omk-admin/operator.toml backups finish --operation OPERATION_ID
```

`finish` предназначен для сбоя около публикации/подтверждения. Он ищет единственный
верифицированный новый sequence с хешем подготовленного архива и проверяет историю,
после чего завершает receipt/journal **без повторной публикации или ротации**.
Частично выполненная очистка receipt также может быть завершена повторно.
Если доказательства публикации отсутствуют/неоднозначны, остаётся отказ и ручной
разбор staging владельцем. Автоматического удаления неизвестных pending/retired
каталогов, автоповтора неуспешной подготовки и сброса незавершённых journal нет.

Для явно **неопубликованной** попытки есть отдельная отмена:

```text
omk admin --config .omk-admin/operator.toml backups cancel --operation OPERATION_ID
```

Она требует отсутствия работающего helper на backup volume, точного совпадения
прежней проверенной истории и отсутствия receipt. Удаляются только известные
неопубликованные `incoming.zip`/`prepared.json` этой операции; проверенные snapshots
и source не затрагиваются. Если публикация возможна, отмена отказывает и нужен
`finish`/разбор. Частичный cancel повторяем, после подтверждённой отмены новый план
снова разрешён. Активные helper видны по Docker label
`omkality.backup.operation=OPERATION_ID`; дождаться их завершения перед разбором.

## Настройки окружения

| Переменная | Default | Диапазон |
|---|---|---|
| `OMK_BACKUP_MAX_BYTES` | 48 GiB | 1 B–1 TiB, общий archive+manifest бюджет |
| `OMK_BACKUP_STAGING_BYTES` | 32 GiB | 1 B–1 TiB |
| `OMK_BACKUP_RESERVE_BYTES` | 16 GiB | 1 B–1 TiB, свободный остаток |
| `OMK_BACKUP_WORLD_MAX_BYTES` | 16 GiB | 1 B–1 TiB, несжатый мир |
| `OMK_BACKUP_MAX_COUNT` | 12 | 2–128 |
| `OMK_BACKUP_JOURNAL_COUNT` | 256 | 8–1000 |
| `OMK_BACKUP_TIMEOUT_SECONDS` | 1800 | 10–7200 |
| `OMK_BACKUP_HELPER_MEMORY_MIB` | 512 | 128–2048 |
| `OMK_BACKUP_HELPER_CPUS` | 1 | 1–8 |
| `OMK_BACKUP_PLAN_TTL_SECONDS` | 3600 | 60–86400 |

Это defaults механизма, не утверждённый бюджет VPS. Их нужно согласовать с
`omk storage plan`, мирами/логами/content/Docker и внешними копиями до размещения.
Staging проверяется по несжатому миру с запасом под ZIP/manifest и второй копией
при публикации, а не по оптимистичной оценке сжатия. При параллельном заполнении
диска возможен ENOSPC: прежние проверенные копии не удаляются ради попытки.

Дополнительные защитные caps: 20000 файлов мира, manifest до 8 MiB, runtime
fingerprint до 20000 файлов/8 GiB. Отказ при большем составе требует отдельного
пересмотра/теста, не удаления guard. Прежние lab-defaults 512 MiB сохранены для
старых тестов; owner helper получает свой явный лимит expanded bytes.

## Где искать данные

- Backup volume: `store/snapshot-<id>/archive.zip` и `manifest.json`; plaintext,
  приватные данные игроков. Одна source world tree, включая её вложенные измерения,
  playerdata/FTB/сущности. Внешние runtime/config/auth не входят в этот world ZIP.
- Во время операции: `incoming.zip`, `prepared.json`, `receipt.json`; их присутствие
  отражается `list`, новый plan требует разбора/завершения.
- Хост: `.omk-admin/backups/<operation>.json`, `backups.lock`, bounded `audit.jsonl`.
  Journal до 64 KiB; при достижении лимита новых планов нет до архивирования
  завершённых записей владельцем. Не удалять незавершённые записи как старые логи.

Один Docker-диск не является внешней резервной копией. Off-host зашифрованное
хранение, расписание, аварийный cutover и пересогласование исторических FTB
memberships остаются в #33/#38. `backups` не реализует частичный откат базы #34.

## Повторить проверки

`omk lab cold-backups` создаёт свежие синтетические runtime/world/volumes: настоящие
Docker/CLI гонка, смерть управляющего процесса после публикации, finish, ротация,
restart источника между prepare/publish и sparse 600 MiB при ограниченной памяти.
Это не запуск Minecraft. Своё состояние удаляется, report/journals остаются в
`.local/cold-backups-<run>/`. Этот сценарий включён в Linux CI.

`dj2-recovery` дополнительно принимает `--operator-backups` вместе с
`--managed-backups --runtime linux-docker --edge-cases --full-backup-return
--access-policy --rank-policy`: четыре холодных owner plan/run на настоящем Forge,
затем существующий full-return/retention сценарий. [Основной стенд](LINUX_WORLD_RETURN.md).
Рабочие аккаунты/миры не используются ни одним из этих labs.


Сравнение локального snapshot storage с готовым restic и принятое ограничение
первого запуска: [READY_SOLUTIONS_COMPARISON.md](READY_SOLUTIONS_COMPARISON.md).
