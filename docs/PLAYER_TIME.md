# Игровое время DJ2

Первый проверенный этап #43 использует штатный счётчик Minecraft 1.12.2,
который FTB Utilities показывает в своей таблице времени. Второго счётчика сессий,
отдельной БД и периодического сборщика нет. Сейчас это время конкретного сохранения
DJ2, **не срок участия в проекте и не основание для автоматических наград**.

## Что считается

Источник — `stat.playOneMinute` в `<level-name>/stats/<account-uuid>.json`.
Несмотря на имя, значение хранится в игровых тиках: номинальные секунды `ticks / 20`,
часы `ticks / 72000`. AFK входит; при пониженном TPS игровые часы идут медленнее
обычных. Перевод времени суток командой `time add` не добавляет эти тики.
Счётчик общий для измерений данного сохранения: Nether не получает независимый
файл `DIM-1/stats`. Используем UUID авторизации, а не offline UUID из ника.

FTB использует этот источник: [регистрация time_played](https://github.com/FTBTeam/FTB-Utilities/blob/1e1f208fd8cd7136a0e9005eaa77c806e84643d9/src/main/java/com/feed_the_beast/ftbutilities/FTBUtilitiesLeaderboards.java),
[команда leaderboards](https://github.com/FTBTeam/FTB-Utilities/blob/1e1f208fd8cd7136a0e9005eaa77c806e84643d9/src/main/java/com/feed_the_beast/ftbutilities/command/CmdLeaderboard.java).
Округлённые часы из визуальной таблицы не разбираем как точный источник.

## Команды

Игрок без OP: `/leaderboards ftbutilities:time_played`. В консоли:
`leaderboards ftbutilities:time_played`. Оба пути проверены на настоящей Docker DJ2
2.23.4. Online-показания FTB могут быть новее сохранённого файла.
Список online UUID владелец получает в консоли через `list uuids`; для offline
нужен UUID из доверенных данных аккаунта/сохранения, не угадывание по нику.

Закрытая утилита владельца читает уже сохранённое значение:

```text
uv run omk admin --config .omk-admin/operator.toml playtime dj2 <UUID>
```

Нужны прежние private operator config, allowlist backup source/store и maintenance
binding: [холодные копии](COLD_BACKUPS.md), [обслуживание](OWNER_MAINTENANCE.md).
Источник — работающий или чисто остановленный локальный Linux Docker server,
соответствующий закреплённому Forge 1.12.2/2860. После аварийной остановки сначала
восстановить/проверить сервер: unclean source отклоняется. Команда не отправляет
`save-all`, не логинится в Drasl, не меняет игру и не требует management token.
В player bundle этих модулей нет.

| Поле JSON | Значение |
| --- | --- |
| `ticks`, `nominal_hours_at_20_tps` | Сохранённые тики и номинальные часы |
| `available` | Известно ли значение; отсутствие файла/ключа не равно нулю |
| `live_unsaved_ticks_included=false` | Несохранённая часть сессии не включена |
| `afk_excluded=false`, `wall_clock_seconds=null` | AFK включён, реальное время не измерялось |
| `snapshot_dependent=true`, `account_lifetime=false` | Это снимок конкретного сервера |
| `running`, `observed_at`, `file_mtime_ns` | Состояние контейнера/чтения, не гарантия свежести live ticks |

Повреждённый/слишком большой JSON, дубли ключей, отрицательные/переполненные тики,
ссылки и изменение файла во время чтения дают отказ. Смена container identity или
lifecycle также требует повтора. Helper без сети/socket читает source и код через
readonly mounts; общий owner lock; cleanup удаляет только собственный helper.
Это ограждение операции от случайных ошибок, не защита от владельца Docker daemon
или изменённого runtime. Проверка закреплённого Forge не аттестует весь сервер.

## Лимиты

[Пример окружения](../deploy/player-time.example.env) задаётся процессу владельца;
CLI не подгружает env-файл автоматически. Неверное значение отклоняется без echo.

| Переменная | Default | Допустимо |
| --- | --- | --- |
| `OMK_PLAYTIME_INPUT_MIB` | 4 | 1–16 МиБ на один stats JSON |
| `OMK_PLAYTIME_TIMEOUT_SECONDS` | 30 | 5–120 секунд на helper |

CPU/RAM используют прежние `OMK_BACKUP_HELPER_CPUS` (1) и
`OMK_BACKUP_HELPER_MEMORY_MIB` (512); ranges и остальные backup policy — в
[таблице](COLD_BACKUPS.md#настройки-окружения). Новых polling jobs нет.

## Перезапуск, копии и сброс миров

Чистая остановка сохраняет тики; после SIGKILL остаётся последнее успешное
сохранение. Несохранённый хвост может потеряться. Join/rejoin/death/Nether/restart
не создают второго параллельного учёта.

Сброс отдельного измерения оставляет корневой `stats`. Регрессия plan → stage →
verify сохраняет точные bytes в свежем candidate. Отдельный Linux replay использовал
stats JSON настоящей DJ2 внутри синтетического остановленного мира и проверенной
backup copy. Это преобразование данных, не новая графическая игра после вайпа.

**Восстановление старой полной копии откатывает и игровое время.** Удаление всего
сохранения, включая stats, удалит источник. Между серверами часы не суммируются.
Для несбрасываемого времени участия/наград нужно отдельно принять семантику
rollback/full reset и проверить дальнейший учёт. #43 остаётся открытой.

Две свежие DJ2 2.23.4 lab, четыре boot: обычная остановка и контролируемый SIGKILL,
Drasl-аккаунты/Forge protocol actors, offline/rejoin, AFK, смерть/respawn, Nether.
Это не графический клиент и не длительная эксплуатация. Собственные containers и
volumes удалены после экспорта закрытых результатов. VPS, release и owned JAR
прежние. [Протокол](validation/player-time-2026-11-13.json).
Приветствие новичкам (#44), награды и общий lifetime — отдельные этапы;
новых сообщений в чат эта правка не рассылает.
