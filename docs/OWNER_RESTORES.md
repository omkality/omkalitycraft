# Подготовка восстановления владельцем

`omk admin restores` готовит **отдельный новый Linux volume** из опубликованного
world snapshot и текущих прав. Команда закрыта в локальной утилите владельца;
лаунчер/API игроков её не предоставляют. Самостоятельно останавливать/запускать
Forge, создавать/удалять тома или переключать рабочий endpoint она не умеет.

[Окно обслуживания](OWNER_MAINTENANCE.md) отдельно управляет штатной остановкой
и возвратом исходного контейнера после копии. Оно **не запускает** staged restore
и не переключает source volume на подготовленный target.

Source/store, restore и resource-reset targets используют общий inventory:
их volumes должны быть различными, даже если конфиги операций заданы отдельными
TOML. Отсутствующий target автоматически не создаётся.

Это ручная операция восстановления, а не второй механизм автобэкапов. Для рабочего
сервера выбирается **один** периодический writer/планировщик и общий бюджет копий.
Если включим managed-копии по расписанию, FTB Backups отключается при проверенном
переходе. Параллельно держать независимые FTB и managed расписания не планируется.
Ручной свежий checkpoint перед восстановлением остаётся частью выбранной процедуры.
Off-host copy переносит проверенные снимки; это не второй writer игрового мира.

## Предварительные условия

- Локальный Linux Docker engine, приватный `.omk-admin/operator.toml`,
  [backups.toml](../deploy/owner/backups.example.toml) и
  [restores.toml](../deploy/owner/restores.example.toml), mode 700/600 на Linux.
- Явно остановленный источник: pinned image, свой container/volume по labels,
  exit 0, OOM=false, выключенный restart policy, корректный журнал остановки,
  ограниченные Docker local logs. Источник и store сохраняются.
- Последний опубликованный owner snapshot должен **побайтно совпадать с текущим
  остановленным миром**. При отличиях сначала выполнить проверенный cold backup.
  Восстановление не создаёт резервную копию незаметно и не меняет retention.
- Отдельный подготовленный target без мира и markers прошлой попытки. Labels,
  creation identity, отсутствие активных mounts, все source/store/target имена
  проверяются. Рабочие тома других настроенных серверов нельзя использовать как target.
- Target использует текущий pinned image/release и тот же перечень/хеши runtime JAR.
  Другие runtime/config файлы связываются хешами плана. Их выбор — явная подготовка
  владельцем, не неявная миграция сборки. Неизвестные FTB конфликты требуют разбора.
  Forge извлекает встроенные core-зависимости в `mods/memory_repo/` и `mods/1.12.2/`
  при первом старте. Свежая распакованная сборка может их ещё не содержать; lab
  отдельно дополняет только отсутствующие зависимости из остановленного источника,
  сверяя хеши. Сама owner-утилита ничего не скачивает и различия JAR не игнорирует.

Текущая реализация требует чистого остановленного источника. Она **не решает**
автоматически случай повреждённого/потерянного тома, fatal/OOM или пропавшего текущего
Drasl. Для такого аварийного случая нужны отдельные сохранённые runtime/config/auth
и процедура владельца; нельзя обходить проверку exit/log простым изменением labels.

## Команды

Из корня проекта; `SNAPSHOT_ID` берётся из `backups list`:

```text
omk admin --config .omk-admin/operator.toml restores plan --server dj2 --snapshot SNAPSHOT_ID
omk admin --config .omk-admin/operator.toml restores status --operation OPERATION_ID
omk admin --config .omk-admin/operator.toml restores apply --operation OPERATION_ID
omk admin --config .omk-admin/operator.toml restores verify --operation OPERATION_ID
```

`plan` монтирует все данные readonly. Проверяет store/архив/CRC, свежий checkpoint,
совместимость известных FTB-полей, runtime, свободный reserve и staging budget.
На target ничего не записывается. Локальный план связывает settings, source lifecycle,
target volume, snapshot/hash и ожидаемые fingerprints. TTL/defaults берутся из
[OMK_BACKUP_*](COLD_BACKUPS.md), отдельные захардкоженные бюджеты не вводятся.

`apply` требует неиспользованный, неистёкший план и неизменные настройки/источники.
Перед helper состояние journal становится `applying`. Helper пишет exclusive план,
raw historical world, текущую policy, полный проверенный receipt. Источник/store
readonly; target writable только при apply. Helper без сети/Docker socket, root
readonly, pinned Python image, ограниченные CPU/RAM/PID/time. Монтируются только
`launcher/__init__.py` и NBT-код, а не session directory лаунчера.

После helper host повторяет lifecycle/volume проверки и сохраняет `staged`.
**Это подготовленная копия, не открытый игровой сервер.** Перед отдельным стартом
нужно выполнить `verify` непосредственно в согласованном окне восстановления.
Пока эксплуатационного promotion/stop/start workflow нет, не применять к рабочему сервису.

`verify` повторно сверяет весь мир, архив, текущий source, JAR/config fingerprints,
политику, планы/receipts. Он может подтвердить завершённую запись после смерти
контроллера между data receipt и journal acknowledgement. TTL на эту read-only
проверку не применяется; используются budgets сохранённого плана. Частично
записанный target проверку не проходит. Повторный `apply` запрещён в обоих случаях.

## Перенос игрока и карантин после вылета

Для DJ2 на Forge 1.12.2 к `restores plan` можно добавить `--incident` с
относительным путём к JSON внутри `.omk-admin`. Перед этим закройте вход,
штатно остановите исходный контейнер и опубликуйте свежую проверенную
[холодную копию](COLD_BACKUPS.md). Подготовьте отдельный том с теми же
JAR, конфигурацией, `server.properties`, списками OP, банов и белым списком.
Том должен быть свободен от контейнеров и старых данных мира.

`reports inspect` помогает найти координаты и предмет. Сверьте их с
серверной записью прежде, чем выбрать действие. Пример переносит игрока из
Ада и изолирует одну стопку в сундуке на указанных координатах.

```json
{
  "rescue": {
    "player": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
    "danger": [-1, -88, -88],
    "landing": [172, 100, 172]
  },
  "quarantine": {
    "kind": "chest",
    "dimension": -1,
    "position": [-89, 100, -86],
    "slot": 4,
    "id": "minecraft:diamond"
  }
}
```

`rescue` и `quarantine` можно применять отдельно. Укажите UUID из сохранения
игрока. `danger` содержит ID измерения, X и Z. Для нескольких соседних опасных
чанков задайте `radius_chunks`, от 0 до 32. Точка приземления всегда в
Основном мире. Если `landing` пропущен, проверяется район сохранённого
защищённого спавна. Можно задать другую существующую площадку с твёрдым полом
и свободным пространством. Для опасной области в Основном мире к её радиусу
прибавляются серверная дальность прогрузки и два чанка запаса.

Перенос сохраняет UUID, инвентарь, опыт, квесты и приваты.
Если у игрока была сохранена история FTB `/back`, она сбрасывается. Кровать,
`/home` и глобальные точки остаются. Держите вход закрытым до проверки
места назначения и устранения опасности возврата через команды или порталы.

| Значение `kind` | Что указать |
| --- | --- |
| `inventory` | `player` с UUID, номер `slot` и `id` предмета. Хотбар 0–8, остальной инвентарь 9–35, броня 100–103, вторая рука 150 |
| `chest` | `dimension`, `position` блока, `slot` от 0 до 26 и `id` предмета в одиночном обычном сундуке |
| `dropped` | `dimension`, `chunk` с координатами чанка, `entity` с UUID выброшенного предмета и `id` предмета |
| `chest-block` | `dimension`, `position` блока и `id` равный `minecraft:chest` для отдельно стоящего сундука |

```text
omk admin --config .omk-admin/operator.toml restores plan --server dj2 --snapshot SNAPSHOT_ID --incident incident.json
omk admin --config .omk-admin/operator.toml restores status --operation OPERATION_ID
omk admin --config .omk-admin/operator.toml restores apply --operation OPERATION_ID
omk admin --config .omk-admin/operator.toml restores verify --operation OPERATION_ID
```

В плане видны исходная позиция, место приземления, выбранный объект и хеши
изменяемых файлов. При `apply` оригинальный объект сохраняется в приватном
`.omk-admin/incident-quarantine/<operation>/object.nbt` до записи исправленной
копии. Там хранятся NBT с исходными типами, количество и данные ForgeCaps.
План связывает NBT с версией сохранения, снимком и хешем реестра мира. Для
сундука он также сохраняет числовой ID и метаданные блока. На всю папку отведено
64 МиБ. Удаление старых записей проводится владельцем после их разбора.

Сверьте `verify` перед первым запуском. Вход и проверка копии выполняются
отдельно, пока действует обслуживание. Проверьте вход игрока, его вещи и опыт,
изменённый чанк и маршруты возврата. Для отката до открытия входа остановите
копию и вернитесь к исходному тому или проверенному снимку. Возврат
изолированного объекта требует отдельного решения владельца.

Мёртвый игрок, сохранённый транспорт, двойной сундук, ожидаемый лут, неизвестная
схема хранилища и неподходящая площадка требуют ручного разбора. Если текущий
контейнер завершился аварийно и свежий холодный снимок сделать нельзя, сначала
восстановите проверенную исходную точку по процедуре аварийного восстановления.

## Прерывание и хранение

При ошибке/неоднозначном исходе — `status`, затем разбор сохранённого target и
`verify`. Не удалять исходник/снимки ради повтора. Если receipt неполон, нужен новый
отдельный target и проверенное решение владельца по старой попытке; автоматического
resume/cleanup/cancel частичного мира нет. Новый plan блокируется незавершённым
journal до его явного разбора/архивирования владельцем.

Операции делят `backups.lock` с cold backups в одном operator root. Это локальная
блокировка, не распределённая lease. Нельзя запускать writer/rotation из второго
operator root или напрямую, пока читается store. Контроль активных Docker mounts
и повторная сверка дополняют блокировку, но не заменяют эксплуатационное окно.

Пути относительно корня проекта:

- `.omk-admin/restores/<operation>.json` — bounded приватный journal, без passwords/tokens;
- `.omk-admin/backups.lock`, `audit.jsonl` — общий lock и ограниченный audit;
- target: `.omk-owner-restore-plan.json`, `.omk-owner-restore-staged.json`,
  raw-world и current-policy markers из [Linux-процедуры](LINUX_CURRENT_POLICY.md);
- lab: `.local/owner-restore-lab-<id>/report.json`, world/policy TAR и owner journals.

World snapshots, source properties, аккаунты и сырые TAR/ZIP приватны. На Windows
они остаются непрозрачными архивами; Linux names вроде `con.dat` не извлекаются на NTFS.
В успешном lab свои тома удаляются после проверенного экспорта; при ошибке owner lab
сохраняет исходный и целевой тома для разбора с их ownership labels в `report.json`.

Исторические homes/claims/вещи и текущие bans/OP/whitelist/ranks/FTB переносятся
по [описанной политике](LINUX_CURRENT_POLICY.md). Drasl и пароли источника не
восстанавливаются из истории. Лимит распакованного мира берётся из
`OMK_BACKUP_WORLD_MAX_BYTES`; старые portable labs сохраняют прежние limits.
FTB сохраняет собственные пределы 1000 records/2 МиБ на запись/32 МиБ суммарно.

Выбор единого расписания/backup-window, общий VPS storage budget, off-host copy,
полноценный аварийный cutover и изменившиеся FTB identity остаются в #33/#38.

## Приёмка 6 ноября 2026

Linux DJ2 2.23.4/Core 0.2.10/CON: 24 native условий/3 старта,
30 независимых проверок. Owner CLI plan/apply/status и verify перед Forge;
возврат вещей/home/claims с текущими bans/whitelist/deop/quota/отзывом ally.
Исходник неизменен, свои тома очищены, stop 0/OOM=false.
Отдельно 14 real Docker/CLI faults и 4 synthetic tmpfs ENOSPC checks.
Windows unit 1010/11 skipped, Linux focused 318.
[Протокол](validation/dj2-owner-restore-2026-11-06.json).
