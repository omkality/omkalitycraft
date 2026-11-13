# Разработка OmkalityCraft

## Вторая порция RU и проверка смысла — 13 ноября 2026

#49/P1: 97 changed-EN/unchanged-RU кандидатов разобраны; 67 переводов сохранены,
30 обновлены (BQ/CT/Natura/OpenBlocks). Уточнены стороны машин, область 7×7×5,
Tesla Core, Grove Stone и Silk Touch. Удалённые upstream warnings синхронизированы
как текст, не объявлены подтверждённым исправлением механики.

Ещё 15 EN-записей Extended Crafting guide и 51 missing Roots переведены.
Всего 191 owned entry, 31 приватный language/config файл; tips первой порции прежние.
Schema 2 с RU-пинами и 97 hashed review decisions. Узкий bytes-only helper правит
шесть фрагментов без переноса полного стороннего текста; unknown/ambiguous/stale
отклоняются. EN guard/placeholders отдельно обязательны. Новых CLI/GUI/API нет.

Red: 19 новых failures /24 прежних passes; green: 43 helper, 50 с CLI. Linux Docker:
9 data checks +43 unit, readonly non-root named volume, 1 CPU/256 МиБ, no network/socket,
exit 0/OOM=false. Независимый replay и две композиции совпали; исходные JAR/seed прежние,
свои scopes удалены. Первый verifier отказал из-за CRLF/LF hash mismatch самого JSON;
явный LF в композиции устранил причину, проверки хешей не ослаблялись.

Слой не установлен в игру; full RU/runtime I18n/шрифт/книги/обычная игра ещё не приняты.
OpenAL #163 независим; player manifest/release/VPS прежние, computer-use выключен.
[Контракт и остаток](DJ2_TRANSLATION_COMPLETION.md),
[протокол](validation/dj2-russian-meaning-2026-11-13.json).

## Дополнение готовых переводов актуальной DJ2 — 13 ноября 2026

Владелец выбрал актуальную DJ2; current upstream latest проверен как 2.23.4.
Два готовых перевода используем как основу, дополняем player-facing пробелы.
#49: P1 до финальной клиентской/миграционной регрессии, предгенерации и выпуска.
Прежнее откладывание перевода текущей DJ2 отменено; email/GTNH позже.
Безопасность/восстановление и OpenAL #163 остаются самостоятельными scope.

Первая порция: 95 адресных записей (92 missing +3 EN в RU), правильный item/tile
ключ ContentTweaker. 129 tips явно сопоставлены с 130 готовыми RU: один старый
дополнительный совет не переносится, 91 перевод сохранён, 38 обновлены; четыре
project adaptations. Собственные source-данные и EN value hashes в profile,
полный заимствованный слой и raw лаборатория вне Git. Common JAR Git blob IDs
BMProjects/candidate: 223 совпадения; дополнительные OptiFine/clientfixer не импортировались.

В прежний render_lang добавлен необязательный source guard: stale EN при том же
ID/формате отвергается, предыдущие callers совместимы. Red: 9 новых failures при
15 прежних passes; green: 24. Data-only Linux named volume: 7 checks +24 unit,
readonly/no network/socket, реальные case-sensitive paths, 1 CPU/256 МиБ,
exit 0/OOM=false, inputs прежние, own scopes удалены. Не Minecraft game acceptance.

Assembled output — 28 только языковых/config файлов; JAR/scripts/recipes/quests,
рабочие manifests/release/VPS прежние. Полнота всей сборки не принята: следующие
player-facing книги/GUI, происхождение локалей, runtime I18n и графический клиент.
[Контракт и остаток](DJ2_TRANSLATION_COMPLETION.md),
[протокол](validation/dj2-russian-completion-2026-11-13.json).

## Полнота русского перевода DJ2 — 13 ноября 2026

Владелец поставил полноту перевода выше свежести версии. Расширенный статический
аудит #49: старые mod JAR locales, ResourceLoader/Groovy, активный FM_NewFont,
tips и Patchouli. Кандидат 2.23.4 содержит все 3532 актуальных BQ-ключа; два
изменённых LightningCraft-описания уже адаптированы. Но 129 custom tips остались
английскими, а восемь JAR потеряли 3025 RU-записей. Их class entries и EN bytes
идентичны старым. Приватный language-only draft восстанавливает эти записи;
на 53908 одинаковых EN-ключах потери наличия RU уменьшаются с 3025 до нуля.

717/718 Patchouli JSON совпали как JSON; одна metadata/macros правка TF, не
обнаруженная потеря RU. Предыдущий аудит пяти внешних файлов был недостаточен
для полноты сборки. Нет global процента/обещания 100% RU. UTF-8/формат/пути и
130 RU tips отдельно проверены data-only Linux Docker: no network/socket,
readonly/1 CPU/256 МиБ, exit 0/OOM=false, inputs прежние, owned container удалён.
Первый strict-input отказ на builtin Erebus EN сохранён; нормализован только
frozen verifier input, не production parser/JAR. Draft не установлен в игру.

Следующее: проверить происхождение/распространение локалей, semantic tips,
runtime resource priority/I18n/шрифт/BQ/JEI/книги и обычную игру. Native OpenAL
crash #163 независим и не исправлен языковым слоем. Версия/manifest/player
release/VPS прежние. [Сравнение](DJ2_TRANSLATION_COVERAGE.md),
[пины и протокол](validation/dj2-translation-coverage-2026-11-13.json).

## Короткая памятка новичкам — 13 ноября 2026

Следующий ограниченный шаг #44: общий opt-in Core 0.3.8, текст DJ2 в data profile,
ручной `/guide` без прежнего имени/алиаса. После login задержка, порог vanilla
PLAY_ONE_MINUTE и persisted cooldown; нет нового учёта времени/БД/owner CLI.
Default: 3 игровых часа, 8 секунд, 30 минут между автопоказами; validated env.
Смерть/dimension change не ставят показ в очередь, logout отменяет ожидание.

49 Java policy/queue controls; native DJ2 2.23.4 в Linux Docker: 24 записи /23
уникальных проверки, два чистых старта, Drasl/non-OP protocol actors, chat packets,
threshold/unknown, NBT fence после restart, сохранность вещей/XP. Отдельный generic
Forge без FTB/DJ2: 9 checks. 30 Linux reset cases сохраняют новые NBT markers.
2279 Windows unit/UI /101 skipped; два чистых Docker build воспроизводят Core,
Fix/Client прежние. Свои server/auth scopes удалены после экспорта.

Обычный графический клиент не принят: private fixture ранее перезаписывала FML
policy, затем использовала displayVersion вместо wire version. Равенство Core
не ослаблялось. Два Windows native exit 0xC0000005 с fault module OpenAL64.dll
сохраняются отдельной проблемой, не доказательством причины в Core/переводе/CPU.
Owned Crash Assistant helpers закрыты после сохранения диагностики. #44 остаётся
открытой до настоящего отображения в чате. Player manifests/release/VPS прежние.
[Контракт](NEW_PLAYER_GUIDE.md), [протокол](validation/new-player-guide-2026-11-13.json).

## Сохранённое игровое время DJ2 — 13 ноября 2026

Ограниченный шаг #43: существующий vanilla stat.playOneMinute из FTB time_played,
без нового counter/database/collector. Один owner CLI читает saved ticks по UUID:
allowlisted pinned Linux source readonly, helper без сети/socket, общий lock,
bounded input/timeout, lifecycle binding и cleanup только собственного helper.
Unknown/corrupt не равны нулю. AFK включён, low TPS замедляет номинальные часы;
unsaved хвост не включается. Это snapshot server time, не account lifetime.

Две native DJ2 2.23.4 lab, четыре boot: console/non-OP FTB, stationary actor,
world time skip, death/respawn, Nether, offline/rejoin, clean restart и SIGKILL.
После kill остаётся сохранённый floor, offline/boot не удваиваются; unclean source
отклоняется до восстановления. Независимый stats JSON совпадает. Protocol actors,
не graphical game. Свои scopes удалены; JAR/player release/VPS прежние.
Linux data-only replay сохраняет точные native stats через verified backup и
allowlisted reset stage в синтетический мир; не game acceptance после wipe.
Старый полный restore откатывает и часы. 82 focused Linux Docker cases и восемь
проверок replay; Windows/full CI — в [протоколе](validation/player-time-2026-11-13.json).
#43 открыт для rollback/lifetime, #44 — для chat welcome. [Контракт](PLAYER_TIME.md).

## Настройки Forge/Docker-журналов — 13 ноября 2026

Следующий ограниченный этап #30/#33: два validated env для генерации Forge 1.12.2
Log4j XML, прежние 8 МиБ/3 gzip и XML с LF при defaults. Остальные версии сохраняют
declared logging. Отдельно два env для local driver проверочных candidate slots:
точные config/driver фиксируются в плане и проверяются в snapshot. Старые schema-1
планы без обоих полей читаются как прежние 10m/3, без миграции/перезаписи policy;
добавить новый override в legacy план нельзя. LOG_BYTES остаётся пределом readback.
Новых CLI/collectors/host schedules нет. Frozen XML существующего runtime не
переписывается переменной задним числом. Добавлены examples и logging inventory.

120 focused Linux Docker cases; Windows 119/1 skipped. Red/green двух hardcode
контролей. Native Java 8/Log4j 2.25.5: 16 checks (14 unique), ротация/exception/
filter/restart/читаемые gzip и большой event выше порога. Настоящий CT FileLogger
4.1.20.711 подтвердил старый inode после rename и старый offset после truncate.
Groovy проверен по exact v1.4.3 source, не native game. Поэтому онлайн-ограничение
CT/Groovy требует отдельного writer adapter/startup/reload/ENOSPC/recipe regression;
оно остаётся #30, не заменяется внешним logrotate или лимитами diagnostic ZIP.

Второй native Docker: production creation/snapshot, 16 checks; реальные local
1m/2 и legacy 10m/3, отказ mismatch, loopback/owned volume/sandbox, Java fixture
после большого stdout завершился 0, OOM=false. Только command/metadata заменены
контролируемой fixture; это не полный resource reset или игра Forge. Свои scopes
удалены. Owned JAR, game data и VPS прежние; общий config/storage audit открыт.
[Протокол](validation/forge-log-policy-2026-11-13.json).

## Хвосты script logs в диагностике владельца — 13 ноября 2026

Ограниченный шаг #30: прежний export_bundle не включал отдельные ошибки рецептов/
скриптов. Добавлена точная allowlist корневого crafttweaker.log и logs/groovy*.log
(только два известных имени). Нет glob всех логов, новых endpoints, CLI или
collectors; player distribution не получает экспортёр. Четыре env управляют
размером фрагмента/всего текста и count/byte retention ZIP; defaults прежние,
проверка до записи и без echo значения. Переполнение после redaction также
ограничено, budget omissions отмечены. Новый ZIP сохраняется при rollback часов.

53 focused Linux Docker cases; Windows 51/2 skipped (symlink controls в Linux).
Отдельный Docker verifier: 10 проверок с readonly source и named output volume,
EROFS на контрольной записи, ZIP/allowlist/tail/redaction/limits/retention.
Исходные bytes/mtime прежние, собственные scopes удалены; crash/OOM нет.
Red/green: исходный exporter пропускает mod logs, исправленный включает их.
Это синтетические логи, не новый запуск DJ2. Активные mod writers, общий storage
budget и оставшийся config audit остаются #30/#33; VPS/game/launcher не менялись.
[Контракт](LOGGING.md#лимиты-экспорта-владельца),
[протокол](validation/diagnostic-script-logs-2026-11-13.json).

## Ползунок памяти без wheel input — 13 ноября 2026

Обычный QSlider менял и сохранял RAM при прокрутке списка сборок. Узкий subclass
игнорирует wheel event, оставляя его родительскому scroll area даже при focus.
Клавиатура/drag, доступность planned GTNH, профили и limits прежние. Без нового
UI, настроек или network calls. 14 Qt cases: оба focus состояния, вертикальные/
горизонтальные angle/pixel deltas, Ctrl, сохранность файла preferences, прокрутка
списка и настоящий drag/key. Доставка через Qt window, а не sendEvent прямо
виджету: прямой synthetic event не проверяет parent scroll dispatch.

На исходном QSlider 9 failures/5 passes; после правки 14 passes. Общий UI suite
79 passed. Actual Qt PNG и отдельный portable Windows EXE; mock account на PNG,
не новая игровая приёмка. VPS/owned JAR/Minecraft не изменены.

## Часовые группы с наблюдавшимися игроками — 13 ноября 2026

Следующий ограниченный шаг #146: `hours_with_players_report` в прежнем read-only
owner API. Выбор по ненулевому online, раздельные host/config, счётчики доступных
и отсутствующих readings; нет новых writers, schema migration, таблиц или CLI.
Это whole-hour совпадение: CPU mean/max включают простой/обслуживание того же часа,
показания online не превращаются в playtime. Ограничения rows/bytes до фильтрации;
empty+truncated не доказывает отсутствие игроков за оставшийся период.

86 focused Linux Docker cases, 84 Windows /2 skipped. 13 новых контролей:
partial/unknown/stopped, host/config/game, sub-hour window, scan cap, readonly,
сохранение hour после удаления details с контролируемым временем 179 дней.
Второй Linux Docker replay: 31 сохранённый настоящий sample DJ2 из #155,
семь независимых проверок одного выбранного часа/пика online=2 и min/max/mean.
DB на readonly mount и исходный capture побайтно прежние; свои containers удалены.
Это replay, не новый запуск Minecraft, не 179 дней настоящей игры и не RX-4 test.
Точные maintenance/активные интервалы и actual VPS остаются #146/#38.
Лаунчер/owned JAR/game content/VPS прежние.
[Контракт](RESOURCE_HISTORY.md#часы-в-которых-зафиксированы-игроки).

## Сброс скина и настройки аккаунта — 13 ноября 2026

Добавлен подтверждаемый сброс на bundled Стива в белой футболке. Повторно
используется upload_game_skin с текущим game token; management token и пароль
не требуются. Cancel/Esc без запроса, loader/общий busy guard, прежнее превью
до успеха. Кнопка отключена во время подготовки сборки. Окно пароля расширено,
подписи центрируются после layout parenting (до него sizeHint давал 26 вместо
стилизованных 48 px); warning без переноса и две равные кнопки на всю ширину.
Остальные правила смены пароля/отзыва сессий сохраняются.

Настоящий fresh persistent Docker Drasl: 18 проверок сброса, сохранности второго
аккаунта, game-token ownership, смены пароля/отзыва старой сессии и restart.
Первый проход получил 500 вместо клиентского отказа; исходные результаты
сохранены. Причина — HandleYggdrasilError не распознавал явный 4xx UserError.
Небольшой patch в `4.0.0-omk.3` сохраняет код без внутренних текстов; неизвестные
ошибки остаются 500. Девять Go-контролей, обычный auth smoke дополнен reset/invalid
PNG. Первая Docker-сборка не получила новые файлы из allowlist; .dockerignore
расширен явно, свежая сборка и native повтор пройдены.

Qt PNG просмотрены, portable Windows EXE проходит startup smoke. Computer Use
дважды отказал в захвате кадра; внешние клики не выполнялись. Это не новая
графическая/Minecraft-проверка. Нужные UI-состояния проверены Qt-тестами отдельно.
Полный Windows unit/UI: 2152 passed /95 skipped; 33 Qt + Drasl smoke checks.
CI выявил старый поиск QDialogButtonBox в GUI lab: обновлены stable button IDs,
callback errors закрывают modal, ожидание ограничено watchdog. Новая проверка
подтверждает fail-fast; настоящий Qt выполняет cancel/reset/password round trip.
VPS/game runtime/owned JAR/player release прежние.
[Протокол](validation/launcher-account-controls-2026-11-13.json).

## Системные требования в карточках — 13 ноября 2026

По запросу владельца добавлена компактная справка для каждой сборки: общая ОЗУ,
CPU/графика/SSD, ОС, отдельная оговорка для Mac и память Java из текущего профиля.
Необязательные typed данные остаются в servers.toml; GUI общий, без ветвлений
по сборкам и дополнительных запросов API. Нет нового запрета запуска по оценке
железа, ползунки/память/установка прежние, planned GTNH по-прежнему недоступна.

Для DJ2 16 ГБ общей памяти/20 ГБ SSD — предварительные ориентиры проекта,
не аппаратная приёмка, минимум или официальные требования автора. Нижний порог
оставлен неподтверждённым. Apple M1+ /16 ГБ — кандидат для проверки; настоящая
игра Intel/Apple Silicon остаётся #36. Фиктивный аккаунт в Qt PNG не выдаётся
за игру на Mac. Требования GTNH ещё не выбраны, её статус не повышен.
13 новых unit/UI cases; отдельно PNG и запуск portable Windows EXE.
VPS/game runtime/owned JAR/player release прежние.
[Контракт и ограничения](CLIENT_REQUIREMENTS.md).

## Игровая часть истории ресурсов — 13 ноября 2026

После PR #154 добавлен generic opt-in Core 0.3.7: скользящие фактические TPS,
штатные tick rings mean/p95/max/loaded dimensions, online и JVM heap/GC.
Main thread снимает числа, отдельный bounded writer публикует private atomic JSON.
Collector читает только readonly metrics volume; без сети/Docker socket/RCON,
невалидное/stale/остановленное состояние не превращается в нулевые active gauges.
Прежний config без games совместим; новые env/overlay и read-only отчёт прежнего API.

27 Java controls; два Docker build одинакового Core SHA, Fix/Client прежние.
73 focused Linux cases; Windows 2131 unit/UI /95 skipped. Настоящая DJ2 2.23.4,
двое Drasl actors, два старта/rejoin, pause/stale/TPS recovery; 19 native checks,
31 row и два game boot. Отдельный minimal Forge без DJ2/FTB: восемь checks,
отказ/возобновление записи не останавливают игру, ошибка ограниченно логируется.
Оба game scope завершены без crash/OOM, собственные volumes удалены после экспорта.
Отдельный Linux verifier: 11 checks истории/сохранения, 7 изумрудов/12 уровней.

Первый fixture неверно приравнивал MXBean max к -Xmx4G. Отдельный тот же Java 8
показал 3817865216 байт; fixture исправлен, старый отказ сохранён. Следующий проход
подтвердил loss короткого TPS interval между producer 5s и collector 10s: seq 7
успел смениться seq 8. Добавлено bounded rolling window, fresh game pass принят.
Ранние helper mount/import/PYTHONPATH ошибки сохранены отдельно, не входят в pass.

Финальный collector добавляет interval/truncation gauges: после full native pass
проверен в новом image на четырёх сохранённых настоящих Core snapshots — 30 checks.
Это replay, не новый запуск игры. Raw fixtures/аккаунты/миры остаются приватными.
#146 открыт для job correlation/active-hour report; #38 — actual VPS/длительная
игра. #41 ready_for_players=false. Core hash закреплён только после native pass;
рабочие manifests, GUI/player release/VPS прежние. Перед VPS аудит владельца.
[Контракт](GAME_RESOURCE_HISTORY.md), [протокол](validation/game-resource-history-2026-11-13.json).

## Подготовка к аудиту и история ресурсов — 13 ноября 2026

Владелец поручил привести локальную подготовку DJ2 к завершению перед просмотром.
VPS до его аудита не разворачиваем. [Входная точка](LAUNCH_READINESS.md) связывает
контракты с актуальными issues; открытые требования не объявляются выполненными
по одному наличию документации или CI трёх ОС. GTNH и отложенные функции вне
первого запуска.

Добавлен opt-in Python Docker collector без сети/портов/Docker socket: allowlisted
Linux host/cgroup counters, метаданные разрешённых ФС, private bounded SQLite,
подробности до 7 дней и часовые сводки до 180 дней. Env budgets/defaults; 64 MiB
main DB, budget journal 129 MiB плюс reserve. При capacity более раннее вытеснение,
при пропуске/смене наблюдаемого источника новый baseline; недоступность не ноль.
Report API read-only для owner/будущей TUI, новых omk-команд/игровых экранов нет.

47 focused Linux Docker cases; Windows 2105 unit/UI /95 skipped. Отдельный native
Linux cgroup-v2 lab с настоящим bounded CPU/OOM: 0.50 ядра при quota 0.5, OOM kill
виден в parent, workload restart и SIGKILL collector, fresh committed health,
exit 73 между detail/hour INSERT и успешное SQLite recovery. Семь samples,
45056 байт history, integrity ok; свои containers/volume удалены, collector OOM
не было. Это не запуск Minecraft, host power loss или измерение RX-4.

Первый Linux unit fixture не включил новый example config: 44 pass/1 missing-file;
после исправления frozen overlay повторно пройдены все 47 cases. История исходного
отказа сохранена. Игровые TPS/MSPT, online/heap/GC, корреляция и actual VPS остаются
#146; сам issue не закрывается. Общий допуск #41 false, Java/launcher/player
release прежние. [Контракт](RESOURCE_HISTORY.md),
[протокол](validation/resource-history-2026-11-13.json).

## Комплект одного остановленного проекта — 13 ноября 2026

PR #153 принят в dev после 9/9 CI, завершённая ветка удалена. Новый внутренний
Linux capture использует существующий world ZIP и фактические закрытые game/auth/
runtime/выбранные operator источники. Drasl config входит в комплект и сверяется
с source hash. Девять файлов, manifest последним, private permissions и env caps;
новых CLI/расписания/stop-start и второго live world backup writer нет.

Настоящая DJ2 2.23.4/Core 0.3.6/Fix 0.1.4 + Drasl 4.0.0-omk.2: два actors
вошли, получили вещи/XP; clean stop и один existing cold snapshot. Выявлены
34 case-пары runtime: добавлен явный Linux-only case-sensitive inventory,
portable default прежний. Реальный auth restart во время capture запрещает seal.
Источник свежего lab продолжен после ошибок fixture, исходные reports сохранены.

Согласованный комплект прошёл настоящий REST/TLS: exit 73 после upload до ACK,
новый worker, тот же snapshot, exact readback/full repository read, без reupload.
Independent Linux verifier: 9 файлов, 2319 runtime/5 auth/15 operator, 514517369
байт TAR payload, ZIP CRC 317 entries, все case-пары и actual runtime source,
SQLite/key и две player→account связи. Вещи/XP в readback ZIP проверены отдельно
existing NBT reader. Текстур в этом новом источнике не было, skin coverage не
добавлено. Clean game/auth exit 0, без crash/OOM; свои scopes удалены после экспорта.

28 новых cases; Windows 2060 unit/UI /93 skipped, Linux Docker focused 655,
Ruff/Black. Это не GUI, full application boot, power-loss или нагрузочный тест.
Caller держит общий owner lock и проверяет соответствие mounts/checkpoints;
выбор полного operator/deployment inventory принадлежит профилю. Дальше #33:
durable export/lifecycle + общий budget/retention в единственном nightly,
внешнее destination и quarantine/authority return. #41/#146 открыты; VPS,
launcher/owned JAR/player release прежние, ready_for_players=false.
Перед VPS — аудит владельца. [Контракт](PROJECT_EXPORT.md),
[протокол](validation/project-export-2026-11-13.json).

## Durable ownership передачи — 12 ноября 2026

После принятого PR #151 добавлен Linux `TransferStore` для готовых архивов:
private volume, frozen intent до upload, fsync/atomic replace, общий flock,
наследуемый дочерним restic. Второй controller не получает ownership, пока жив
старый restic, даже после SIGKILL управляющего Python. Попытанный upload не
переиздаётся; явное recovery ищет прежний ID и обязательно делает exact readback.
Без snapshot попытка остаётся неоднозначной. Новых CLI, host jobs и второго
writer игры нет. Limits через OMK_OFFSITE_JOB_MAX_RECORDS/BYTES; записи не удаляются.

29 новых cases; Windows 2054 unit/UI /71 skipped (Linux owner tests пропущены),
Linux Docker focused 627. Отдельно 9 настоящих REST/TLS условий: конкурирующие
controllers, exits 71/73/75, живой restic после SIGKILL Python, input drift.
Отрицательный контроль без наследования fd показал потерю fence; исправный
вариант держит его до завершения того же дочернего процесса. Независимый Linux
verifier: 5 завершённых records /23 файла, 20 сравнений исходных архивов,
ZIP CRC 321 entry, auth TAR/SQLite/key/skins. Свои scopes удалены, OOM нет.

Это local flock одного общего Linux store, не distributed lock. Controller
timeout не переживает смерть controller: живой orphan держит busy до выхода;
внешний bounded worker lifecycle ещё не подключён. Status verified — историческая
сверка, не новая проверка доступности remote. Остаток atomic tmp требует осмотра,
не удаляется автоматически. При 128 попытках следующая prepare отказывает:
лимит/архивацию надо учесть до включения долгого расписания.

Дальше #33: согласованный project export одного источника world/auth/runtime/
operator, интеграция transfer/lifecycle с одним nightly, внешнее destination и
retention, полный quarantine/authority return. Архивы этого опыта из разных
прежних labs, новая игра/Drasl не запускались. #41/#146 открыты; VPS/launcher/
Java/player release прежние, ready_for_players=false. Перед VPS аудит владельца.
[Порядок](OFFSITE_TRANSPORT.md#сохранение-и-продолжение-передачи-на-linux),
[протокол](validation/offsite-transfer-2026-11-12.json).

## REST/TLS транспорт готовых архивов — 12 ноября 2026

PR #150 принят в dev после 9/9 CI, завершённая ветка удалена. Следующий шаг #33 —
Python primitives restic 0.19.1: pinned бинарник, TLS/auth/repository ID,
изолированное окружение и bounded процесс. Секреты читаются из private readonly
файлов, не argv/Docker Env; raw child output не попадает в ошибки. Новых CLI,
таймеров/host jobs и второго writer живого Minecraft нет.

Upload подтверждает только передачу с прежними source SHA; отдельный staging
restore сверяет полный набор файлов/размеры/SHA. Exit 3/timeout/lost ACK не дают
автоматического повтора или unlock. Lookup по тому же ID ещё не concurrency
fence: durable owner coordinator/worker ownership остаются следующей работой.
Read-only операции не создают remote lock; backup/full check сохраняют его.
Это исправило реальный отказ quota/507 при попытке чтения полного хранилища.

24 Linux Docker transport-условия с готовыми архивами разных принятых labs:
реальный exit 73 после upload, настоящий partial exit 3, peer kill/restart,
quota, corruption/control, readonly repository и раздельные client/server secrets.
Независимый Linux verifier: 7 restore /42 файла, ZIP CRC 321 entry, auth TAR/
SQLite/signing key/skins, operator archive 18 файлов. OOM нет, свои ресурсы удалены.
59 новых cases, Windows 2048 unit/UI /48 skipped, Linux focused 598, Ruff/Black.

Ранние непринятые trials сохранены: зависимость от psutil через admin import
убрана (stdlib-only image), CRLF исправлен red/green; locked metadata/restore
отказывали на full/readonly repo. Диагностический local CLI без внутреннего
deadline остановлен по точному собственному readonly mount; runtime bounded
worker не ослаблялся. Финальная свежая серия принята отдельно, исходные reports
не исправлялись. Подготовка Linux unit overlay один раз отказала до Docker из-за
отсутствующей новой папки; fixture исправлен, пройден свежий запуск.

Согласованный project snapshot, durable transfer/nightly integration, внешний
fault domain/retention и полный application recovery остаются #33; ресурсная
история — #146. #41 открыт, ready_for_players=false. Игра/Drasl не запускались,
runtime payload/VPS/launcher/Java/player releases прежние. Перед VPS — аудит
владельца. [Интерфейс/лимиты](OFFSITE_TRANSPORT.md),
[протокол](validation/offsite-transport-2026-11-12.json).

## Ограниченная история ночных journals — 12 ноября 2026

Календарный runner PR #149 принят в dev после 9/9 CI, завершённая ветка удалена.
Новый opt-in Python service переносит только complete nightly и четыре
подтверждённых child records перед следующим countdown. Новых CLI-действий нет.
Последние семь завершённых scopes остаются live; active/cancelled и отдельные
ручные операции не архивируются. Каждый архив содержит исходные байты и SHA;
все пять публикуются/fsync/проверяются до unlink, root удаляется последним.
Старые status/cross-reference/calendar ACK читаются через history fallback;
архивные действия и повторное использование ID отказывают до server effects.

Env limits: default 10000 файлов /256 MiB логических данных, batch 32 и keep 7.
Запись сохраняет общий project reserve на FS истории. История не вытесняется:
при заполнении новый перенос/цикл отказывает до чата, прежние recovery-ссылки
сохраняются. История лежит в `.omk-admin/journal-history`, переносится с полным
operator state, а не только world ZIP. Не filesystem quota и не off-host copy.

56 новых cases; Windows 1989 unit/UI /48 skipped, Linux focused 539, Ruff/Black.
11 отдельных Linux Docker filesystem-условий на копии принятых реальных DJ2
journals: exact bytes, реальные exit 71/72/73 до publication/после publication/
в cleanup, два owner-процесса, hardlink/conflict/cap и readonly mount. Старый
native export побайтно прежний, свои scopes удалены после экспорта. Это не
новый запуск Minecraft и не потеря питания host. Первичный suite отказал только
из-за изменённого текста ошибки identifier; совместимость восстановлена и
контроль пройден. Во время этого этапа серверные миры не монтировались.

Default archive/schedule disabled, host jobs/VPS не установлены. До VPS остаётся
аудит владельца; off-host и оставшийся full recovery/cutover — #33, ресурсная
история — #146. #41 открыт, ready_for_players=false. Лаунчер/Java/player release
прежние. [Порядок](NIGHTLY_BACKUPS.md#ограниченная-история-завершённых-циклов),
[протокол](validation/journal-history-2026-11-12.json).

## Календарный runner с восстановлением — 12 ноября 2026

Opt-in `nightly watch --server` использует существующий цикл и один приватный
cursor на сервер. По умолчанию disabled, host job/VPS не установлены. Дата и
ID фиксируются до preflight; потерянное подтверждение подхватывает только тот
же root с проверенным origin. Общий owner lock допускает два процесса без
двойного цикла. Пропущенное окно не догоняется, DST gap/fold и откат часов
учитываются. Ошибка оставляет тот же root для существующих run/status/cancel.

До отсчёта проверяются TTL и slots всех journals, включая два ingress.
Журналы автоматически не удаляются: default 128 ingress хватает примерно на
64 ночи, а не на полгода. Для 180 циклов ориентир M/B journal_count=512 с запасом
на ручные операции и проверкой общего диска; безопасная архивация связанных
journals остаётся #33. Сохранённое armed не доказывает живой процесс watcher.

Полная DJ2 2.23.4/Core 0.3.6: 22 native /41 independent условия. Игра и сам
owner controller работают в Linux Docker; readonly код и приватный durable
state разделены. Первый реальный Python-процесс завершён через os._exit(73)
после fsynced root до cursor ACK. Два новых watcher продолжают тот же root/
четыре child IDs: каждое предупреждение один раз обоим Drasl-аккаунтам, один
архив, два старта того же source. Оба аккаунта снова вошли; CRC/SHA/manifest
и вещи/XP проверены в копии и final NBT. Оба watcher затем SIGKILL (137,
не OOM); новый процесс сохраняет будущую дату без повторного цикла сегодня.
Весь frozen код в Linux volume побайтно прежний. Clean game stop/no crash/OOM;
свои scopes удалены после экспорта. Это protocol actors, не GUI, и не новый
тест потери питания host посреди stop/start. Docker socket даёт owner authority.

Ранний fixture отказал до расписания из-за системного Python без зависимостей;
интерпретатор исправлен, непринятые scopes экспортированы/очищены. Другой проход
прерван при загрузке Forge: WSL/Docker engine перестал отвечать, calendar ещё
не стартовал. Владелец отдельно разрешил restart WSL; после восстановления
этот scope экспортирован/очищен и выполнен свежий принятый проход. Исходные
неуспешные результаты сохранены. Offline verifier сначала захватил лишний
controller-files.json широким glob; исправлен выбор по точным watcher IDs,
исходный native report не менялся.

45 новых cases; Windows 1933 unit/UI /48 skipped, Linux Docker focused 483
под 2 CPU/1 GiB, source readonly, без сети; Ruff/Black/public source boundary.
Лаунчер, owned JAR и player releases не изменены. Перед VPS — аудит владельца.
Следующие #33: ограниченная архивация связанных journals, off-host и оставшийся
full recovery/cutover. Ресурсная история #146 и #41 остаются открыты;
ready_for_players=false. [Интерфейс](NIGHTLY_BACKUPS.md),
[протокол и границы](validation/nightly-calendar-2026-11-12.json).

## Явный цикл backup/restart с продолжением — 12 ноября 2026

HAProxy остаётся admission barrier. Перед развёртыванием на уже купленном PL
RX-4 владелец проведёт аудит всего репозитория; deploy до этого не делаем.

`nightly run/status/cancel` объединяет существующие owner services в одну
приватную durable операцию: чат → close → clean stop → verified cold backup →
same-container start/readiness → open. Для восстановления используется тот же
ID и заранее выбранные дочерние IDs; попытанные действия не отправляются заново.
Отсчёт запускается явно сейчас, а не в LOCAL_TIME. Автоматический календарный
scheduler не реализован и не включён; это остаётся отдельным шагом #33.

Stock FTB должен быть disabled/idle и в файле, и в Java. До закрытия/записи
проверяются общий census, caps, staging и max(project reserve, backup reserve).
Во время ожидания нет повторного сканирования всего runtime каждую секунду;
проверки выполняются перед сообщением/действием. Общий owner lock освобождается
на ожидании; reentrant composition того же потока не снимает OS exclusion для
другого потока/процесса. Отмена до stop не открывает ingress и не запускает Java.

Первый native candidate сохранил вход закрытым после успешного restart из-за
слишком строгого полного digest до/после boot. Runtime целиком сверяется перед
stop/start, затем Forge может записать generated files. После старта остаются
точные FTB JAR/config, loaded disabled/idle и новый Core boot; существующий
maintenance start guard не ослаблялся. Старое строгое условие воспроизводит
отрицательный unit control; FTB artifact/config drift по-прежнему отказывает.
Непринятый scope с исходным report экспортирован и очищен, не выдан за успех.

Свежая DJ2 2.23.4/Linux Docker с постоянным Drasl volume: 26 native и 32
independent условия, два старта одного source, два аккаунта. Потеря пяти ACK
после реальных close/stop/publish/start/open не повторяет эффекты; оба игрока
получают каждое предупреждение и повторно входят с прежними вещами/XP.
CRC/SHA/manifest новой копии проверены, один prepare/publish. Изменившиеся при
boot файлы: server.properties, Astral Sorcery amulet config, Team Reborn NBT;
FTB config/Core/Fix прежние. Без game crash/OOM, свои scopes очищены после
экспорта. Это protocol actors и controller interruption, не GUI/power-loss test.

CI затем выявил отдельную read-only regression: BackupStore.inspect открывал
lock в r+b, что отказывало на readonly volume после инициализации store. На
Linux используется rb + shared flock, publisher сохраняет exclusive lock;
Windows byte-range locking прежний. Красный Docker control воспроизвёл отказ,
после исправления пройдены 13 cold-backups условий, включая restart/600 MiB,
и отдельное readonly чтение принятого DJ2 archive с прежними четырьмя файлами.
Native nightly/maintenance modules прежние; этот filesystem follow-up испытан
отдельно, без повторной полной загрузки Minecraft.

55 новых Python cases; Windows 1888 unit/UI /48 skipped, Linux focused 438
под 2 CPU/1 GiB, Ruff/Black/source boundary. Моды/лаунчер/release payloads
этим изменением не обновляются. [Команды и границы](NIGHTLY_BACKUPS.md),
[протокол](validation/nightly-cycle-2026-11-12.json). Далее #33: календарный
запуск без догоняющих/двойных jobs, off-host и оставшийся полный recovery/cutover;
#146 — приватная ресурсная история. #41 остаётся открытой.

## Внутренний maintenance bridge без роста CLI — 12 ноября 2026

Владелец просит сохранять небольшой набор owner-действий для будущей Rust TUI.
Рабочая логика остаётся в типизированных Python services; новые CLI-команды
добавляются только для конкретной операторской/recovery потребности. Rust TUI
пока не реализуем. В этом этапе новых CLI-действий нет.

Для VPS согласована приватная долгосрочная история host/container ресурсов с
TPS/MSPT/онлайном и служебными интервалами. Хранение ограничивается retention и
byte budget; будущая TUI использует тот же источник данных. Сбор ещё не включён,
отдельная задача [#146](https://github.com/omkality/omkalitycraft/issues/146) привязана
к первому запуску; стек выбирается при реализации и проверяется в Linux Docker.

Core 0.3.6 имеет RCON-only bridge с main-thread probe/warning, boot identity и
bounded retry fences без вытеснения. Общий Core API получает optional backup
provider; FTB integration читает реальные поля reviewed stock 1.1.0.1 после
проверки версии/SHA. Неподдержанная policy, активный backup, старый boot и sender
игрок отказывают. Поздняя отменённая задача не рассылает сообщение; частичный
сбой оставляет unconfirmed fence. Произвольных сообщений/команд/world writes нет.

Полная DJ2/Linux Docker: два Drasl-игрока, два старта одного контейнера. Изменение
FTB config на диске не подменяет loaded state до restart; затем disabled proof.
Русское предупреждение принято обоими, повтор и реальная потеря RCON-ответа не
дают второй рассылки; OP-игрок тоже не может использовать bridge. 14 игровых
условий +2 экспортных, 32 independent. Human OP не остался; известный Forge fake
profile отделён. Clean stop/no crash/OOM, own scopes удалены после экспорта.

Первый candidate отказал в loaded adapter из-за file-only JAR URL handling;
jar:file regression пройден red/green, непринятый scope экспортирован/очищен.
В успешном игровом проходе postprocess ожидал versioned filename, тогда как
fixture ставит стабильный Core.jar; также no-human-OP check уточнён до прежнего
known Forge fake profile. Два file assertions завершены offline по исходному
экспорту; исходный report сохранён, игровой код для этого не менялся.

36 новых Python cases; Windows 1833 unit/UI /48 skipped, Linux focused 340;
12 Java maintenance/14 client controls, source boundary и два повторяемых Docker
build. Core SHA закреплён; DJ2Fix 0.1.4 и Client 0.1.1 прежние. Выпускной контент
и VPS не переключались. Scheduler, full nightly transaction, общая owner reserve
перед записью и off-host остаются #33; #41 открыт, ready_for_players=false.
[Интерфейс/ограничения](NIGHTLY_BACKUPS.md),
[протокол](validation/maintenance-bridge-2026-11-12.json).

## Календарь и read-only допуск ночной политики — 12 ноября 2026

`omk admin nightly preview/inspect` готовит следующий ночной coordinator:
env-время/timezone/countdown, пропуск опоздавшего окна/DST gap и единственное
первое вхождение DST fold. Inspect проверяет явный adapter, pinned FTB JAR,
канонический config с выключенными enabled/shutdown и неизменность runtime/
container/volume через readonly Linux helper и общий owner lock.

Полная DJ2 2.23.4/Linux Docker: два старта того же контейнера, 12 native /
25 independent условий. Включённый stock FTB даёт CRC/level.dat-положительную
копию и отказ preflight; выключенный — running/stopped disk proof. При наблюдении
не менее 195 секунд через полный 180-секундный timer, manual/shutdown controls
новые stock archives/receipt не появляются. Все 1809 экспортированных runtime/
backup файлов прежние до/после inspect; crash/OOM нет, own scopes удалены.

67 новых synthetic cases, Windows 1742 unit +55 UI /48 skipped, Linux focused
280 (включая четыре Linux-only link cases), Ruff/Black/source boundary. Инспекция
остаётся disk-only: live_config_verified/other_writers_verified/activation_approved
false; host cron/чужой Docker CLI/ручные OP-команды не исключены. Scheduler и chat
warnings не реализованы/не включены, working FTB config и VPS прежние.

Следующий этап #33 — durable coordinator с chat warning adapter, единственным
writer, reserve перед записью, interrupted-step recovery и связанной цепочкой
close → stop → backup → ready → open. Не обходить guards существующих операций.
Off-host и остальные #32/#38/#41 остаются открытыми. [Команды и границы](NIGHTLY_BACKUPS.md),
[протокол](validation/nightly-preflight-2026-11-12.json).

## Stock FTB retention и выбор ночного режима — 12 ноября 2026

Владелец выбрал запланированный ночной рестарт с предупреждением в чате.
Следующий координатор должен иметь настраиваемые время/timezone/countdown,
один writer, отключённые stock periodic/shutdown backups и уже проверенную
цепочку closed ingress → clean stop → verified publish-before-rotate → start/
readiness → explicit open. Сам scheduler ещё не реализован и не включён.

Неизменённый FTBBackups1.1.0.1 испытан на полной DJ2/Linux Docker: 13 native /
20 independent условий, два проверенных старых ZIP и искусственный I/O отказ
нового output после quota-loop. Оба прежних архива удалены до отказа. После
явного initial save положительный контроль содержит level.dat, CRC и согласованный
success receipt. Game crash/OOM нет, свои scopes удалены после экспорта.
Это отказ output через каталог, не ENOSPC. Одних stock-настроек недостаточно,
чтобы считать ротацию безопасной при ошибке новой копии.

Один ранний log-matcher отказ исключён (нормальный /srv/./ путь). Второй ранний
прогон сохранён как отдельное наблюдение: первый hot backup свежего мира дал
success и CRC-valid ZIP без level.dat; после stop файл появился в мире. Это не
принято как пригодная копия, обобщения на все рабочие миры нет. Оба scopes
экспортированы/очищены; последующий retention trial имеет saved-world precondition.
Runtime/FTB config рабочего сервера не менялся. PR #143 принят после 9/9 CI.
[Решение/границы](NIGHTLY_BACKUPS.md), [протокол](validation/ftb-retention-2026-11-12.json).

## Проектный census и проверка бюджетов — 12 ноября 2026

`omk admin storage estate` объединяет все серверы из backups.toml и явные
auth/content/reports/exports volumes из приватного storage.toml. Считываются
только метаданные; ownership/config identities сверяются до/после. Общие тома
не могут совпадать с source/store/staging, обязательный auth не пропускается.
Старый per-server inspect сохраняет прежний контракт.

Объём категорий сопоставляется с единым OMK_STORAGE_* планом. Общий filesystem
не складывается по числу mounts; остаток вне census/reserved blocks виден отдельно
и консервативно учитывается в system. Для нескольких FS один общий бюджет не
объявляется пригодным. Declared caps текущего CLI сравниваются суммарно: два
backup лимита по 48 ГиБ не считаются совместимыми с project backup budget 48 ГиБ.
Существующие store policies не читаются и не мигрируются этим наблюдением.

Настоящая CLI/Linux Docker: 38 условий, десять новых томов, 7700 файлов, две
независимые копии принятых DJ2 экспортов и настоящий Drasl. Учёт сверён независимо,
все SHA game/store/staging/auth/shared до/после прежние; секреты не выведены.
Drasl после restart сохранил account/skin/signature. Own scopes удалены; Minecraft
не запускался, вторая копия не является приёмкой GTNH. 42 новых synthetic случая,
Linux focused 568; Windows 1734 unit/UI / 44 skipped (13 новых Linux-only cases
проверены в Docker). Артефакты зафиксированы в протоколе. Учёт unknown
host usage принят red/green. Ruff/Black/source boundary.

Следующий этап #33 — выбор и приёмка одного periodic writer/scheduler, reserve
перед записью, retention и encrypted off-host. Census — не quota/atomic snapshot,
не backup integrity proof и не допуск игроков; `admission_approved=false`.
#38/#41 остаются открытыми; VPS не менялся.
[Реестр/команда](PROJECT_STORAGE.md), [протокол](validation/project-storage-2026-11-12.json).

## Linux-права несекретного ingress template — 12 ноября 2026

Воспроизведён реальный different-UID отказ HAProxy: leaf `700` / file `600`
другого host owner не читаются root-контейнером с ALL caps dropped. `prepare`
теперь готовит только несекретный leaf `755` / template `644`; приватный parent
`700`, credentials и admin socket `600` прежние. Legacy leaf исправляется при
повторном prepare только после точного content proof и отсутствия unknown files.

Настоящий pinned HAProxy/Linux Docker: 7 условий, UID 12345 против container UID0,
legacy negative и исправленный positive config-check, реальный closed runtime с
нулём sessions, socket 600, clean stop и удаление собственных scopes. Два новых
unit случая; Windows 1705 / 31 skipped, Linux focused 526, Ruff/Black.
Это proxy-приёмка, Minecraft не запускался. Игровой функционал/порты не менялись.

PR #140 и #141 приняты в dev после 9/9 CI каждый. Следующий объём #33 остаётся
общим budget/scheduler/off-host; #32 — остальными transport adapters/online
evacuation, затем graphical и VPS deployment #38/#41.
[Права и повторная подготовка](OWNER_INGRESS.md),
[протокол](validation/ingress-linux-uid-2026-11-12.json).

## Read-only учёт диска — 12 ноября 2026

`omk admin storage inspect --server dj2` считает метаданные source/store и явно
настроенных reset/restore volumes. Source разделяется на active world, всю
retained/partial историю, logs/crash/pack backups и runtime/other. Logical и
allocated bytes раздельны; общий filesystem free не складывается по числу mounts.
Низкий резерв отражается в JSON. Содержимое файлов не читается/не выводится;
ссылки, special files, превышение env-лимитов и изменение во время обхода дают отказ.

Настоящая CLI/Linux Docker на копиях принятых DJ2 экспортов: 16 условий,
четыре свежих volumes, 5324 файла / 632 retained. Число/размеры сверены независимо,
все байты прежние до/после; свои тома удалены. Minecraft здесь не запускался.
31 synthetic случай, Linux focused 524; Windows 1703 unit/UI / 31 skipped
(15 новых skip относятся к Linux-only FS, проверены в Linux Docker).
Минимум free для последующего mount проверен red/green. Ruff/Black/source boundary.

PR #140 принят в dev после 9/9 CI. Следующий этап #33 — общий host/Drasl/Docker
budget, выбранный один scheduler и off-host копии. Текущий отчёт не включает все
orphan volumes/images/container logs и не является атомарным snapshot либо
проверкой целостности backup. Никакая автоматическая очистка не добавлена.
#32/#38/#41 открыты; VPS deploy/graphical landing после установки отдельно.
[Руководство](OWNER_STORAGE.md),
[протокол](validation/owner-storage-2026-11-12.json).

## Установка нового мира в тот же контейнер — 12 ноября 2026

Owner `world-cutovers plan/apply/verify/recover/revert/cancel/commit/status`
устанавливает sealed не запущенный ресурсный кандидат в прежний stopped source.
Runtime/auth/proxy/порты/backup binding прежние; меняется только world directory.
Прежний мир удерживается рядом. Два fsynced перемещения восстанавливаются явно,
повторного копирования нет; возврат разрешён только до первого start.
Потерянный commit заканчивается изменением журналов, без перезаписи world.

Старая попытка получает отзываемый nonce: запоздавший helper не пишет после
отмены/подтверждения. Linux проверен с другим host UID и ALL caps dropped;
публичное readonly зеркало содержит только fence, приватный журнал остаётся 600.
Pending установка блокирует обычные backup/restore/maintenance/open операции.
После commit обычные backup и restart используют стандартный путь.

Полная DJ2 2.23.4 / Linux Docker: 61 native / 134 independent условий, два
Drasl-аккаунта, три старта того же source, ни одного target boot, две копии.
324 исходных файла точно сохранены после pre-start revert; установленные
306 world-файлов совпадают с sealed target. 2015 runtime-файлов / 480187632 байта
прежние; 632 файла удержанной истории сверены. Вещи/XP/UUID, остальные FTB homes,
claims/authority сохранены; новый ресурс создаётся и переживает обычный restart.
Игровых крашей/OOM нет, own scopes удалены после экспорта.

39 новых synthetic случаев; Windows 1687 unit/UI / 16 skipped, Linux focused
493. Отдельно Linux Docker: 17 FS fault условий, два настоящих SIGKILL между
перемещениями и реальный tmpfs ENOSPC; плюс два different-UID permission контроля.
Это синтетические данные, не игровые краши. Ruff/Black/source boundary пройдены.
Core 0.3.5 / Fix 0.1.4 / Client 0.1.1, player releases и periodic writer прежние.

Следующий этап #33 — read-only учёт active/retained/staging/backup/logs и общего
свободного резерва; затем единый scheduler/off-host budget. #32 сохраняет online
evacuation, оставшиеся adapters/порталы и wipe других разрешённых миров.
Root-owned source adapter и loopback admission пока обязательны. Графическая
высадка после установки, публичный ingress и VPS deploy отдельно; #41 открыт,
`ready_for_players=false`. [Команды](OWNER_WORLD_CUTOVERS.md),
[обезличенный протокол](validation/dj2-owner-world-cutover-2026-11-12.json).

## Закрытый вход перед обслуживанием — 12 ноября 2026

Owner `ingress prepare/inspect/plan/apply/verify/status/cancel` управляет одним
исходным сервером через pinned HAProxy TCP. Loopback only; boot/restart закрыты,
новые подключения не проходят, существующие сохраняются до штатного game stop.
Maintenance фиксирует deployment и требует закрытый вход до stop intent.
Открытие требует текущую готовность source и отсутствие pending M/R/S/I.
Потерянные open/close ответы проверяются без повторной записи; после proxy
restart старый open intent отменяется только при проверенном закрытии.

Linux Docker / полная DJ2 2.23.4: 62 native / 185 independent условий,
два Drasl-аккаунта, два source boot, один candidate boot и один backup.
Сохранены вещи/XP/UUID/позиции и остальные FTB-данные; исходные 324 world-файлов
неизменны при trial. Возврат исходника оставляет вход закрытым до нового плана.
Own scopes удалены после экспорта. Два ранних отказа утилиты/fixture исключены,
Minecraft не падал; финальная приёмка на замороженной копии controller/helpers.

69 новых synthetic случаев, Windows 1648 unit/UI / 16 skipped, Linux focused
454; Ruff/Black/source boundary. Compose defaults/overrides совпадают с owner
policy. Core/Fix/Client и player releases прежние, periodic backup writer не
добавлен. Источник видит IP proxy, а не отдельного игрока; эта граница явно описана.

Следующий этап #32/#33 — явное cutover/recovery подготовленного мира; затем
оставшиеся adapters/online evacuation и общий storage budget с одним scheduler.
Публичного ingress, переключения профиля и deploy нет; `ready_for_players=false`,
#41 открыт. Покупка PL RX-4 подтверждена, доступы пока не передавались; локальная
приёмка продолжается. [Команды/настройки](OWNER_INGRESS.md),
[обезличенный протокол](validation/dj2-owner-ingress-2026-11-12.json).

## Owner loopback candidate lifecycle — 11 ноября 2026

`resource-resets slot-plan/create/start/stop/status/reconcile/release` создаёт
проверочный контейнер вокруг sealed кандидата. Явный Forge template, pinned
image/JAR, public Drasl metadata и owned bridge; game/RCON только loopback.
Source остаётся выключенным, source/store read-only при proof. Сохраняются
полный runtime receipt, immutable container ID и durable lifecycle intents.
При потере ответа reconcile проверяет факты без повторных lifecycle-команд.
Чистый stop и bounded private log предшествуют release; volume сохраняется.
Parent abandon запрещён до подтверждённого release, даже если контейнера уже нет.

Linux Docker / полная DJ2 2.23.4: 42 native / 130 independent условий. Два
Drasl-аккаунта, один backup, два старта source и один owner-start кандидата.
Потеря каждого из четырёх ответов восстановлена, оба игрока вошли, `/resource`
работает, прежний source вернулся. 320 исходных world-файлов неизменны во время
trial; 302 файла кандидата и 2015 runtime-файлов сверены. Typed вещи/XP/UUID,
остальные FTB homes/claims и исходный ресурс сохранены. Все own scopes удалены
после экспорта. Один fixture-export отказ исключён; источник сверён и сохранён.

55 новых synthetic случаев; Windows 1579 unit/UI / 16 skipped, Linux focused
385; Ruff/Black/source boundary/credential-pattern scan. Invalid transition
guard дополнительно проверен red/green после native, успешный путь неизменен.
Core 0.3.5 / DJ2Fix 0.1.4 / Client 0.1.1 и player releases прежние. PlaneFix fake
OP policy не менялась; readiness не является permissions/игровой приёмкой.

Следующий этап #32/#33 — закрыть вход при переключении и проверить explicit
cutover/recovery; online-эвакуация, оставшиеся модовые ссылки, общее ограничение
хранения и один scheduler отдельно. Restart после stop внутри того же slot,
публичное переключение и wipe любого измерения пока не поддерживаются.
`ready_for_players=false`; #41 открыта. VPS для следующего изолированного этапа
пока не нужен. [Команды и пределы](OWNER_CANDIDATE_SLOTS.md),
[протокол](validation/dj2-owner-candidate-slot-2026-11-11.json).

## Окружение reset-кандидата и пробный запуск — 11 ноября 2026

Owner `resource-resets runtime-plan/runtime-stage/runtime-verify` готовит точные
известные runtime/access/EULA-файлы вокруг завершённого data stage. Один writer,
source/store read-only, полный receipt и readonly recovery потерянного ответа.
Считается общий world+runtime staging budget и свободный резерв; права и
согласие EULA не меняются ради запуска, непустые OP отклоняются. Корневые
логи/cache/backup не наследуются, рабочие Java-каталоги создаются пустыми.
Барьер maintenance и все ready-флаги сохраняются.

Реальный отказ на pack case-sensitive путях воспроизведён в Linux red/green.
Runtime сохраняет регистр; world ZIP validator не менялся. В принятом runtime
34 группы разных по регистру путей. Symlink/hardlink/неизвестные target files,
изменение source/access, частичная копия и повторная запись отклоняются.

Полная DJ2 2.23.4 / Linux Docker: 49 native / 121 independent условий. Два
исходных старта и два lab-only старта кандидата, два Drasl-аккаунта, один backup.
Все 320 исходных world-файлов неизменны во время подготовки и trial; в кандидате
302 файла. Все 2015 runtime-файлов / 480187632 байта совпадают с источником.
Вещи/XP/UUID сохранены; resource home не возвращается, другой home и claims
остальных миров сохраняются. Новый ресурс создаётся с прежней frozen policy/seed
и переживает restart. После удаления своего trial container и abandon исходник
возвращён со своим прежним ресурсом. Свои scopes очищены после экспорта.

Два ранних опыта исключены: runtime casefold gate (исправлен) и fixture race
создания restart-log (не Minecraft crash). У обоих исходник неизменён, собственные
resources очищены после экспорта. 48 новых synthetic случаев; Windows 1524
unit/UI / 16 skipped, Linux focused 330; Ruff/Black/source boundary/secret scan.

Core 0.3.5 / DJ2Fix 0.1.4 / Client 0.1.1 и player releases прежние. Это проверенная
упаковка окружения с отдельным приватным trial, не owner create/start/cutover.
Следующий этап #32/#33 — явный immutable deployment slot, закрытый внешний вход
до приёмки, журнал переключения и возврат при неясном исходе. Нельзя просто
клонировать Docker Inspect Env/Args или автоматически откатывать уже принятые
игровые изменения. Online evacuation, оставшиеся adapters и графическая проверка
также открыты; #41 остаётся открыт. VPS пока не нужен.
[Команды](OWNER_RESOURCE_STAGING.md),
[протокол](validation/dj2-resource-runtime-2026-11-11.json).

## Owner resource staging и барьер возврата — 11 ноября 2026

`omk admin resource-resets` готовит отдельный data-only target только из
остановленного maintenance window и завершённого cold backup этой остановки.
Source/store read-only; один stage в пустой явно принадлежащий target, durable
intent и readonly verify после потери acknowledgement. `list` возвращает ID без
Docker. Пока кандидат не abandoned, исходное окно не start/cancel; abandon
сохраняет файлы и разрешает возврат исходного immutable контейнера.

Общий реестр restore/reset исключает совпадение с любыми source/store/peer
volumes. Политика и preflight env заморожены. Исправлен obsolete v1 gate в
inspection: adapter/SHA берётся из текущего reviewed data profile, проверяется
до/после worker. Red/green регрессия и future-profile/hash-race контроли прошли.

Полная DJ2 2.23.4 / Linux Docker: 30 native + 70 independent условий. Два
аккаунта, два старта исходного сервера, один реальный backup, два отдельных
кандидата (один после потери ответа stage). При обеих подготовках 320 исходных
world-файлов прежние; каждый target 302 файла / 4 изменения / 18 исключений.
Ресурсные home/197 claims очищены; остальные home/1444 claims, FTB authority,
typed inventory/XP/UUID сохранены. Барьер и явный abandon проверены. Исходник
запущен с прежним ресурсом; все собственные Docker scopes очищены после экспорта.

44 новых synthetic случая; Windows 1425 unit + 55 UI / 12 skipped, Linux focused
282; Ruff/Black. Один ранний fixture-прогон с конвертированным Underground Biomes
каменным полом исключён; железная платформа принята без ослабления allowlist.
Графический клиент/кандидат не запускались. Core 0.3.5 / DJ2Fix 0.1.4 / Client
0.1.1 прежние. Переключение, online evacuation, более широкие адаптеры и реальная
игровая высадка после reset остаются в #32; единый scheduler/off-host budget —
в #33; #41 открыт. VPS пока не нужен.
[Руководство](OWNER_RESOURCE_STAGING.md),
[обезличенный протокол](validation/dj2-owner-resource-staging-2026-11-11.json).

## Остановка, копия и возврат того же контейнера — 11 ноября 2026

Owner-only `omk admin maintenance` фиксирует pinned container/volume identities,
runtime и точный loopback RCON binding. Штатная остановка принимается только по
clean Docker checkpoint; запуск того же immutable ID требует завершённый backup
этой остановки и readonly повторную проверку фактического архива/world/runtime.
`Done` дополняется Core readiness и 15 секундами устойчивого состояния.
Порядок stop/start проверяется по меткам одного Docker engine, независимо от
расхождения часов VM и хоста; host intent timestamp остаётся полем аудита.
Durable intents / `reconcile` не повторяют lifecycle-команды; stopped `cancel`
оставляет источник выключенным. Пределы задаются env, журналы ограничены.

Полная DJ2 2.23.4 в Linux Docker: 34 native / 60 независимых условий, три clean
старта/stop, два Drasl-аккаунта, две копии. 317 / 344 / 344 world-файла;
весь фактический ZIP побайтно совпадает с соответствующим остановленным миром.
Типизированные Inventory, XP, UUID, survival и основной мир сохранены.
Прерывания после stop/start приняты через reconcile; предыдущая копия и
параллельное окно отвергнуты. Собственные game/auth/store scopes очищены
после экспорта. Отдельный real Docker + fake RCON контроль остаётся synthetic.

51 новых synthetic тестов; Linux focused 144, Windows unit/UI 1436/12 skipped,
Ruff/Black/secret scan. Пять ранних неподтверждённых прогонов исключены;
ограничения доказательств явно сохранены в протоколе. Подготовка игровых
состояний идёт через stdin-очередь; произвольные world-команды vanilla RCON
не добавлены. Allowlist восстановления аккаунта прежняя.

Core 0.3.5 / DJ2Fix 0.1.4 / Client 0.1.1 и player releases прежние. Это
same-container maintenance, не promotion новой копии и не owner wipe.
Единственный периодический writer/off-host copy, барьер и cutover/recovery
остаются в #33/#32; #41 открыт. Графическая, Hard/PvP и полная quest-приёмка
этим шагом не повторяются. VPS пока не нужен.
[Руководство](OWNER_MAINTENANCE.md),
[обезличенный протокол](validation/dj2-owner-maintenance-2026-11-11.json).

## EnderItems: доступ, reset и restart — 11 ноября 2026

Python-адаптер v2 расширен стандартным 27-слотовым EnderItems в `.dat`/`.dat_old`.
Preflight v3 требует новый frozen plan вместо v1/v2; неизвестные слоты/схемы,
вложенные сумки и остальные хранилища не допускаются. Source/backup read-only,
ручной data-only режим отвязку не включает. Pins/JAR и allowlist прежние.

Полная DJ2 / Linux Docker: 81 native / 107 independent условий, три clean старта,
восемь серверных переносов через сундук. Два аккаунта видят свои предметы до/после
reset; 12 ссылок очищены в обеих записях первого игрока. Три изменения при stage,
301 retained файл побайтно прежний, 19 старых ресурсных файлов исключены.
Очищенный Porter заново привязан, возвращён в сундук, получен и использован после
restart. Полное типизированное NBT/количество, опыт и контрольные вещи сохранены.

14 новых synthetic случаев; фокус адаптера 61, Linux focused 143, Windows unit/UI
1385/12 skipped; Ruff/Black. Три ранних fixture-отказа исключены, четыре своих
scopes очищены после экспорта. Protocol transfers приняты по server save;
отрицательные prediction confirmations фикстуры не выданы за графическую приёмку.
Core 0.3.5 / DJ2Fix 0.1.4 / Client 0.1.1 прежние. Owner wipe закрыт;
`ready_for_start=false`, `ready_for_players=false`, #32/#41 открыты.
[Границы и сценарий](RESOURCE_RESET_ENDERCHEST.md),
[протокол](validation/dj2-enderchest-reset-2026-11-11.json). VPS пока не нужен.

## Ender Utilities: отвязка и повторная привязка после reset — 10 ноября 2026

Добавлен узкий Python-адаптер остановленной копии: location crystals tier 0
в Inventory и модулях Ender Porter, включая невыбранные, в player `.dat`/`.dat_old`.
Удаляется только Target сбрасываемого мира; основной Target, заряд, выбор
модуля и остальные NBT сохраняются. Admission требует точный SHA Ender Utilities
0.7.15, типизированную схему и замороженный preflight v2; неизвестные хранилища
и tiers остаются блокирующими. Ручной data-only режим адаптер не включает.

Полная DJ2 / Linux Docker: 39 native условий, 56 независимых, три чистых запуска.
Сверены штатная отвязка, настоящий расход заряда, source read-only, шесть ссылок
в обеих записях игрока, эвакуация и новая копия. При stage меняются три файла,
остальные 295 retained файлов побайтно прежние; 19 ресурсных файлов исключены.
Очищенный модуль заново привязывается обычным sneak + block use, работает
между мирами и после restart; старая ресурсная площадка отсутствует.

47 новых синтетических тестов; Linux focused 129, Windows unit/UI 1371/12 skipped,
Ruff/Black. Неоднозначные NBT-ключи экранируются до сопоставления с допущенными
путями; дефект воспроизведён отрицательным контролем, итоговый scanner повторно
проверен на том же native source с полным совпадением frozen preflight.
Core 0.3.5 / DJ2Fix 0.1.4 / Client 0.1.1 и player manifests не менялись.
Это не графическая или Hard/PvP приёмка. Рабочий owner wipe закрыт;
`ready_for_start=false`, `ready_for_players=false`, #32/#41 открыты.
[Границы адаптера](RESOURCE_RESET_ENDERUTILITIES.md),
[обезличенный протокол](validation/dj2-enderutilities-reset-2026-11-10.json).

## Серверные условия переносимого телепортера — 10 ноября 2026

DJ2Fix 0.1.4 проверяет штатное право доступа к предмету, актуальную загруженную
цель и достаточный заряд на серверном потоке до побочных эффектов. Основной
контроль полной DJ2 в Linux Docker: 65 условий с observer, 91 независимое
условие по сохранениям/очистке. Прежний дефект 0.1.3 подтверждён отдельно;
не засчитываем отсутствие адресата за проверку заряда. Обе руки, точная
стоимость и публичная частота работают; отказ не меняет позицию/инвентарь.
Выгруженный мир не загружается запросом, после обычной загрузки переход работает.

Core 0.3.5 / Client 0.1.1 побайтно прежние; новый Fix `d0b31385…` воспроизводится
двумя Linux Docker build. Windows unit/UI 1324/12 skipped, Ruff/Black.
Restart сохранённой сети и новая копия после data reset приняты отдельно:
59 native условий / 62 независимых, три clean старта/stop. После restart/reset
пустое устройство не меняет игрока/предмет, заряженное штатно работает в новой
основной сети; два владельца и retained-связи сохранены. При stage меняются
два файла, остальные 327 retained файлов побайтно прежние; 19 старых ресурсных
файлов исключены. Все свои game/auth volumes удалены после экспорта.
Ранние несовместимый профиль, ожидание cooldown и выгрузка цели исключены;
для принятого lifecycle-повтора адресат удерживал аутентифицированный witness.
Рабочие manifests/releases/миры и owner wipe не включаются,
`ready_for_players=false`; #32/#41 остаются в плане.
[Правило и границы](DJ2_MEKANISM_PORTABLE.md),
[протокол](validation/dj2-mekanism-portable-2026-11-10.json). VPS пока не нужен.

## Публичные исходники Forge-модов — 10 ноября 2026

По явному решению владельца собственные реализации Core 0.3.5, DJ2Fix 0.1.3
и Client 0.1.1 теперь развиваются в `mods/forge-1.12.2/` этого монорепозитория.
Это чистый импорт исходников без прежней Git-истории. Полный приватный checkout
`../omkalitycore` и проверенный bundle его истории сохраняются как архив и
native-лаборатория. Старые записи ниже о приватности исходников описывают прошлые
этапы; дальнейшие изменения production-исходников делаются в публичном каталоге.

Код и ресурсы дают точно прежние JAR: Core `786fa897…`, DJ2Fix `9063ad85…`,
Client `817a40a4…`. Два повтора в Linux Docker сверяют полный SHA256, Java 8
class version, отсутствие ABI/зависимостей/пробников и разделение компонентов.
13 Python build-safety контролей, 14 Java helper-условий клиента и два Forge
splash target дополняют проверку сборки; игровая приёмка этим шагом не повторяется.
Скрытые входы старого Forge manifest заменены явным compile-only Log4j API и
минимальным ABI-типом; метаданные и порядок ZIP закреплены независимо от ОС.

Внешние JAR не публикуются. Лаборатория, полные протоколы, миры, аккаунты и
детальные воспроизведения открытых проблем остаются приватными. #128 всё ещё
требует исправления; source publication не включает guard и не закрывает #32/#41.
Новые правила описаны в [mods README](../mods/README.md) и
[инструкции сборки/версий](../mods/forge-1.12.2/README.md).
GitHub Releases остаются лаунчерными; компонентные теги отмечают исходный снимок.

Решение владельца после измерений #89: дополнительный кеш преобразований
не внедряем, риск не оправдывает выигрыш. #89 закрыта как `not planned`;
исследование остаётся историей. Продолжаем обязательную приёмку DJ2 / reset #32.

## Mekanism: частная сеть после ресурсного сброса — 9 ноября 2026

Два полных прохода полной DJ2 в Linux Docker: физические рамки, два владельца
частных частот, отказ без рамки/энергии, native round trip, полный restart,
offline-эвакуация и новая копия после reset. После удаления ресурсного измерения
старая точка перестала быть адресатом, основные устройства и отдельная частота
другого владельца сохранены; новый основной адрес снова принимает переход.

52 проверки на проход (с повторами observer), шесть чистых стартов/остановок.
Creative-пилот дополнен полным survival-проходом с независимой проверкой режима
и четырёх контрольных точек здоровья. Stopped TAR/Anvil/NBT: 40 / 46 проверок;
325 → 348 → 329 → 346 файлов, два изменения при stage, 327 retained файлов
побайтно совпадают. Два manager-файла до stop содержат три частоты, после stop
списки пусты; physical Tile NBT и native restart подтверждают восстановление
проверенной сети, но не сохранность неиспользуемых имён частот.

Focused reset 154, Ruff/Black; observer пересобран с тем же SHA256. Ранние ошибки
подготовки исключены; пять своих scopes, девять game и пять auth volumes очищены.
Core 0.3.5 / DJ2Fix 0.1.3 не менялись. Переносимые устройства, public/unloaded
адресаты, другие модовые сети, production adapters и owner barrier/recovery
остаются в #32. `ready_for_start=false`, `portal_adapters_reviewed=false`,
`ready_for_players=false`. [Границы приёмки](RESOURCE_RESET_MEKANISM.md),
[протокол](validation/dj2-mekanism-reset-2026-11-09.json). VPS пока не нужен.

## Измерение загрузки DJ2 — 9 ноября 2026

По отдельному запросу владельца выполнено исследование #89: десять принятых
запусков обычного Windows-клиента DJ2 2.23.4 без MCP-мода, включая отдельный
read-only profiler, cache fault и настоящий сборщик логов. Первый запуск 168.745 с,
обычные повторы 144.811–149.927 с; opt-in кеш классов VintageFix — 129.353–130.184 с.
Разница медиан 18.155 с / 12.27% на одном ПК. Profiler исключён из A/B; граница
меню подтверждена `GuiCustom`, время загрузки модов не выдано за полный старт.

Флаг **не включён в рабочий профиль**: нужны инвалидация runtime/mod/config,
обновление/откат и игровая регрессия. Исходные runtime/mods/config, manifest,
серверные Docker-службы и player releases не менялись. Сохранность локального
discovery-кеша при install/repair/update проверена отдельно от его native parser;
повреждённый кеш пересоздан и прочитан следующим клиентом. Два запуска неполной
первой фикстуры исключены. Принятые клиенты штатно закрыты; исходные config/mods
сверены по SHA256, в полной копии нет crash-report/hs_err. После решения владельца
#89 закрыта без внедрения кандидата.
[Выводы и методика](DJ2_STARTUP_PERFORMANCE.md),
[протокол](validation/dj2-startup-performance-2026-11-09.json).
Обязательная приёмка resource reset #32 продолжается следующим этапом; VPS пока не нужен.

## RFTools: устройства, переносимые блоки и reset — 9 ноября 2026

Read-only preflight теперь учитывает `destinationId` переносимого приёмника,
штатный unbound `-1` и неполную отвязку Porter с оставшимся `tpTimer`.
Сначала воспроизведены пропуски/ложные срабатывания, затем добавлены регрессии.
Это не автоматическая перепись предметов: рабочий owner wipe ещё закрыт.

Полная DJ2 в Linux Docker: 45 условий / три чистых запуска, реальные transmitter,
receiver и использование Porter игровыми пакетами. Basic штатно не хватает
20k RF для межмирового перехода за 150k; Advanced возвращает игрока без урона.
Подтверждены сохранение ID в native block drop и его восстановление, выборочная
тестовая отвязка, offline reset/stage, основной прогресс устройств и обычная
установка очищенного блока. Игрок без выдачи OP не строит в спавне, но строит
снаружи; новый receiver получает новый ID. Независимый аудит: 37 проверок,
340 → 321 файл, два изменения, остальные 319 retained файлов побайтно сохранены.

Windows unit/UI 1322/12 skipped; focused 115; Linux fault controls 55; Ruff/Black.
Ранние ошибки фикстур и поздняя diagnostic race исключены; свои шесть scopes /
12 game + 6 auth volumes очищены, дополнительный пустой volume удалён после
проверки. Core 0.3.5 / DJ2Fix 0.1.3 не менялись. Owner transport adapters,
online-эвакуация, barrier/recovery и другие порталы остаются в #32.
`ready_for_start=false`, `portal_adapters_reviewed=false`, `ready_for_players=false`.
[Устройство и границы](RESOURCE_RESET_RFTOOLS.md),
[протокол](validation/dj2-rftools-reset-2026-11-09.json). VPS пока не нужен.

Администрирование: **игровых OP не будет ни у кого**, включая владельца;
управление — из консоли/owner-операций. Пустой список OP и отсутствие игровых
административных разрешений — критерий настройки перед запуском, не новая
применённая конфигурация существующих служб. Rust TUI для владельца — идея на
позже поверх общих операций `omk`; сейчас её не разрабатываем.

## Безопасная точка и известные модовые ссылки — 9 ноября 2026

Owner `resource-resets inspect --preflight` читает защищённый сохранённый спавн,
Anvil/NEID и известные NBT-ссылки модов, включая числовые приёмники/осиротевшие
ID RFTools и Ender Utilities Target. Внутренний data stage принимает `position:"auto"`
и замораживает proof/policy в плане. Env-лимиты не требуют коммитов. Неподдерживаемый
формат, отсутствие безопасной точки, известные ссылки или source/runtime drift
дают отказ; обход всех возможных модовых сериализаторов не заявляется.

Полная DJ2 в Linux Docker: 20 условий / три чистых запуска, заблокированный
смещённый спавн → соседняя точка, offline-вход в candidate. Нативные serializers
RFTools/Ender Utilities и Mekanism Frequency; 29 независимых TAR/NBT проверок,
339 → 321 файл, два изменения, остальные 319 retained файлов побайтно сохранены.
Настоящий owner Docker-worker дал тот же proof. Linux fault controls 47;
Windows unit/UI 1314 passed / 12 skipped, focused 146, Ruff/Black. Повторный
полный опыт также прошёл; ранние ошибки фикстур исключены. Свои четыре native
scopes / восемь game + четыре auth volumes и отдельный readonly probe очищены.

Core 0.3.5 / DJ2Fix 0.1.3 не менялись. Полноценные transport adapters, online
эвакуация и owner lifecycle/recovery впереди: `ready_for_start=false`,
`portal_adapters_reviewed=false`, `ready_for_players=false`. #32 открыта.
[Команда, профили и ограничения](RESOURCE_RESET_PREFLIGHT.md),
[протокол](validation/dj2-resource-preflight-2026-11-09.json). VPS пока не нужен.

## Нативный restart после ресурсного сброса — 9 ноября 2026

На новой копии из свежего backup полной DJ2 2.23.4 в Linux Docker прошли offline
эвакуация, очистка ресурсных homes/warps/claims, сохранение основного мира, вещей,
опыта и двух нативных retrieval-квестов; повторный restart и `/resource`/`/spawn`.
Core 0.3.5 / DJ2Fix 0.1.3 не менялись. 107 условий (28 нового reset этапа),
четыре штатных запуска, 39 независимых stopped TAR/NBT/QuestProgress проверок.
352 → 331 файл, ровно пять рассмотренных изменений; 1445 иных claims сохранены,
старый ресурсный player claim убран, новые 196 server claims спавна восстановлены.
Ранние ошибки фикстуры исключены; три своих scopes/девять game volumes и три
auth volumes очищены. Другие проекты и постоянный UI-preview не менялись.

Это **не owner-wipe и не автоматическое разрешение старта**: safety произвольной
точки/порталы/shared data, online-эвакуация и lifecycle/recovery ещё предстоят.
Owner CLI inspect-only; `ready_for_players=false`. Нового backup writer нет.
[Правила и границы проверки](RESOURCE_RESET_RESTART.md),
[протокол](validation/dj2-resource-reset-restart-2026-11-09.json). #32 открыта.

## Оформление и новые решения — 8 ноября 2026

По запросу владельца пробуем obsidian black + ice gray: Qt-палитра, форма входа,
карточки/персонаж/прогресс/ссылки; Forge/DJ2 appearance пока отдельный overlay.
В меню только центрированная надпись, на загрузке — блок руды и название проекта.
Сторонний featured server из Ender Modpack Tweaks выключается в staging.
[Устройство, локальный preview и границы проверки](CLIENT_APPEARANCE.md),
[#117](https://github.com/omkality/omkalitycraft/issues/117).

Будущие серверы проекта: **PvP и Hard**. Это deployment-критерий для всех
профилей; не рекламировать его как проверенное поведение существующих миров.
Новые рабочие конфиги/VPS/player releases этим прототипом не разворачиваются.
Ресурсный reset #32 и остальные launch-критерии остаются в плане.

## Data staging ресурсного сброса — 7 ноября 2026

Внутренний Linux worker строит новую копию мира из **последнего проверенного
backup, точно совпадающего с текущим источником**. Пустой target, эксклюзивный
план до записи, SHA source/runtime/result, бюджет/staging/reserve, fsync и
независимый verify перед receipt. Старые ресурсная DIM/внешняя запись только
исключаются из копии; source/store read-only. Нового backup writer нет.

Разобраны player NBT/`.dat_old`, Forge respawn без удаления основной кровати,
FTB homes/warps/claims/back и current/legacy JED. Остальные файлы/неизвестные
данные сохраняются. Транспорт в ресурсе, неизвестный формат, изменение источника,
неподходящий ID и неполный target отклоняются. Отдельно исправлен реальный отказ
переноса FTB authority для ownerless server team; текущие запреты и отсутствие
владельца сохраняются вместо исторических. Red/green regression подтверждён.

По требованию владельца правило очистки действует при вайпе **любого** мира:
все его приваты/дома/публичные варпы и известные back-ссылки удаляются. FTB 5.4
адаптер выделен отдельно, проверен на 13 ID (0, отрицательные, положительные и
динамический), в Linux — также на native ссылках основного/ресурсного миров.
Это общий data-контракт; разрешение и процедура вайпа остальных миров отдельны.

Docker: **28 условий** data worker, **11** независимых проверок данных внутри
Linux и **23** независимых stopped TAR-проверки. Native архив: 320 → 301 файл,
ровно 19 исключённых и три изменённых записи; прочие байты основного мира,
квестов, Astral data и 1444 server claims сохранены. Гонка оставляет одного
writer; реальная маленькая tmpfs, смерть процесса, повтор и подмена region
дают отказ. Шесть успешных data scopes / 32 своих volumes очищены и сверены.
Windows unit/UI: **1249 passed / 12 skipped**, Ruff/Black.

**Minecraft после reset в этом этапе не запускался**. Непустые beds/back/warps,
`.dat_old` и JED tracker проверены синтетически; native архив их не содержал.
Owner CLI остаётся inspect-only. `ready_for_start=false`: нужны безопасная точка,
модовые порталы/shared saved data, online/offline эвакуация и native restart с
квестами; затем owner lifecycle/controller и полноценная приёмка #32.
[Устройство и ограничения](RESOURCE_RESET_STAGING.md),
[протокол](validation/dj2-resource-reset-staging-2026-11-07.json).
Core/Fix, рабочие миры, границы, manifest, releases и расписания не менялись.
`ready_for_players=false`; VPS для этого шага не нужен.

## Read-only проверка перед сбросом — 7 ноября 2026

`omk admin resource-resets inspect` читает явно настроенный остановленный Linux
Docker source: player NBT/резервные записи/respawn, FTB homes/warps/claims/back,
JED dimensions. Общий owner lock, checkpoint до/после, SHA закреплённых JAR,
resource policy и paired ownership markers; source/rootfs readonly, без сети,
backup mount и Docker socket. Ошибки формата/identity/drift отклоняются; таймаут
не оставляет свой helper при доступном daemon. Это **не reset plan/apply** и не
проверка пригодности бэкапа; модовые порталы остаются непрочитанными.

На native save найден корректный ownerless server team FTB. Валидатор теперь
принимает его без выдумывания владельца; обычные команды по-прежнему требуют
Owner, изменение Owner/fake-player permissions по-прежнему различается.

Linux data worker и полный owner CLI — **27 условий**, включая Docker metadata
fixture, read-only enforcement, отказы ID/действий и очистку прерванного helper.
Архив взят из прежнего игрового опыта; нового Minecraft boot или wipe здесь нет.
Неполные ранние проверки исключены, свои ресурсы очищены. Windows unit/UI:
**1188 passed / 12 skipped**, focused **153/1**, Ruff/Black.
[Команда/папки/ограничения](RESOURCE_RESET_INSPECTION.md),
[протокол](validation/dj2-resource-inspection-2026-11-07.json).
Далее #32: исполняемый план новой копии со свежим backup, перенос offline/online
игроков и ссылок, порталы, прерывания и квесты после настоящего reset/restart.
Core/Fix, рабочие миры, границы, расписания и player releases не менялись.
`ready_for_players=false`; VPS для этого шага не требуется.

## Графический ресурсный мир и контракт сброса — 7 ноября 2026

Настоящий Windows-клиент/MCMCP + Linux Docker: на неизменных Core **0.3.5** /
DJ2Fix **0.1.3** и **server view-distance=6** прошли первый вход `/resource`,
`/spawn`, межмировой home, rejoin, скин/мини-карта и server-owned защита. Клиент
отрисовал 49/49 чанков; server observer подтвердил отправку. Граница проверена
отдельно. **29** независимых stopped TAR/NBT-проверок подтвердили сохранения.

При дальности 3 дважды воспроизведены пропущенные чанки первого входа. Изменение
очереди выгрузки не помогло и откатилось; нового Core-релиза нет. В контроле с
дальностью 6 все mods/config/scripts/groovy совпали, отличалось только это значение
server.properties. Рабочая настройка проверена, первопричина/минимальный порог ещё
не установлены ([#113](https://github.com/omkality/omkalitycraft/issues/113)). Fullscreen JourneyMap не подтверждена автоматизацией. RTP в
непрогенерированной зоне ожидаемо отказал; рабочие радиусы повторить после #37.

Три графических клиента и четыре игровых сервера закрылись штатно; пять своих
scopes очищены, неуспешный prestart-стенд исключён. **61** focused unit-тест,
Ruff/Black. [Протокол](RESOURCE_CLIENT.md). Далее #32: исполняемая процедура
сброса с backup, online/offline игроками, homes/claims/порталами и сохранением
квестов. [Контракт](RESOURCE_WORLD.md#контракт-безопасного-сброса) записан;
read-only reference inventory не является wipe. Manifest/гайд, lifecycle/storage,
откат базы и финальная предгенерация остаются в плане. `ready_for_players=false`.
VPS пока не требуется; рабочие данные, player releases и backup writers не менялись.

## Ресурсная генерация, могила на входе и квесты — 7 ноября 2026

Кандидат **Core 0.3.5 / DJ2Fix 0.1.3** дополняет основу ниже. Python готовит
проверенные копии CoFH/Extreme Reactors/Natura/Integrated Dynamics/Thaumcraft;
переносятся и запреты основного мира, без расширения сюжетных ресурсов. JED требует
точного DimensionType. DJ2Fix пересчитывает штатные фильтры Thaumcraft после поздней
регистрации JED и до инициализации ресурсного мира; имя/артефакты/результат проверяются.
Общий Core не получил зависимости от Thaumcraft. Новый требуемый статус DJ2 —
`fix.resource.generation`.

Тест смерти обнаружил реальную блокировку `/resource` собственной могилой в точке
входа на 0.3.4. В 0.3.5 при преграде выполняется ограниченный повторный поиск с
проверкой текущих FTB server claims. Могила сохраняется. Полное отсутствие точки
не становится runtime-fault; восстановление границы возвращает вход без restart.

Linux Docker, 4 CPU / 6 GiB / heap 4 GiB: **78 условий полной DJ2 / два запуска**,
**94 общего Core без DJ2Fix / два запуска**. Независимое сравнение по **75**
полностью сгенерированных чанков до/после подтвердило ресурсы; широкий stopped
снимок — 123 Vis-кристалла всех шести типов в 206 чанках. Два native retrieval-квеста
прошли переход/смерть/restart; QuestProgress/player NBT подтвердили владельца,
незабранные награды, вещи/опыт и сохранённую могилу при новой точке входа.
Минимальное сохранение — ещё **33** проверки. Это не полное прохождение DJ2;
условия включают preflight/метаданные, предметы для квестов выдавались консолью.

Повторные SHA совпали; API и прежние реализации защит byte-identical. Семь своих
scopes очищены; три неполных/отклонённых опыта исключены. Unit/UI Windows
**1127 passed / 12 skipped**, Ruff/Black. [Устройство и результаты](RESOURCE_GENERATION.md),
[обезличенный протокол](validation/dj2-resource-generation-2026-11-07.json).

Далее #32: графический клиент/JED, client manifest/гайд, безопасный owner reset с
backup и эвакуацией online/offline игроков, homes/claims/portals и квестами после
сброса. Lifecycle/storage #33/#38, откат базы #34 и финальная предгенерация #37
сохранены. VPS пока не нужен. Рабочие данные, manifest, player releases и backup
writers не переключены; `ready_for_players=false`.

## Основа ресурсного мира — 7 ноября 2026

Core **0.3.4** содержит необязательный общий JED/FTB-адаптер, DJ2Fix **0.1.2**
сохранён. Профиль DJ2 выбирает -18000 с обычным генератором, собственным seed и
WorldInfo/границей. Никакой подмены папок другого мира. `/resource` делегирует
права и SPAWN timer настоящей команде FTB `/spawn`; движение, урон, отзыв прав,
повторные запросы и два игрока проверены. Ресурсный спавн ±100 защищён FTB,
своя могила выдаёт вещи через Shift; `/rtp` остаётся в ресурсном измерении.

`omk policy dj2-resource` готовит исключительно новую staging-папку с SHA,
проверяя env и создавая копию UB whitelist. Команда не применяет конфигурацию,
не скачивает JAR, не запускает сервер и не выполняет wipe. Внутренняя запись
в DIM и внешняя в корне мира запрещают незаметное пересоздание потерянных
данных и присвоение чужой папки. Runtime-fault блокирует вход, даёт один лог,
сохраняет `/spawn` и требует проверки/restart. Пустые временные загрузки
отпускаются через очередь Forge с сохранением принудительных загрузок модов.

Linux Docker: **98 условий полной DJ2 / два старта**, **90 минимального Forge /
два старта**, **10 отдельных контролей / 67 условий** (восемь ожидаемых отказов,
два здоровых старта без JED и без FTB). Проверены расширение ресурсной границы
16k → 32k и сохранность после restart, та же identity, вещи/опыт/home/claim.
Условия включают подготовку и чтение метаданных, не только игровые действия.
Независимые stopped TAR/Anvil/NBT: **71 + 60 проверок**. Нормальные старты
stop 0/no fatal/no OOM; повторная сборка совпала, 36 проверок состава, прежние
API/guard classes byte-identical. Все **33 собственных scopes** очищены и
сверены; 21 ранний/неполный опыт не входит в приёмку. Windows unit/UI
**1113 passed / 12 skipped**, Ruff/Black.

[Устройство, команды, env и папки](RESOURCE_WORLD.md),
[обезличенный протокол](validation/dj2-resource-foundation-2026-11-07.json).
#32 остаётся открытой. Далее: адаптация особых Overworld-совместимых whitelist
CoFH без открытия сюжетных ресурсов, графический клиент/JED и квестовый прогресс;
затем owner-only reset с backup, эвакуацией online/offline игроков, homes/claims/
portals и восстановлением при сбое. Lifecycle/storage #33/#38, откат базы #34,
финальная предгенерация #37 остаются отдельными этапами. VPS пока не требуется.
Рабочие профили/миры, client manifest, player releases и backup-расписания не
переключены; второго backup writer нет. `ready_for_players=false`.

## Квота связных территорий FTB — 7 ноября 2026

Core **0.3.3** добавляет необязательную общую политику FTB: 3 территории на участника,
3/6/9 для команды из 1/2/3 игроков. Чанки 50/150 и личные дома остаются у FTB.
Диагонали/измерения разделены; команды, native GUI-запросы и pending queue покрыты.
Снятие мостового чанка сверх квоты отклоняется до записи. При уменьшении команды
базы сохраняются, соединение участков разрешено. Server-owned спавн освобождён от
квоты участников. DJ2Fix **0.1.2** не изменён; новых mixin/игровых команд/БД нет.

Владелец готовит env-политику через **`omk policy dj2-territories`**: просмотр без
записи либо исключительное создание нового файла в остановленной копии. В профиле,
где квота обязательна, требуется `ftb.territories`. Ошибка конфигурации/пина отклоняет
старт; runtime-fault запрещает проверяемые изменения, сохраняет приваты и даёт один
лог. После restart адаптер снова включается.

Linux Docker: **156 условий / два старта** территорий и **54** прежних security/claim
регрессии с обязательной политикой, итого **210 DJ2**. Минимальный Forge — три рабочих
режима и шесть ожидаемых отказов, 32 условия с preflight. Независимое чтение
остановленных TAR/NBT новой пары — **63 проверки**. Отдельно **305 JVM-случаев / 627
условий** против Python-эталона; это не gameplay. Контроль старого Core: 8 native / 9
independent, шесть несвязных территорий. Семь ранних кандидатов/фикстур исключены.
Все **19 собственных scopes** очищены и сверены, здоровые старты stop 0/no OOM.
24 проверки состава/повторной сборки; общий API и прежние guard-классы byte-identical.
Windows unit/UI **1084 passed / 12 skipped**, Ruff/Black.

[Правила, env и папки](CLAIM_TERRITORIES.md),
[обезличенный протокол](validation/dj2-territories-2026-11-07.json).
Закрывается только #31; графическая карта FTB/клиент и spawn/RTP не повторялись.
Следующий этап — ресурсный мир #32, далее lifecycle/backup/storage #33/#38,
откат базы #34, предгенерация #37. #29/#49/#102/#105 остаются открытыми.
VPS пока не нужен; рабочие миры/профили, client adapter, player releases и расписания
бэкапов не переключались.

## Прямые операции плоскостей AE2 и актуальные FTB-права — 7 ноября 2026

Core **0.3.2** не изменён; DJ2Fix **0.1.2** добавляет pre-write адаптер пяти
плоскостей AE2 через существующий `ClaimAccess`. Незанятое назначение и собственная
команда работают, чужие/server назначения защищаются до прямого изменения блока
или жидкости. Входной ресурс возвращается штатному механизму AE2. PlaneFix и его
native silk-touch сохранены; новых команд, запретов предметов и своей БД claims нет.

Основная приёмка AE2: **46 сценариев / три старта / 721 нативное условие**,
**338 независимых проверок** stopped TAR/Anvil/NBT. Покрыты пять типов, свои/чужие/
server claims, живая смена прав на одной сети, команда, контейнер с точными вещами,
silk-touch, жидкости, отрицательные координаты/обе оси, измерение, fault и restart.
Отдельно security/claims **54 / 8** и рост растений **96 / 40**.
Итого **871 нативное / 386 независимых**; здоровые старты stop 0/no fatal/no OOM.
Первый неполный guard отклонён; два неполных fixture-прогона не считаются приёмкой.
Независимые сохранения объяснили ошибку NBT-типа и гонку повторной подачи блока.

Изменённая копия AE2 получила ожидаемый startup refusal; исходный JAR цел.
25 composition checks, прежние реализации byte-identical, повторные SHA совпали.
Все **10 собственных scopes** очищены и сверены. Windows unit/UI **1059 / 11 skipped**,
Ruff/Black. [Правило и папки](DJ2_AE2_BOUNDARIES.md),
[протокол и SHA](validation/dj2-ae2-planes-2026-11-07.json).

Закрывается только #108. Другие машины/AE2-шины/подбор сущностей/произвольные
многоблочные эффекты и quest-acquisition остаются #29/#49; #105/#102 открыты.
Spawn/RTP и графический клиент в этой итерации не повторялись. Далее также квота
территорий #31, ресурсный мир #32, lifecycle/единый backup writer/storage/off-host
#33/#38, региональное восстановление #34 и финальная предгенерация #37. VPS пока
не нужен; живые миры, client adapter, player releases и backup-расписания не переключались.

## Записи роста перед изменением привата — 6 ноября 2026

Кандидат Core **0.3.2** / DJ2Fix **0.1.1** закрывает узкую #106: общий API прав FTB
в Core и pre-write адаптер одной подтверждённой механики в Fix. Чужие/server назначения
не заменяются, разрешённая часть растёт штатно. Рецепты, предметы и квестовые данные
не запрещаются. Поздняя отмена MultiPlaceEvent отклонена: отдельный native-контроль
восстановил TileEntity, но оставил предметные побочные эффекты; остановленный NBT
подтвердил дюп. Экспериментальный Core 0.3.1 не принят; общая модель остаётся #105.

**435 нативных условий**, включая 14 обычных survival-сценариев роста (136),
10 детерминированных TileEntity/rights/dimension/restart/fault сценариев (89),
минимальный Forge без DJ2/MixinBooter (32), security/claims (54), spawn/могилы
с restart (74) и RTP (50). **124 независимые проверки** stopped TAR/Anvil/NBT.
Учтены точные контрольные предметы в контейнерах, выпавших сущностях и инвентарях.
Два ранних неполных fixture-опыта и отклонённый rollback не считаются приёмкой защиты.
Обвязка после здорового claims-опыта возобновлена из-за различия названия поля отчёта;
сам пройденный игровой suite не повторялся и не подменялся.

Повторная сборка дала те же SHA; 19 проверок состава/старых артефактов. Core без
pack patches/Mixin/probe, существующие реализации патчей и connection adapter
byte-identical прежнему контролю. Свои **14 scopes** очищены и сверены по Docker
containers/volumes/networks. Windows unit/UI **1059 passed / 11 skipped**, Ruff/Black.

[Правило, папки и ограничения](DJ2_PLANT_PLACEMENT.md),
[обезличенные результаты и входные хеши](validation/dj2-plant-placement-2026-11-06.json).
Графический клиент и полное quest-acquisition не повторены. #29/#49 остаются для
других деревьев/модовых механизмов/AE2; #102 по-прежнему открыта. Далее также
ресурсный мир #32, lifecycle/единый backup writer/storage/off-host #33/#38,
региональное восстановление #34 и финальная предгенерация #37. VPS пока не нужен;
живые миры, client adapter, player releases и backup-расписания не переключались.

## Спавн/RTP на разделённых компонентах и диагностика входа — 6 ноября 2026

На прежних SHA Core 0.3.0/DJ2Fix 0.1.0 допроверены **74 условия спавна/могил
с restart**, **50 условий RTP**, **47 входов полной DJ2** (15 конкретных отказов
неверному mod list, 32 корректных входа). Строгий community profile включил spawn
и RTP одновременно на обоих стартах; NBT подтвердил точные 1444 серверных claim-чанка,
личные приваты и прежние UUID. Независимое чтение принятых DJ2-опытов — **27 проверок**.
Здоровые старты stop 0/no fatal/no OOM; шесть собственных game/auth scopes очищены.
Unit Windows **1015 passed / 11 skipped**, Ruff/Black прошли.

#102 локализована, но не исправлена. Минимальные Forge-контроли получили 2 обрыва
из 35 попыток с Core, 7 из 62 без Core, 9 из 68 без Core с encoder trace.
В последнем случае каждый обрыв соответствует записи LoginSuccess при состоянии PLAY.
Отсутствие Core и четыре разных UUID подтверждены сохранениями, ещё **27 независимых
проверок диагностики**. Все неверные mod lists явно отклонены, обхода авторизации нет;
неуспешные корректные входы не записаны как pass. Пауза не является исправлением.
На полной DJ2 этого симптома в текущих 47 попытках не было; графический клиент
и узкий fix остаются отдельной приёмкой в #102. Бинарники Core/Fix не менялись.

[Проверки, выводы и папки](SERVER_LOGIN_DIAGNOSTICS.md),
[обезличенный протокол](validation/split-policy-reconnect-2026-11-06.json).
#29/#32/#33/#34/#37/#38/#49 остаются открытыми в своём объёме. VPS пока не нужен,
player releases/live data не менялись, второго backup-планировщика нет.

## Общий Forge Core и отдельный DJ2Fix — 6 ноября 2026

По решению владельца приватная серверная интеграция разделена: **OmkalityCore 0.3.0**
содержит общие подключения, mod policy, диагностику, API 1 и необязательную интеграцию
FTB; **OmkalityDJ2Fix 0.1.0** — композицию проверенных vanilla/TF/WR-патчей.
Core не содержит mixin bootstrap или классов исправлений сборки. Версии, требования
профиля и фактически включённые возможности проверяются при старте. FTB остаётся
источником прав; повторно используемые алгоритмы патчей отделены от композиции DJ2.

Минимальный Linux Forge: **44 условия**, включая четыре намеренных отказа старта
(8 условий), без FTB/TF/WR/MixinBooter, с FTB без Iron Chest, с отключёнными claims
и с независимым тестовым расширением. Полная DJ2 2.23.4: **881 условие** для claims,
ванильных границ, эффектов мира, сортировки и восстановления аккаунта; **195 независимых
проверок** сохранённых данных. Отдельный переход мира Core 0.2.11 → новая пара:
**13 условий / два старта / 10 независимых проверок**, те же Drasl/UUID, вещи, опыт,
дом и приват, реальные действия владельца/постороннего; старый снимок неизменен.
Здоровые опыты stop 0/no fatal/no OOM; отдельный pin-negative ожидаемо отказал.
14 проверок состава/повторяемости сборки; 29 собственных scopes очищены и сверены.
Windows unit **1015 passed / 11 skipped**, Ruff/Black прошли.

[Архитектура, сборка, профили и отчёты](SERVER_MOD_COMPONENTS.md),
[обезличенный протокол](validation/core-pack-split-2026-11-06.json).
Полные spawn/RTP suites на новой паре пока не повторены; соответствующие реализации
byte-identical старому контролю. Клиентский адаптер, player releases и живые данные
не менялись. Новый случай повторного протокольного входа на минимальном Forge — #102;
источник ещё не установлен. #29/#33/#34/#38/#49 остаются открытыми, GTNH не принят.
Это проверка замены Core, не полной смены версии сборки. VPS для следующего локального
этапа пока не нужен. Нового backup-планировщика нет.

## Ванильные записи через FTB-границы — 6 ноября 2026

В кандидате DJ2 2.23.4/Core 0.2.11 закрыта узкая часть #29/#99: нативные поршни,
вода/лава и их смешивание больше не пишут через чужую/server FTB-границу.
FTB остаётся источником live ownership; незанятая земля и общая команда работают,
новых команд, запретов предметов или изменений квестов нет. Служебный startup-каталог
берёт версию из фактически загруженного Forge mod container и показывает guard state.

Native Linux Docker: **229 условий / 111 сценариев / два старта**, включая non-OP
survival-ввод, отрицательные координаты, live claim change, restart и правило 12/13.
**161 независимая проверка** двух остановленных TAR/Anvil/NBT (150 состояний блоков).
Отдельно существующие security regressions: **54 условия / 8 независимых проверок**.
Здоровые запуски stop 0/no fatal/no OOM, свои scopes очищены. Изменённая копия JAR
в отдельном негативном опыте получила ожидаемый fatal startup refusal; исходник цел.
Это не случайный краш gameplay и не графический клиент.

[Правило, отчёты и ограничения](DJ2_VANILLA_BOUNDARIES.md),
[обезличенный протокол](validation/dj2-vanilla-boundaries-2026-11-06.json).
Публичные профили/live runtime не переключены. Все виды огня, модовые жидкости,
деревья, трубы/машины, AE2/PlaneFix и quest-acquisition не объявляются проверенными;
#29/#49 остаются открытыми. #33/#38 сохраняют single backup writer/storage/off-host,
#34 — безопасный откат базы. VPS для следующих локальных тестов пока не нужен.

## Закрытый owner restore staging — 6 ноября 2026

`omk admin restores plan/apply/verify/status` работает с явным новым Linux volume,
текущим чисто остановленным источником и опубликованными snapshots. Требует свежую
проверенную копию фактического текущего мира; связывает lifecycle/volume/settings/
runtime/архив/FTB, держит общий lock с cold backups. Входные тома readonly;
target writable только при apply. Устаревший/использованный план не повторяется.
Verify подтверждает завершённую запись после потери host acknowledgement; частичный
target не принимается. Пароли/Drasl не переносятся из истории. Это staging, не cutover.

Linux DJ2 2.23.4/Core 0.2.10/CON: **24 native условий / 3 старта**,
**30 независимых проверок**. Исторические вещи/home/claims вернулись,
текущие ban/whitelist/deop/home quota/отзыв ally сохранились; реальное ломание блоков
проверено. Исходник byte-identical; stop 0/OOM=false, свои game/auth/backup тома очищены.
LabPlayer — протокол, не GUI. Два ранних preflight отказали до записи: свежий runtime
не содержал шести извлечённых Forge core JAR. Lab теперь явно готовит их из source,
все SHA сверены с embedded bytes существующих модов; guard не ослаблен, загрузок нет.
Пять оставшихся томов этих опытов очищены после сверки экспортов.

Отдельно **14 real Docker/CLI fault checks + 4 tmpfs ENOSPC checks**, synthetic
runtime/FTB fixtures, не падение Minecraft. Windows unit **1010/11 skipped**,
focused Linux **318**. [Команды, папки, ограничения](OWNER_RESTORES.md),
[протокол](validation/dj2-owner-restore-2026-11-06.json).

В production будет **один** периодический backup writer/планировщик и общий бюджет;
не запускаем FTB и managed расписания параллельно. Этот этап расписания не добавляет.
Lifecycle/promotion, повреждённый current source, изменившиеся identity, единое
backup-window/storage/off-host и VPS acceptance остаются #33/#38. VPS пока не нужен.

## Исторический Linux-мир с текущими правами — 6 ноября 2026

`dj2-linux-policy` связывает Linux stage с актуальными bans/OP/whitelist/ranks
и известными FTB-полномочиями. Свежая копия текущего мира создаётся перед возвратом;
источник/store readonly. План/receipt и весь inventory перепроверяются перед Forge.
Raw verify не разрешает обойти частичное применение policy. Пароли/Drasl не копируются;
прочие target properties сохранены. Это lab, не production restore/cutover.

Linux DJ2 2.23.4/Core 0.2.10: **19 native условий / три старта**,
**25 независимых проверок / 273 исторических файлов**.
CON вернул 7 вещей и старый home, сохранив текущий бан другого аккаунта, whitelist,
снятую OP, quota homes и отзыв ally. Союзник раньше действительно ломал приват;
после возврата не может, владелец может, вне привата guest может. Исходник неизменен,
stop 0/OOM=false, свои game/auth/backup тома очищены. LabPlayer — протокол, не GUI.

Отдельно **10 Linux FS/process проверок**: SIGKILL после первой замены,
два процесса/один writer, настоящий ENOSPC tmpfs. Это synthetic fixture с pinned FTB
JAR, не краш Minecraft. Windows unit **977 passed / 11 skipped**, focused Linux **285**.
[Порядок/папки/ограничения](LINUX_CURRENT_POLICY.md),
[обезличенный протокол](validation/dj2-linux-current-policy-2026-11-06.json).
Production owner workflow, изменившиеся identity, backup-window, общий budget/off-host
и VPS acceptance остаются в #33/#38. VPS для следующей локальной работы пока не нужен.

## Linux-имена FTB в бэкапах — 6 ноября 2026

Исправлена #95: Linux cold worker использует явную `linux-server` path policy,
которая разрешает Windows-reserved basename, сохраняя остальные проверки путей,
ссылок, дубликатов, размеров/хешей/CRC. Generic default остаётся portable.
Новый store сохраняет policy в owner schema 2; старые store не мигрируются автоматически.
Новый data worker извлекает только в свежий инициализированный Linux target, пишет
план/подтверждение, проверяет reserve и весь inventory. На Windows extraction запрещён;
snapshot/manifest читаются без извлечения имён. Это staging, не production cutover.

`dj2-linux-paths`: настоящий Drasl зарегистрировал CON; Linux DJ2/Core 0.2.10 создал
`con.dat`, owner plan/run сохранил его, новый Linux volume загрузился и игрок вошёл
с семью предметами и работающим home. **9 native условий / два старта**,
**13 независимых проверок / 265 файлов**. Исходный мир неизменен, свои
game/auth/backup тома очищены; stop 0/OOM=false. Последний worker дополнительно
повторил stage/verify того же снимка в Linux. Это сервер/протокол, не GUI.

Windows unit **967 passed / 10 skipped**, focused Linux Docker **274 passed**;
13 real Docker cold CLI регрессий прошли. [Процедура/папки](LINUX_SERVER_PATHS.md),
[протокол](validation/dj2-linux-server-paths-2026-11-06.json).
Согласование текущих полномочий, production owner restore, backup-window,
storage/off-host и VPS acceptance остаются в #33/#38. VPS пока не нужен.

## Текущие права FTB в историческом мире — 6 ноября 2026

Явный `--reconcile-ftb-authority` перед строгой сверкой переносит известные текущие
членства/владельцев/статусы/приглашения и правила FTBUtilities в новую копию.
Homes/claims/инвентарь/мир остаются историческими. Нужны одинаковый набор записей,
стабильные Name/UUID и ID/UID/Type; неизвестные различия требуют владельца.
Exclusive fsynced plan, проверенные отдельные NBT, замена, подтверждение; перед
стартом результат заново строится из архивов. Частичное применение не повторяется
и не разрешает запуск; многофайловая замена не является атомарной транзакцией.

Linux DJ2 2.23.4/Core 0.2.10/persistent Drasl: **130 условий / пять стартов**.
Раньше союзник реально ломал блок в привате; после отзыва и полного возврата
не может, владелец может. Вещи/home/claim/машины/сущности и текущие ranks/access
проверены. **18 независимых проверок** сохранённых NBT/хешей/экспортов;
исходник неизменен, stop 0/OOM=false, свои game/auth тома очищены.
Прочие переходы полномочий имеют unit-покрытие, не отдельную игровую приёмку.

Отдельный Linux FS probe: **6 проверок**, два реальных процесса/один writer,
SIGKILL после первой замены, настоящий ENOSPC tmpfs. Это не краш Minecraft.
Windows unit **935 passed / 9 skipped**, Linux Docker focused **214 passed**.
[Процедура/папки/ограничения](FTB_AUTHORITY_TRANSFER.md),
[обезличенный протокол](validation/dj2-ftb-authority-transfer-2026-11-06.json).
Production restore, изменившиеся identity, scheduler/backup-window, общий бюджет
и off-host copy остаются в #33/#38. Лаунчер/Core/рабочие миры не менялись; VPS пока не нужен.

## Сверка полномочий FTB перед полным возвратом — 6 ноября 2026

`dj2-recovery --ftb-authority-policy` сравнивает текущие и исторические данные
FTBLib/FTBUtilities перед стартом новой копии. Возврат homes/claims допускается,
изменившиеся владельцы/членства/ally/mod/invites/fake-player правила блокируют старт.
Неизвестные FTB-данные сравниваются консервативно, версии JAR закреплены по SHA-256.
Перед подготовкой replacement volume фактические данные читаются повторно;
положительного marker недостаточно. Адаптер ничего не переписывает и не объединяет.

Linux DJ2 2.23.4/Core 0.2.10/persistent Drasl: **126 условий / пять стартов**
для положительного полного возврата и **108 условий / четыре старта**
для отказа при реально отозванном историческом союзнике. Во втором опыте замена
не запускалась. **25 независимых проверок** NBT/экспортов/рангов/допусков;
исходные миры неизменны, свои game/auth volumes очищены, stop 0/OOM=false.
Windows unit **910 passed / 9 skipped**, Linux Docker focused **189 passed**.
LabPlayer — протокольный клиент, не графический Minecraft; launcher UI не менялся.

[Покрытие/папки/ограничения](FTB_RESTORE_AUTHORITY.md),
[обезличенный протокол](validation/dj2-ftb-restore-authority-2026-11-06.json).
Сверка требует нового флага; это не production restore/cutover и не решение
автоматического переноса изменившихся членств. #33 остаётся открытой вместе с
scheduler/backup-window, off-host copy и общим бюджетом VPS. VPS пока не нужен.

## Закрытая cold-backup утилита владельца — 6 ноября 2026

`omk admin backups plan/run/status/list/finish/cancel` создаёт копию остановленного
Linux Docker мира по приватному allowlist. План связывает container/image/volumes,
inventory мира, fingerprint runtime и env-политику; prepare отделён от publication.
Повторный lifecycle-check перед публикацией отвергает старт источника во время чтения.
Неоднозначный run не повторяется. `finish` подтверждает committed sequence/хеш без
новой ротации; `cancel` удаляет только доказанно неопубликованный staging при
неизменной истории. Источник readonly, helper без сети/Docker socket, ресурсы ограничены.

Настоящий DJ2 2.23.4/Core 0.2.10/persistent Drasl прошёл **137 игровых условий**,
четыре owner plan/run и пять стартов; **30 независимых проверок** файлов/journals.
Восстановление inventory/home/claim/сущностей/плавки, текущих допусков и рангов
сохранено. Source unchanged, stop 0/fatal/OOM=false; свои data/auth scopes очищены.
Отдельные 13 real Docker/CLI условий используют synthetic runtime: гонка двух
процессов, os._exit(73), finish без перепубликации, source restart/change, безопасный
cancel и sparse 600 MiB при helper memory 512 MiB. Не называть это Minecraft crash.

Введён явный expanded-byte limit owner store вместо прежнего общего lab cap 512 MiB;
старые defaults сохранены. Worker budgets/TTL/CPU/RAM/journal cap задаются env,
ошибочные значения не отражаются в сообщениях. Windows unit **887 passed / 8 skipped**,
focused Linux Docker **192 passed**; filesystem ENOSPC/4 SIGKILL пройдены отдельно.
[Команды, конфиг, лимиты и папки](COLD_BACKUPS.md),
[обезличенный протокол](validation/dj2-owner-cold-backups-2026-11-06.json).

Это рабочая ручная cold-copy операция, не scheduler, не автоматический stop/start
и не production restore/cutover. Off-host storage, общий бюджет VPS и сверка старых
FTB memberships остаются в #33/#38; частичный откат #34 отдельно. Исторический
world zip не содержит runtime/config/Drasl: они требуют собственных сохраняемых
артефактов/политики. VPS для локальной приёмки по-прежнему не нужен.

## Управляемые копии настоящего Forge-мира — 6 ноября 2026

`dj2-recovery --managed-backups` связал независимый inventory остановленного Linux
volume с `BackupStore`, выбором опубликованного снимка и полным возвратом в новый
игровой volume. Вся запись/ротация происходит на Linux FS; source readonly, helper
без сети, 1 CPU/512 MiB. Чистый остановленный снимок проверяется до публикации,
новая проверенная копия — до удаления старой. Не принимает рабочие миры/FTB-папки.

DJ2 2.23.4 / Core 0.2.10 / persistent Drasl: **133 игровых условия, пять стартов и
25 независимых проверок сохранённых данных**. Четыре снимка, выбранная управляемая
копия с 267 файлами, восстановление инвентаря/home/claim/сущностей/плавки, сохранение
текущих bans/OP/whitelist/определений рангов. Byte-quota отказала без изменения
истории; пятая копия оставила sequences 2/3/4/5. Исходник неизменен; все stop 0,
fatal/OOM=false; два игровых volume, backup volume и свой auth scope очищены
после экспорта. [Протокол](validation/dj2-managed-backups-2026-11-06.json).

Отдельный синтетический Linux filesystem lab повторно прошёл реальный ENOSPC и
четыре SIGKILL-фазы транзакции. Это не падение настоящего Minecraft. Windows unit
860 passed / 8 skipped, focused Linux Docker 165 passed; Ruff/Black.
[Процедура/папки](LINUX_WORLD_RETURN.md#управляемые-копии-остановленного-мира).
Серверные прогоны продолжаем в Linux Docker с ограниченными ресурсами.

#33 остаётся открытой: эксплуатационный scheduler/закрытый owner plan/apply,
реалистичные бюджеты/внешняя копия и пересогласование исторических FTB memberships
ещё не реализованы. Это полный возврат всего мира/игроков, не безопасный частичный
откат #34; неполный WorldEdit restore по-прежнему не атомарен. Публичный профиль,
реальные аккаунты/миры и launcher UI не менялись. VPS для этого этапа не нужен.

## Постоянный Drasl проверен локально — 6 ноября 2026

`deploy/auth` и `deploy/auth-lab` теперь расширяют общий Linux runtime с именованным
state volume, read-only root, ограничениями CPU/RAM/tmp/logs и выключенным debug.
`omk auth configure` создаёт конфиг из валидированных переменных, без credentials
и перезаписи существующего файла. Скины/БД/ключи пережили recreate и инъекцию SIGKILL.
`omk lab auth-storage` использовал deployment entrypoint: полный offline snapshot,
SQLite integrity, восстановление в новый том, staging без host ports и отзыв старых
API/game/refresh/join/password/browser/invite доступов перед открытием копии.
UUID/скин/подпись сохранены; восстановленные игроки закрыты до owner recovery.
Приватный backup/report остаётся в `.local/auth-storage-<run>/`; свои тома очищены.
Это локальная HTTP/storage-проверка, не миграция живых аккаунтов. [Процедура](AUTH_STORAGE.md).

Drasl `4.0.0-omk.2` дополнительно исправляет отзыв старых join approvals и гонки
stateful HTTP-запросов одного процесса; четыре Go-проверки встроены в сборку.
Повторный Linux DJ2/Core 0.2.10 на постоянном auth volume: **78 native условий и
8 независимых проверок**; stop 0/OOM=false, UUID/вещи/XP/home/claim сохранены.
Исторические результаты tmpfs/.1 ниже относятся к прежнему этапу, а не текущему
контейнерному профилю. #38 сохраняет HTTPS, внешний backup/retention/диск и проверку
конкретного VPS; арендовать VPS ради этих локальных тестов пока не требуется.

## Native MCMCP после перезагрузки — 6 ноября 2026

Принят native namespace #84: настоящий Windows DJ2 вошёл на Linux Core 0.2.10;
roster/endpoint/PID/connection/player/gui прочитаны инструментами чата, штатный
native quit дал exit 0 и чистые 55 секунд. Собственный стенд очищен.
[Протокол](validation/dj2-native-codex-mcp-2026-11-06.json). Это не прохождение #85.
Ускорение загрузки — необязательная #89 после P0: сначала замеры обычного
клиента/кешей, без обещаний ускорения и смены авторского Forge. VPS пока не нужен.

## Утилита восстановления аккаунта и незавершённый вход — 6 ноября 2026

`omk admin recover-account plan/run/status/resume` работает с существующим Drasl
аккаунтом: проверяемый план всех игровых UUID/настроенных серверов, lock, смена
пароля и отзыв секретов, подтверждённый drain подключений, unlock и однократная
выдача нового пароля в приватном терминале. Journal без секретов атомарный,
ограниченный; есть межпроцессная блокировка. Повтор после сбоя требует явного resume
и новой смены секрета. Пароль не входит в JSON/audit/launcher/process arguments.

Реальный сценарий на Core 0.2.9 показал недостаточность `list uuids`/`kick`: вход,
прошедший auth, но задержавшийся до Forge handshake, отсутствовал в онлайн-списке
и пережил reset. Приватный Core 0.2.10 даёт узкий RCON-only адаптер просмотра/drain
самих сетевых подключений; старый сервер отвергается до изменений аккаунта.

Финальный Linux DJ2 2.23.4/Drasl/Core 0.2.10: **73 условия и 8 независимых
проверок**. Закрыты активный и незавершённый входы; посторонний остаётся онлайн;
даже OP-игрок не может вызвать служебную операцию. После os._exit(73) до выдачи
пароля остался незавершённый journal, обычный run отказал, resume отозвал секреты
повторно и сохранил UUID/7 изумрудов/12 уровней/home/claim. Stop 0, fatal/OOM=false,
свои volume/auth удалены после экспорта. GUI не использовался: LabPlayer —
протокольный клиент, а не отрисованный Minecraft. Windows unit 829 passed / 6 skipped,
Linux Docker 119 passed, Ruff/Black. Подробности и ранние непринятые попытки:
[операция](ACCOUNT_RECOVERY.md), [обезличенный протокол](validation/dj2-owner-recovery-2026-11-06.json).

Данные аккаунтов/скинов/ключей описаны в [ADMIN](ADMIN.md#где-лежат-аккаунты).
Постоянный runtime/restore уже проверен локально, см. обновление выше; в #38 остаются
задачи рабочего размещения. Рабочие аккаунты/миры не менялись, публичного деплоя нет.
GTNH-адаптер не принят; расширение на него относится к #40. Смерть процесса после
unlock не гарантирует закрытый аккаунт: честный незавершённый этап и явный resume,
не общая транзакция Drasl/файлов. Далее оставшиеся P0 #29/#33/#34/#49; VPS пока не нужен.

## Постоянный Orchestrator и defaults dev12 — 6 ноября 2026

Desktop MCMCP установлен в `.local/tooling/mcmcp-desktop/`, global/project Codex
config использует официальный shim. Два одновременных подключения видят 70 tools;
проверены перезапуск idle app и новый stdio session. Public `omk lab dj2-mcp`
воспроизводит fresh Windows client + Linux server/auth и client restart без живых
данных; GUI-политика этого upstream требует idle refresh после CLI changes.
Каждый refresh проверяет точные EXE hashes, оба listener PID, state/port environment
и дважды отсутствие активных игр. Это не атомарный lock от нового соединения.

Финальный lab: один Linux Core 0.2.9 server, два Windows client starts. Начальная
K открывает квесты, после остановки/редактирования личных lab-файлов сохранились
F10/F8 и Circle/grid; настоящая F10 тоже открыла GUI. Independent saved NBT:
тот же UUID-файл, 7 изумрудов, 12 уровней. Оба exit 0 до cleanup, по 55 секунд
без новых reports/task fatal; Linux stop 0/OOM=false, свои volume/auth/MCP grants
очищены. Default K/F12 и Square/no-grid восстановлены только в остановленном lab.

Начальные keys — подписанные данные профиля, GUI не содержит DJ2-веток. Marker
не даёт повторно добавлять отброшенный Minecraft языковой alias и не сбрасывает
личный выбор. Полная потеря options.txt возвращает начальные настройки.
Минимальная версия для новых метаданных — dev12, проверяется и при подписи.
Windows full unit 786 passed / 6 skipped, Linux Docker 138 passed, Ruff/Black;
ярлыки desktop app сохраняют профиль Codex через проверяемый bootstrap.
Собран loopback EXE dev12,
packaged Qt startup прошёл. Ошибки ранних fixture и различия с native game сохранены
в [протоколе](MINECRAFT_MCP.md). Полная смена языка Galacticraft не принята.

Native namespace чата всё ещё не загружен, #84 открыта; это не мешает проверенным
MCP JSON-RPC вызовам через Python. После переподключения проверить native roster.
Следующий блок основного плана — production owner recovery #35 и оставшиеся P0
#29/#33/#34/#49. Сценарное прохождение #85 и массовая предгенерация #37 остаются
позже; GTNH ещё не готов. Рабочий профиль/миры и публичные релизы не менялись,
VPS пока не требуется.

## MCMCP и первые сценарии настоящего клиента — 6 ноября 2026

Официальный MCMCP 2026.11.02 установлен только в отдельные test-only overlay
клиенты DJ2 2.23.4. HTTP дал 64 инструмента; official stdio Orchestrator — 70,
с сохранением каталога при закрытой игре и следующем старте. Local Codex config
обнаружен CLI, но текущий native namespace чата не обновился; эта часть #84 открыта.

Два Windows-клиента и два свежих Linux/Core 0.2.9/auth scope: GUI, chest,
команды/полёт, русский список квестов, переход в Эдем/обратно, disconnect/rejoin,
штатный quit. Java exit 0 до cleanup, 55 секунд без новых reports/fatal; Linux
exit 0 / OOM=false, свои volumes/auth очищены. Во втором fixture структуры true,
острова Эдема видимы; saved NBT подтвердил UUID-файл, 7 изумрудов и 12 уровней.

[Версии, схема подключения, ограничения и evidence](MINECRAFT_MCP.md).
Найдены конфликт K (#86), отличие synthetic key и широкий readiness timeout;
RC population compatibility warning требует проверки структур в #37. Не закрываем
#49/#36 и не считаем это проверкой всех машин/сюжета. Новый #85 — конечная матрица
прогрессии и база собственных заметок после обязательных P0, с оценкой цены малого
пилота. Ресурсный TP с КД/warmup `/spawn` добавлен в #32, ресурсный мир включён
в финальный pregeneration #37. Сейчас массовой прогрузки нет, VPS пока не нужен.
Следующий практический шаг: native MCP discovery после обновления чата и точное
исправление начальных K-привязок с сохранением пользовательских настроек.

## Drasl reset/lock и действующий Forge-клиент — 6 ноября 2026

Новый `omk lab dj2-account-recovery` проверяет существующий аккаунт в свежих Drasl
и Linux DJ2 2.23.4 / Core 0.2.9. **44 native условия / один старт и 8 независимых
проверок** прошли: два отозванных game tokens, API credential, старый/новый пароль,
настоящий отказ/успех Forge-входа, lock/unlock без оживления старого токена, повторный
сброс, сохранность UUID/вещей/уровней/FTB/home. Stop чистый, fatal=false / OOM=false;
свои auth/volume удалены. Ранние ошибки самого теста сохранены в протоколе.

Важная граница: Drasl reset/lock не отключает уже действующего игрока; явный
console kick проверен отдельно. [Порядок будущей операции](ACCOUNT_RECOVERY.md):
заблокировать → сменить секреты/отозвать токены → подтвердить отключение на всех
серверах → разблокировать. Production CLI, журнал стадий и обработка сбоев ещё
не реализованы, #35 открыта. GUI/MCP не использовались; рабочие данные не менялись.
Focused Windows/Linux Docker: 76 passed, Ruff/Black. VPS пока не нужен.

## Автономные тики/биомы по границам FTB — 6 ноября 2026

Core 0.2.9 использует общий адаптер актуального владения FTB для проверенных
автономных эффектов и прежней сортировки. 300 целевых + 394 регрессионных серверных
условия прошли на новом Linux DJ2 2.23.4; baseline 37 и reader 8 посчитаны отдельно.
Все свои области остановлены чисто / OOM=false и очищены после экспорта.
Обычный Windows-клиент без probe отрисовал мир и штатно закрылся с exit 0 до
cleanup; ещё 55 секунд без reports/fatal. Графическая активация блока не проверена
из-за отказа инструмента ввода. Скрипты/квесты не менялись; новые команды не нужны.

[Метод и точные границы](DJ2_WORLD_EFFECTS.md). Это узкая задача #81 внутри #29;
#29/#49 и общий выпуск не закрываются этим прогоном. Рабочий профиль не менялся.
Следующий независимый блок: административное восстановление аккаунта и отзыв
сессий (#35), без GUI/MCP. VPS пока не нужен.

## Повторение claim/container/TNT регрессий на 2.23.4 — 5 ноября 2026

`omk lab dj2-claims` повторяет существующие сценарии в новом Linux volume:
claim-edges, обычные vanilla/Iron Chest, модерация/мут и TNT. Проверяет guard
metadata из bounded startup-каталога и отсутствие OP у двух игровых UUID;
служебный OP PlaneFix сохраняется. Никаких новых модов/запретов предметов нет.

DJ2 2.23.4 / Core 0.2.8 прошёл **54 серверных условия / один старт** и
**8 независимых проверок** остановленных файлов. Посторонний не забирает предметы
через составной сундук; исключённый участник теряет открытое vanilla/Iron Chest.
Владелец/действующий участник и обычные операции работают. TNT сохраняет внутренний
блок и разрушает наружный контроль. Final stop чистый / OOM=false, свои volume/auth
удалены. Unit/lifecycle: Windows/Linux по 26 passed, Ruff/Black.

[Метод, версии и ограничения](DJ2_CLAIM_REGRESSIONS.md) сохраняют непринятую первую
попытку (слишком малый лимит каталога, без краша игры) и исправления независимого
reader. Не проверены графический GUI, все модовые эффекты, деревья/жидкости/поршни,
AE2 planes/служебный OP, полный restart или длительный survival. #29/#49 остаются
открытыми, рабочий профиль/миры не менялись. VPS пока не требуется.

## Текущие определения FTB-рангов при world-return — 5 ноября 2026

Дополнительный `--rank-policy` поверх `--access-policy` переносит точный текущий
`local/ftbutilities/ranks.txt` отдельно от исторического мира, до первого старта
новой копии. План, bounded TAR/readback и отдельный маркер не допускают старт после
частичной записи; незавершённая проверка сохраняет исходный volume.

Linux DJ2 2.23.4 / Core 0.2.8 прошёл **125 серверных условий / пять стартов** и
**16 независимых проверок файлов**. После deop текущий лимит одного home запрещает
второй; явное увеличение до двух разрешает его, уменьшение снова запрещает.
Сохранённый home реально телепортирует, инвентарь/claim и vanilla-допуски проверены.
Исходные world/access/ranks не изменились, оба stop чистые / OOM=false; свои volumes
и временный Drasl удалены. FTB JAR сверены с закреплённым официальным BOM.

Unit/lifecycle: Windows 177 passed / 2 link skips, Linux Docker 179 passed.
[Порядок и границы](LINUX_WORLD_RETURN.md). Это определения рангов, не сверка старых
назначений ролей и членств команд: #33 остаётся открытым вместе с эксплуатационной
процедурой/retention/внешней копией. #34/#49 тоже не закрыты этим опытом. Графический
клиент, рабочий профиль и существующие данные не менялись; VPS пока не нужен.

## Текущие vanilla-допуски при world-return — 5 ноября 2026

Linux full-return с `--access-policy` отдельно переносит текущие ops/bans/whitelist
и whitelist-флаг после staging исторического мира. Целиком server.properties не
копируется; сеть/RCON не подменяются историческими настройками. Списки копируются
побайтно, источник читается readonly. Отсутствие готового access-маркера запрещает
старт; незавершённая проверка сохраняет оригинальный volume даже с world-экспортом.

Настоящий Linux DJ2 2.23.4 / Core 0.2.8 прошёл 120 серверных условий / пять стартов,
12 независимых проверок файлов. Действующая сессия забаненного аккаунта отвергнута;
OP-команда разрешена до deop и запрещена после, pardon разрешает вход, whitelist
отвергает удалённого участника и допускает добавленного. Это управляемые изменения
в новой копии; источник world/access не изменился. Оба stop чистые / OOM=false,
свои volumes удалены после проверки экспортов, временный Drasl удалён.

Unit/lifecycle: Windows 158 passed / 1 skip, Linux Docker 159 passed. Эти отказы
mocked, не crash/power-loss проверка. [Порядок и границы](LINUX_WORLD_RETURN.md).
Текущие FTB-ранги/исторические членства, Drasl reset/revocation, scheduler/retention
и production-cutover остаются отдельными задачами #33/#35. Графический клиент не
запускался, рабочий профиль и существующие данные не менялись. VPS пока не нужен.

## Полный Linux world-return — 5 ноября 2026

`dj2-recovery --runtime linux-docker --edge-cases --full-backup-return` теперь
проверяет исторический полный мир в новом volume, отдельно от остановленного
исходника. DJ2 2.23.4 / Core 0.2.8 прошёл 112 серверных условий / пять стартов и
6 независимых проверок сохранённых файлов: 267 файлов staging, сущности, NBT,
инвентарь, тот же UUID, FTB claim/home/команда, права постороннего и работа печи.
Digest исходного volume до/после совпал; stop обеих областей 0 / fatal=false /
OOM=false, собственные volumes удалены после проверенного экспорта, Drasl удалён.

Профильные unit: Windows 139 passed / 1 skip, Linux Docker 140 passed.
[Порядок, доказательства и границы](LINUX_WORLD_RETURN.md) сохраняют отменённый
первый запуск и исправление ожидания reader. Это полный откат всей истории мира,
не выборочное возвращение базы; новый графический клиент здесь не тестировался.
SIGKILL/power-loss во время записи, актуальная административная политика вне мира,
production-cutover, scheduler/retention/внешняя копия остаются в #33/#34.
Рабочий профиль и существующие миры не менялись, VPS пока не нужен.

## Обычный выход DJ2 без probe — 4 ноября 2026

Владелец вручную выполнил два выхода через меню, повторный вход и штатное закрытие
свежего подписанного клиента 2.23.4 rc.1. Все 224 mod JAR сверены до/после, probe
и его JVM-флага нет. Наблюдение после выходов 40,2/46 секунд, после повторного входа
52,9 секунды, после закрытия 53,5 секунды: новых/перезаписанных reports и поздних
task/fatal markers нет. Client exit 0 до cleanup; Crash Assistant завершился сам.
Семь предметов/12 уровней подтверждены повторным серверным запросом и NBT export
того же UUID. Final Linux stop чистый, OOM=false; собственные volume/auth удалены.

[Подробности и ограничения](DJ2_DISCONNECT.md#обычный-клиент-ручной-контроль-владельца--4-ноября-2026)
сохраняют capture timeouts, принудительное завершение прежней попытки и ошибку
создания тестовой площадки. Обычные действия человека приняты отдельно от раннего
инструментированного stress; это не полный survival, Linux/macOS renderer или
публичный выпуск. #65 можно закрыть после проверки точного PR head; #49 остаётся.

## Проверка остановленных снимков — 4 ноября 2026

Промежуточный Linux recovery-снимок больше не доверяет одному exit 0: до экспорта
требуются остановленный собственный контейнер, отсутствие OOM и читаемый bounded
журнал без фатального маркера Forge. Краш с exit 0, отсутствующий/слишком большой
журнал и неизвестный OOM отвергаются до экспорта/удаления контейнера. Профильные
unit-тесты: Windows 126 passed / 1 skip, Linux Docker 127 passed.

Настоящий DJ2 2.23.4 / Core 0.2.8 прошёл 93 recovery-условия и четыре старта,
включая три чистых снимка, откат/undo/redo/повтор, соседей и сохранённый NBT.
После restart печь работает. Final stop 0 / fatal=false / OOM=false; собственные
volume/auth удалены после экспорта. [Доказательства и ограничения](BACKUP_SAFETY.md#барьер-linux-снимка-после-остановки--4-ноября-2026).
Это не полный Linux world-return, scheduler или готовая безопасная команда #34;
неатомарность неполного native restore и отсутствие entity restore сохранены явно.
Рабочий профиль/миры/FTB Backups не менялись; #33/#34/#49 остаются открытыми.

## Текущая работа и issues

Открытые задачи ведём в [трекере первого запуска #41](https://github.com/omkality/omkalitycraft/issues/41)
и [milestone DJ2](https://github.com/omkality/omkalitycraft/milestone/1).
P0 — краши/безопасность/потеря данных, P1 — подготовка открытия, P2 — следующие этапы.
У каждой задачи есть критерии приёмки; PR закрывает только реально выполненную и
проверенную область. Здесь остаются решения и доказательства, отдельный полный backlog
не дублируется. Подробные security-fixtures и Core не публикуются в issues.

Решение 2 ноября: переход на свежий русскоязычный DJ2 проверяется в
[#49](https://github.com/omkality/omkalitycraft/issues/49). По решению владельца цель первого
запуска — 2.23.4 с проверенным русским overlay на основе перевода BMProjects 2.23.3.
Наличие всех языковых ключей не заменяет проверку смысла и настоящего клиента.
Настройка API закрыта PR #50. Кандидат 2.23.4 прошёл [первые 15 Linux-условий](DJ2_UPGRADE_PREFLIGHT.md),
два старта и полный restart с независимой проверкой сохранённого инвентаря, пока без Core/клиента.
Затем [Core 0.2.8 на 2.23.4](DJ2_CORE_UPGRADE.md) прошёл 17 startup/persistence условий,
220 проверок инвентарных границ, 67 WR-CBE и 50 RTP; старый профиль сохранён отдельным
контролем. Синтетический mod list не является разрешением реального клиентского выпуска.
Далее полная миграционная копия/возврат и клиент/перевод. Весь аудит старой 2.21.3 перед этим не завершаем. Payload/профиль
пока не переключались; [порядок обновления](PACK_UPGRADES.md) и приёмка обязательны.

[Настоящий Windows-клиент 2.23.4](DJ2_RENDERED_CLIENT.md) теперь собран из всех
223 точных авторских JAR; BOM/источники закреплены, повторно использованные файлы
независимо сверены. Выявлен отдельный блокер [#63](https://github.com/omkality/omkalitycraft/issues/63):
UniversalTweaks 1.20.0 dereference null GUI при прямом входе. Поддерживаемый mode
NOTHING отключает только декоративный load-sound handler. После изменения staging
пройдены 17 реальных GUI-условий, 20 runtime locale keys и обычный контроль без probe
со штатной очисткой лишнего JAR/сохранением инвентаря/чистым завершением.
Это не выпускной install/update и не полная приёмка перевода. Причина NPE AgriCraft —
отсутствующий ServerData при переподключении диагностического инструмента. После
исправления только fixture три входа подтвердили запись 262 сетевых JSON каждый.
Но общий ранний итог 21 условия отозван: после выхода появились поздние NPE сетевых
задач vanilla/Bewitchment, несмотря на client exit 0. [#65](https://github.com/omkality/omkalitycraft/issues/65)
требует независимого штатного контроля и post-disconnect/post-exit аудита. AgriCraft
и рабочий Core для этого случая не менялись. Приоритет владельца — стабильность:
если 2.23.4 требует множества исправлений, сравнить со старым кандидатом и выбрать
надёжную основу; обновление не обязательно любой ценой.

[Парное сравнение раннего выхода](DJ2_DISCONNECT.md) 4 ноября воспроизвело проблему
и на 2.21.3; Bewitchment handler class совпал побайтно. Приватный клиентский адаптер
0.1.0 отменяет только отложенные задачи исходного закрытого соединения. 14 Java-условий
прошли на Windows и Linux JRE; реальные Windows-клиенты с Linux-серверами прошли по
5 циклов / 41 условию, с сохранением инвентаря/опыта и post-exit аудитом. Серверный
Core 0.2.8 не менялся. На target дополнительно проверены version rejection/restart,
обычный вход/server kick без probe и чистое завершение; все 11 baseline handled
reports найдены в закрытой локальной очереди лаунчера ещё при работающем процессе.
Обычный клик выхода без probe не подтверждён из-за двух Windows capture timeouts:
#65 остаётся открытым. Полный выпуск/обновление/renderer Linux/macOS не приняты,
рабочий payload остаётся прежним. Неуспешные fixture-попытки сохранены в отчёте.

[Подписанный клиентский кандидат](SIGNED_PACK_INSTALL.md) прошёл 22 условия:
полная установка source/target, обрыв HTTP и Range resume, repair двух модов,
сохранность options/JourneyMap/личного списка серверов. Чистая установка проверена
через настоящий Linux API; обновлённая папка затем вошла в Linux Forge с обычным
Windows-клиентом без probe и завершилась чисто. В игре сохранены Circle/grid
JourneyMap. Команда `omk lab pack-install` повторяет транспортные проверки на новых
копиях; SIGKILL/потеря питания, серверная миграция и renderer других ОС этим не приняты.
В 0.3.0.dev9 убран fallback запуска cached pack после ошибки проверки манифеста:
при сетевом отказе/невалидной подписи запуск прекращается, файлы и сессия сохраняются.
Рабочий профиль остаётся 2.21.3; подписанный rc.1 не является публичным выпуском.

В 0.3.0.dev10 отдельный `pack-install --hard-kill` прошёл 15 условий на полной DJ2:
Windows TerminateProcess, новый процесс с Range resume от 262 144 байт, все hashes
и личные файлы сохранены. Потеря питания этим не проверена. Новый signed schema 2
содержит обязательный минимум версии лаунчера; слишком старый клиент прекращает
подготовку/запуск. Dev9 reader отверг новый формат, новый reader принял совместимый
минимум и отверг будущий до artifacts. Payload rc.1 не менялся, отдельный rc.2 —
только локальная проверка метаданных. [Доказательства и границы](SIGNED_PACK_INSTALL.md).

Повторный `omk lab admin smoke` с Drasl 4.0.0 прошёл 16 условий. Отзыв приглашения
запрещает регистрацию по этому коду; другие коды и существующий аккаунт/сессия
сохраняются. Коды одноразовые, сами по времени не истекают; [инструкция](ADMIN.md)
различает отзыв неиспользованного кода и отдельную блокировку уже созданного аккаунта.

Уточнение владельца 4 ноября: ключ — только одноразовое приглашение, не пожизненное
разрешение, связанное с аккаунтом. Можно вручную разыграть код в чате; первый успешно
зарегистрировавшийся получает аккаунт, код сгорает. Неиспользованный код отзывается,
бан уже созданного игрока выполняется отдельно. В [#70](https://github.com/omkality/omkalitycraft/issues/70)
найдена гонка стандартного Drasl 4.0.0: последовательного reuse-контроля было недостаточно.
Минимальное исправление транзакции включено в Docker `4.0.0-omk.1`, без новых таблиц
или самописных паролей. Проверены 20 раундов по 2/4/8 участников, фактические аккаунты
и профили, 20 гонок отзыва и restart. [Правило и доказательства](INVITATIONS.md).
Первый concurrency-стенд упёрся в штатный HTTP rate limit; не принят как полный.

В 0.3.0.dev11 по решению владельца вместо выдачи случайного пароля — свой пароль и его
повтор на одной форме регистрации. Проверка длины/совпадения выполняется до HTTP;
короткий пароль также отвергается Drasl без потребления приглашения. Поля не сохраняются
в настройках/логах и очищаются после входа. В новом стенде реальный Qt + Drasl прошли
29 условий, включая уже завершённую регистрацию с потерянным ответом и последующий
обычный вход тем же паролем. На диске остаётся только игровая сессия, восстановление
без почты административное. [Текущая модель](PORTABLE_SESSIONS.md).

Первый Linux UI CI PR #69 завершился внутри Qt repaint (exit 139), полный повтор с
именами тестов прошёл все 8 jobs. Это не исправление причины:
[#71](https://github.com/omkality/omkalitycraft/issues/71) остаётся отдельной задачей.

Последующий парный контроль #71 локализовал дефект владения тестовыми окнами:
`qtbot` хранил слабые ссылки, и GC мог удалить окно после возврата теста, до штатного
закрытия и завершения repaint. Только очистки traceback оказалось недостаточно.
Удержание зарегистрированных окон до teardown прошло исходный сценарий 60 раз на
Windows/Linux и по 132 GUI-проверки с усиленным GC; два новых ownership-контроля
провалились на старой fixture и прошли на новой. Код приложения/Qt не менялись.
Добавлена постоянная регрессия Desktop CI. [Доказательства и границы](QT_TEST_LIFETIME.md).

Последующая косметическая задача владельца [#64](https://github.com/omkality/omkalitycraft/issues/64):
исходная иконка руды, заголовок «Omkalitycraft — <сборка> · <версия>» уже при загрузке
Minecraft, значок окна/панели задач и отдельная проверка ОС. Это данные профиля за
адаптером; не срочный блокер и пока без изменений UI.

При подготовке миграции [read-only сравнение 46 реестров](DJ2_MIGRATION_REGISTRIES.md)
выявило 6 отсутствующих прежних имён блоков и 35 предметов; это требует разбора,
а не означает автоматически 41 потерянный объект. В точном official target авторские
datafixers отключены на dedicated server. Нативный перенос копии дошёл до FML
StartupQuery перед стартом мира; новое направление [#61](https://github.com/omkality/omkalitycraft/issues/61)
остаётся открытым внутри #49. `omk upgrade registry-audit` только читает остановленные
копии; Linux-стенд теперь заранее отменяет запросы, не подтверждая удаление mappings.
Репетиция отказа/возврата прошла 50 нативных условий и 12 проверок остановленных
снимков: исходные вещи/NBT, AE2/EnderIO/Thermal, тот же UUID, рабочий home,
записи FTB и один завершённый квест сохранены. Target с cancel-политикой отвергнут
до Done без OOM. Это проверенный возврат source, а не принятая конверсия target;
первый неуспешный pilot и ограничения описаны в отчёте.
Для первого открытия владелец ранее выбрал новые миры, без переноса старых.
Поэтому конверсия legacy-вещей #61 выделена за пределы первого открытия; она
потребуется перед переносом сохраняемого source-мира. Следующий этап #49 —
настоящий русский клиент fresh 2.23.4 и регрессии. Будущие миры игроков не
разрешено вайпать ради обновления; приёмка миграции и выборочный откат остаются.

RTP — [#27](https://github.com/omkality/omkalitycraft/issues/27): 50 Linux-проверок,
8 проверок CI, PR #42 слит в `dev` (01bdebd), issue закрыт.
[WR-CBE при остановке #28](https://github.com/omkality/omkalitycraft/issues/28): Core 0.2.6,
67 Linux-проверок / 3 старта, два restart с повторным переключением беспроводной связи;
baseline воспроизвёл естественный NPE. [Доказательства и границы](WRCBE_SHUTDOWN.md).
Следующий блокер: [границы FTB/модовые механизмы #29](https://github.com/omkality/omkalitycraft/issues/29).
Его первая часть [#46](https://github.com/omkality/omkalitycraft/issues/46): Core 0.2.7,
219 реальных Linux-проверок одного автономного эффекта, 28 сценариев / два старта;
baseline на тех же сценариях воспроизвёл обход. [Правило и границы](AUTOMATION_BOUNDARIES.md).
Без диагностических модов Core 0.2.7 прошёл ещё [50 RTP-проверок](validation/dj2-rtp-core-0.2.7-2026-11-02.json)
с усиленным определением посадки по измерению/полным координатам и чистой остановкой.
Это не закрывает весь #29: другие эффекты, рост, биомы, машины и взрывы — отдельно.
[Полный проход env #30](https://github.com/omkality/omkalitycraft/issues/30) обязателен
перед VPS и пока не завершён. Его [часть API #48](https://github.com/omkality/omkalitycraft/issues/48)
закрыта после 16 Linux Docker условий и 8 CI jobs: единый entrypoint и env-параметры
Compose; [описание](API_RUNTIME.md). Остальная конфигурация ещё требует аудита.
В расследовании [#54](https://github.com/omkality/omkalitycraft/issues/54) пойман
deadlock остановки Granian 2.7.3, сопоставленный с upstream #875. Кандидат 2.8.6
прошёл 24 обычных Linux-цикла и сравнительную синтетическую гонку; добавлена
постоянная CI-регрессия. PR #59 слит в `dev` (6691c22) после 8 зелёных CI jobs
точного head 225e982, включая Windows/Linux/macOS; #54 закрыт. Живой сервис не развёртывался.
GTNH отслеживается отдельно после DJ2.

Установление автора лаг-машины/краш-чанка — отдельный обязательный этап до приглашения
игроков [#52](https://github.com/omkality/omkalitycraft/issues/52).
Нужен серверный журнал действий по UUID с измерением/координатами/временем и связь с
инцидентом; владелец привата, последний посетитель и автоматизация не доказывают авторство.
Сначала проверяем готовые Forge-решения, затем необходимые узкие адаптеры. Доступ только
владельцу через `omk`; нужны лимиты диска/очереди и проверка сохранности при сбоях.
[Требования и границы доказательств](ACTION_ATTRIBUTION.md). Реализация ещё не выбрана.

Дополнение владельца: сохранять весь игровой текстовый чат, включая личные и FTB-каналы,
для поиска жалоб по UUID/нику/периоду и контексту. Отдельный архив и owner search пока
отсутствуют; обычные ротируемые логи их не заменяют. Этап до открытия —
[#58](https://github.com/omkality/omkalitycraft/issues/58),
[требования и предложенные лимиты](CHAT_HISTORY.md). Предложены 90 суток/256 МиБ,
что наступит раньше, с env overrides; окончательная реализация и приёмка ещё впереди.

Решения владельца по хранению/приветствию: Drasl оставляем на SQLite без собственного
форка ради PostgreSQL; перед VPS нужны постоянные данные и проверенное восстановление.
Приветствие с короткими командами переносится в чат при входе в первые наигранные часы
([#44](https://github.com/omkality/omkalitycraft/issues/44)); title по центру отменён.
Предложенный настраиваемый порог — 3 часа. Серверный учёт времени по UUID/профилю
([#43](https://github.com/omkality/omkalitycraft/issues/43)) отделяет онлайн от будущей
политики активности/наград; активность AFK автоматически не доказана. Подробный справочник
лаунчера остаётся отдельным последующим этапом #39. Реализация этих пунктов ещё предстоит.

## Назначение и состояние

Лаунчер для сообщества стримера: ник → свой пароль и повтор → одноразовое приглашение →
запомненная сессия → установка сборки → игра. Без обязательных сайта, Telegram,
Microsoft, Ely.by и платёжной интеграции. Python отвечает за лаунчер, API и операции;
Java и адаптеры — за версионную интеграцию Forge. Приваты используют FTB / ServerUtilities.

Версия разработки — **0.3.0.dev11**. Локально на Windows проверены установка DJ2 RU 2.21.3,
вложенная Java, настоящий вход на отдельный Forge-сервер и автообновление готового лаунчера.
Публичный сервис ещё не развёрнут. GTNH остаётся планируемым профилем. Полный сервер DJ2
запущен в Linux Docker, полноценный Windows-клиент вошёл на него. Стандартный скин и
три загруженных варианта осмотрены на игровых кадрах. Игровые клиенты Linux/macOS
требуют отдельных проверок.

## Папки и Git

Changelog и документация владельца/игрока ведутся на русском; названия коммитов и
`AGENTS.md` — на английском. При изменении интерфейса показывать PNG соответствующего
состояния, включая проверку минимального окна, и давать ссылку на проверенный локальный
exe вместе с его папкой зависимостей. Скрин PR не заменяет скрин лаунчера.

Ссылка владельца в Telegram: https://t.me/vy_bolshovo_psa. Она добавлена к YouTube,
Twitch и Kick с монохромными иконками. Изолированный preview дистрибутива может иметь
отключённые адреса сервисов; такой exe не объявлять готовым для входа на публичный сервер.

Логотип от 2 ноября — именно предоставленный владельцем PNG блока руды мёртвума,
без AI-перерисовки. Файл/хеш закреплены в `launcher/assets/branding/provenance.json`;
он используется в общей шапке, значке окна и упаковке системного значка.
Альтернатива денежной проходке обсуждается в [памятке по баллам](STREAM_ACCESS.md):
цены являются предложением, награды на площадках не создавались, правила внешней
платной услуги нужно проверить отдельно. Новые привязки аккаунтов не добавляются.

Уточнение владельца: после активации награды зритель просто пишет в Telegram;
challenge-фразы и подтверждение аккаунта стрим-площадки не нужны. Принят риск ручной
выдачи при публичной заявке. Это не административный сброс пароля существующему игроку.
У запланированных профилей (сейчас GTNH) настройка RAM недоступна и приглушена.
Отказ ввода символа в ник показывает короткую подсказку, не забирая фокус.

Краши/баги/дюпы испытываются на ПК владельца в отдельных Linux Docker-стендах, максимально
совпадающих с будущей серверной средой. Закреплённые image/Java/моды/config нужны и там,
и на VPS; Docker сам по себе не воспроизводит сеть VPS, диск, лимиты CPU/RAM и нагрузку.
Сейчас Forge/Drasl проверяются в Linux-контейнерах; Granian в последнем crash-lab был
Windows-процессом. Контейнеризация API/БД/операторских задач остаётся до развёртывания.

Настройки эксплуатации должны иметь проверяемые env overrides и документированные
defaults; некорректное значение отклоняется явно. Не менять исходники ради лимита логов,
бэкапов, адреса сервиса или тайминга. Параметры игрового профиля готовит адаптер до запуска
контейнера; Forge-мод сам по себе не начинает читать наши переменные окружения. Ключи
доверия и проверку целостности нельзя отдавать произвольным клиентским override.

Новый обязательный этап: общий бюджет диска VPS для миров, FTB/операторских бэкапов,
логов/крашей/inbox, staging обновлений, Docker images/cache и свободного резерва. В старом
DJ2 `ftbbackups.cfg`: каждые 2 часа, 12 копий, `max_total_size=75%`. Это обнаруженная
прежняя настройка, не утверждённый лимит для VPS. Проверить семантику процента и ротации
точной версии FTB Backups, явный лимит объёма, одиночную слишком большую копию, отказ
диска и восстановление; существующие бэкапы автоматически не удалять. Полный диск нельзя
лечить удалением единственной пригодной копии. Резервные копии на том же VPS не заменяют
отдельную копию вне его диска.

Решения владельца от 1 ноября 2026: домашнего публичного хостинга не будет. План —
DJ2 на IT Garage RZ-W-6 после локальной подготовки, затем отдельный такой VPS для GTNH,
когда DJ2 завершён; большой VPS/дедик выбирается позже по измеренной нагрузке.
FRPS/FRPC и домашний NAT не входят в обязательные этапы. Российский шлюз добавляется
только при подтверждённой проблеме прямой доступности. Локальные стенды остаются для
разработки; аренда/развёртывание пока не выполнялись. Сообщить владельцу, когда для
следующего этапа потребуются VPS и публичные адреса. Бюджет до 100 €/мес., ориентир
до 10–15 игроков на сервер; тариф/цена не заменяют проверки реальной нагрузки.

Один аккаунт сообщества даёт доступ ко всем его серверам. Почта отложена; первичное
восстановление — административный сброс случайного пароля через прежнюю доверенную
переписку в Telegram, без бота/обязательной Telegram-интеграции. Такой сброс ещё нужно
реализовать и испытать с отзывом токенов и обработкой уже открытого игрового подключения.
Решение об оплате входа пока не фиксируется; платёжной интеграции не будет.

Весь актуальный код находится в `minecraft_server/omkalitycraft`, включая `launcher/`.
Лаунчер и API остаются одним репозиторием `omkality/omkalitycraft`.

- `master` сохраняет прежнюю историю; `dev` — интеграция проверенных изменений.
- Работа ведётся небольшими коммитами на feature-ветках с PR в `dev`.
- OmkalityCore остаётся вне публичного репозитория; новая версия проверяется только на отдельном стенде.
- Миры, БД, `.env`, сессии, закрытые ключи и payload сборок не публикуются.
- Старый `omkality_launcher` сохранён в `../project-analysis/archives/omkality_launcher-legacy-2026-10-30`.
  Рабочий `omkality_server` не переносился и не обновлялся.

## Запуск разработки

```powershell
uv sync --locked --all-groups
uv run omk doctor
uv run omk server list
docker compose -f deploy/auth-lab/compose.yaml build --pull
uv run omk lab launcher smoke
uv run omk lab auth expiry
uv run pytest -q
```

Тестовые Drasl-контейнеры используют уникальный Compose-проект, loopback и именованный volume.
Рабочие аккаунты, БД и миры не подключаются. Закреплён Drasl 4.0.0 по digest образа.
GUI-тесты всегда передают собственное временное хранилище сессии.

CDN отдельно от аккаунтов, после создания/подготовки папки контента:

```powershell
$env:CONTENT_ROOT = (Resolve-Path "data/content").Path
uv run granian --interface asgi api.app:app --host 127.0.0.1 --port 8000
```

Старый `.env` может содержать Docker-путь `/data/content`. Для локального процесса
путь задаётся окружением, без изменения рабочего `.env`.

Интерфейс из исходников:

```powershell
uv run omk launcher --auth-url http://127.0.0.1:25586 --api-url http://127.0.0.1:8000 --root .local/player-test --data-dir .local/player-test/userdata
```

Нужны отдельно запущенные Drasl и CDN с подписанным релизом. Без `--api-url` установка
отключена. Это команда разработки; автообновления проверяет входная программа дистрибутива.
Публичные адреса и рабочие ключи выдачи релизов ещё не настроены.

## Реализованное поведение

Сессия хранится переносимым файлом без системного keyring. Пароль и Drasl API token
не сохраняются. Автовход и запуск игры обновляют игровой токен; окончательно истёкшая
или отозванная сессия требует входа. Смена пароля отзывает прежние токены.
Кнопки забывания входа и завершения всех сессий убраны из UI; серверный отзыв сохранён.
Подробности: [PORTABLE_SESSIONS.md](PORTABLE_SESSIONS.md).

Интерфейс использует вложенный Rubik Bold (15 px) и Monocraft Bold для ввода ника,
карточки сборок, ссылки на версии CurseForge,
описания и проекты перевода. Вращающийся скин рисуется Qt без браузерного движка.
PNG ограничен 256 КиБ, декодируется и пересохраняется без метаданных. Одна кнопка загрузки,
автоматическая подсказка модели и вращающийся предпросмотр; необязательная коррекция
«Стандартная / Узкая» скрыта по умолчанию. Выбор версии Minecraft убран.
Вопрос у скина и текст о техническом отчёте на регистрации убраны по решению владельца;
автоматический bounded сбор крашей сохранён. [Шрифты/ник](FONTS_AND_NAMES.md).
Все три предоставленных владельцем PNG сохранены с хешами; первый Slim выбран стандартным
обликом лаунчера и штатным default skin Drasl. Подробности и ограничения: [SKINS.md](SKINS.md).

Подписанный manifest задаёт файлы, размеры, SHA256, Java, агент и параметры Forge.
Установщик проверяет файлы, докачивает загрузки, восстанавливает повреждения и удаляет
только устаревшие файлы из прежних подписанных описаний. Незавершённая установка не готова.
Сохранения, скриншоты, карты и личные параметры исключены из управления релизом.
Конфиги, перечисленные в manifest, являются управляемыми файлами сборки.

Java, сборки, временные файлы приложения, журналы и обновления находятся в переносимой папке.
Вторая копия с теми же данными блокируется, в том числе пока Minecraft работает после скрытия
окна лаунчера. Внешние глобальные Java options не наследуются.

Автообновление использует TUF, отдельные папки версий и подтверждение запуска нового окна.
При сбое возвращается рабочая версия. Команды и модель доверия: [RELEASES.md](RELEASES.md).

## Проверки и ограничения

Локально проходит 451 unit/UI-тест (два Windows symlink-теста пропущены без привилегий), Ruff и Black. Загрузчики проверяются настоящим локальным HTTP.
Auth/GUI smoke включает 26 проверок настоящего Drasl и Qt: default skin/Slim metadata,
автоподсказка и загрузка/чтение всех трёх PNG, регистрация/сессии и отзыв при очистке.
Expiry smoke проверяет настоящее истечение токена.

Клиентский crash-lab прошёл 27 сквозных проверок: настоящий Windows DJ2 на Linux Forge,
управляемый тестовый краш при выключенном API, сбор отчёта ещё до закрытия Minecraft,
автоматическая доставка после восстановления API и штатного выхода, закрытый экспорт
владельца. Это воспроизводимый тест, а не случайное падение игрового мода. Старый admin
smoke повторно прошёл 13 проверок Drasl/HTTP/CLI. Подробности: [CLIENT_CRASH_TESTING.md](CLIENT_CRASH_TESTING.md).

Настоящий Minecraft DJ2 вошёл на отдельный Forge 1.12.2 / 14.23.5.2860 в `online-mode=true`
через authlib-injector 1.2.8. Отдельные настоящие Forge login-пробы подтвердили правильный UUID
и отказ с чужим ником, неверным и отозванным токеном. Это не доказательство отсутствия
всех обходов и дюпов. Стенд использовал новый тестовый мир.

Готовые Windows `.exe` проверены с реальными процессами: подписанное обновление, подтверждение
нового окна, сохранение пользовательских файлов, отказ нового `.exe`, возврат к рабочей версии
и запуск последней рабочей копии при недоступном CDN. Проверка здоровья подтверждает запуск
интерфейса, а не отсутствие всех ошибок релиза.

GitHub Actions проверяет исходники и Qt на Windows/Linux/macOS, настоящий Drasl на Linux,
а также собирает дистрибутив и запускает его в изолированной папке на каждой ОС.
Последнее проверяет упаковку интерфейса; Java/игра на этих платформах проверяются отдельно.
В Litestar остаётся предупреждение об импорте Pydantic v1 под Python 3.14; наш код использует v2.

Целевая серверная среда — Linux Docker на VPS. Новый `omk lab dj2-linux` проверил
регистрозависимый Linux volume, полный Forge, протокольный вход и вход настоящего
Windows DJ2. Образ Java закреплён digest; стенд штатно остановлен, мир экспортирован,
контейнеры и volume удалены. Отдельный Linux-прогон восстановления области прошёл
93 проверки: прежние 92 игровых условия и Linux volume. Полные 111 сценариев возврата
мира пока относятся к Windows. Один предыдущий Linux restart упал в преобразовании
классов ThaumcraftFix/Forge до применения снимка; причина не исправлена, сбойный volume
сохранён. Успешный повтор не доказывает стабильность запуска. VPS-сеть и нагрузка ещё
не проверяются. Инструкция: [SERVER_CONTAINERS.md](SERVER_CONTAINERS.md).

Прежний контроль на read-only клонах воспроизвёл тот же сбой на третьем старте.
С отключённой только `optimizeFMLRemapper` прошли 6 стартов; затем ещё 3 старта
без изменения настройки тоже прошли. На том этапе причинное исправление не было
доказано; исходный конфиг и сбойные volume были сохранены.
[Машиночитаемый отчёт](validation/linux-startup-controls-2026-11-01.json).

Дальнейший захват установил отдельный путь метаданных Mixin: его исключение
`DeobfuscationTransformer` предшествует no-holder падению, хотя обычная JVM-загрузка
ItemBlock может быть успешной. Replay настоящего Forge подтвердил отказ до
деобфускации и успех после неё. Первоначальный триггер ещё не исправлен.
Новый `omk lab dj2-startup` работает на ПК владельца, Linux Docker 6 ГиБ / 4 CPU,
Java heap 4 ГиБ. Пойманное падение произошло при работающем контейнере без Docker/
Java OOM; последующий код выхода после очистки не подменяет причину сбоя.
[Инструкция, режимы наблюдения и ограничения](DJ2_STARTUP_DIAGNOSTICS.md).

Новый парный контроль на одном клоне: исходный `true` упал, `false` прошёл 6 стартов,
возврат `true` снова дал тот же сбой сразу. Поэтому свежие DJ2 lab/staging-копии теперь
отключают только эту необязательную оптимизацию FermiumASM 5.24. Строгий env override
`OMK_DJ2_OPTIMIZE_FML_REMAPPER` описан в инструкции; оригинальный сервер не меняется.
Это конфигурационный обход текущей сборки, не исправление первоначального триггера
и не обещание отсутствия остальных багов. Без startup observer прошли 4 полных старта
и повторные 93 Linux-проверки отката области, включая работу восстановленной печи.
Дополнительный прогон подтвердил вход полноценного Windows DJ2 на свежий Linux-сервер
с обходом без observer, экспорт мира и штатное завершение.
[Обезличенные результаты](validation/dj2-startup-workaround-2026-11-01.json).

Уточнение владельца: **GitHub Releases предназначены только для готового лаунчера
игроков**, не для публикации контрольных срезов исходников/API. Публикуются проверенные
переносимые дистрибутивы; на VPS размещается тот же артефакт, а автообновление использует
подписанные метаданные. Loopback-preview не публиковать как пользовательский релиз.
Исходный prerelease `v0.3.0-dev8` переведён в черновик; публично он недоступен.
Его Git-тег/commit `b23f61c861b412b0c2079e79703801c32f34c97b` сохранены без изменения.
История/ветки/теги обслуживают разработку отдельно от Releases; теги не передвигать.
Первый пользовательский релиз — после публичного развёртывания/сквозного входа и
проверки обновления. Автоматические архивы исходников GitHub и состав наших вручную
прикреплённых файлов различаются: [политика выпуска](RELEASES.md#github-releases-для-игроков).

## Следующий игровой этап

Онлайн добавлен на карточку через `GET /servers/status`; цели/TTL/timeout задаются env,
при их отсутствии сервер не опрашивается. Полный Linux Forge + настоящий HTTP и Qt
подтвердили 0/20, 1/20, отключение игрока и offline после остановки. Подробнее:
[SERVER_STATUS.md](SERVER_STATUS.md). Публичного сервиса ещё нет.

Добавлены `omk storage plan` и `deploy/storage.example.env`: env-настройки с defaults,
проверкой общего бюджета и staging, без записи/удаления данных. Это **план**, не готовые
дисковые квоты/retention. В установленном FTB Backups 1.1.0.1 байткодом подтверждены
процент от полной ёмкости и удаление старых копий до завершения новой; отказ записи
и безопасный эксплуатационный планировщик ещё нужно проверить.

Первый слой безопасной ротации проверяется отдельно: `omk lab backup-safety` создаёт
только одноразовый Linux-контейнер с синтетическими файлами. Новая копия проходит
полную сверку/перечитывание до публикации и удаления старых; должны помещаться новая
и предыдущая копии. При ENOSPC/SIGKILL история сохраняется, незавершённая операция
блокирует бесконечные staging-повторы. Это пока не Forge-адаптер/планировщик, прежний
FTB config не меняется. [Устройство, тесты и границы](BACKUP_SAFETY.md).

Проверен и архив ранее чисто остановленного Linux DJ2-стенда: независимый перечень из
исходного TAR, три публикации/ротация, возврат всех 270 файлов в пустой каталог и
сверка SHA256. Minecraft в этом новом опыте не запускался; это не игровой restore.
[Запись файловых отказов и round trip](validation/backup-safety-2026-11-01.json).

Предгенерация и отдельные лимиты измерений обязательны до публичного запуска. Первичное
предложение: основной/ресурсный мир по 16384, Nether 8192, End 16384 блоков в диаметре;
остальные только после runtime-реестра/проверки прогрессии. Это ещё не применённые границы.
FTB RTP использует радиус от (0,0); начальный максимум — около ⅔ радиуса основного мира,
с отдельными проверками поверхности, границы, claims и порталов. Полный размер не равен
объёму первой предгенерации. Подробный план/источники: [WORLDS_AND_STORAGE.md](WORLDS_AND_STORAGE.md).
Картинки/описание миров на карточке лаунчера добавить после игровых проверок. Предгенерация — в самом конце подготовки: локально, перед переносом на VPS; сейчас её не выполнять. Лимит игровых слотов — 20; онлайн нужен на карточках, недоступность не показывать как 0/20.

Зафиксированное предложение владельца: при сетевом сбое обновления лаунчера/сборки
нужны понятная ошибка и повтор без повреждения рабочей установки. Для обязательных
обновлений безопасности требуется согласованная серверная/API-политика совместимости;
номер версии, присланный клиентом, не является доказательством подлинности его процесса.
Текущий проверенный offline fallback лаунчера не следует выдавать за готовую политику
допуска устаревших клиентов. Это отдельный будущий этап, текущие проверки крашей не прерывает.
При реализации отдельно проверить: отсутствие сети до запроса метаданных; обрыв загрузки
и повтор; недоступный CDN при доступных auth/игровом сервере; обязательную новую версию;
откат неудачного обновления при уже повышенном минимуме безопасности. Ошибку подписи
не маскировать под сетевую, непроверенную/частично установленную сборку не запускать.
Сохранить userdata и настройки игрока; обычный необязательный релиз сам по себе не должен
автоматически объявлять все предыдущие установки небезопасными.

1. Разобрать непостоянный сбой запуска Linux-сервера до публичного запуска.
2. Оставшаяся визуальная проверка меню серверов и полной карты JourneyMap; скины,
   русская надпись инвентаря и квадратная миникарта уже осмотрены на кадрах Minecraft.
3. FTB, права, границы, RTP, резервные копии и отдельный ресурсный мир.
4. Выбор GTNH и отдельная проверка его модов.
5. Игровые релизы и Java для остальных платформ.
6. До приглашения игроков: политика обязательных обновлений и сетевых отказов,
   согласованное развёртывание HTTPS-сервисов и пробный вход приглашённого игрока.

Переводы пока вторичны. Есть проект DJ2 **2.23.3**:
https://github.com/BMProjects-Development/Divine-Journey-2-Translate — это не установленная
локальная 2.21.3; автор её перевода пока не подтверждён. Для GTNH есть
https://github.com/GTNewHorizons/GTNH-Translations. Ссылки в UI не означают применения обновлений.

В новом чате достаточно прочитать корневой `AGENTS.md`, этот документ и текущий Git status.
Исторические отчёты в `../project-analysis` не являются новыми заданиями.

## Настройки игрока — 0.3.0.dev1

На карточках сборок есть отдельный выбор RAM с сохранением в `userdata/preferences.json`.
Начальные профили: 6 ГБ, верхний предел 16 ГБ. Предел дополнительно ограничен физической ОЗУ
с резервом под ОС/Java. Ниже рекомендации показывается предупреждение; это не обещание
работоспособности на слабом ПК. Выбор передаётся настоящим `-Xmx`, память из manifest не переопределяет его.
GTNH ещё не проверен в игре, его начальный профиль памяти предварительный.

Официальный сайт GTNH указывает стабильный 2.8.4 отдельно от nightly 2.9.0. Из его Prism ZIP
проверен `instance.cfg`: `OverrideMemory=false`, конкретную норму он не задаёт. DJ2 также не
содержит найденной жёсткой авторской нормы на доступных основных страницах. Поэтому 6 ГБ для
DJ2 — наш проверенный старт, а не выдуманная гарантия автора. Источники:
https://www.gtnewhorizons.com/downloads/ и https://www.curseforge.com/minecraft/modpacks/divine-journey-2 .

`launch.client_defaults` в подписанном описании задаёт обязательные ресурспаки, язык первого
запуска и совместимые серверы. В тестовом DJ2 включён существующий `FM_NewFont`, `ru_ru` и
`forceUnicodeFont=false`. Старые миры и серверы не импортируются. Публичных адресов ещё нет;
loopback в лабораторном manifest не является адресом будущего сервера. Для каждой сборки
нужен свой совместимый сервер, DJ2 и GTNH нельзя соединять одним игровым профилем.

Личные options/добавленные игроком серверы сохраняются. Перед изменением файлов создаётся
локальная копия в `.omk-defaults-backups`. Небезопасные пути, плохие форматы и слишком большие
файлы останавливают запуск с понятной ошибкой. Все изменения проверяются на временных данных.

Проверки всех обсуждённых игровых функций ведём по [GAME_TEST_MATRIX.md](GAME_TEST_MATRIX.md).
Непроверенные строки не считать готовыми. Пользователь разрешил выпуск проверенных этапов в
`master` и удаление завершённых feature-веток после проверки их слияния. Развёртывание отдельно.

Начальные личные настройки DJ2 лежат в `profiles/client-defaults/dj2.json`: найденная в архиве
основная миникарта JourneyMap квадратная, сверху справа, без сетки; большая карта тоже без
сетки. Эти JSON-конфиги создаются только при отсутствии, пользовательские изменения не
перезаписываются. Миры, исследованная карта и точки не переносятся. Поддерживаемые пути
ограничены адаптером JourneyMap 5.7; никакой сборочной логики в GUI нет.

Повторный реальный DJ2-вход прошёл с `-Xmx5120M`, активным `FM_NewFont` и одним совместимым
сервером в NBT. Эти настройки подтверждены файлами запущенного клиента и журналом сервера.
Первый захват окна Minecraft через computer-use дважды завершился тайм-аутом (`FrameArrived timed out`,
`window capture timed out`). 1 ноября это обойдено штатной F2 игры через Computer Use:
осмотрены скины, русская надпись инвентаря и квадратная миникарта без сетки на новом
Windows-клиенте, вошедшем на Linux Docker Forge. Полная карта и меню серверов ещё
требуют визуальной проверки. Seed JourneyMap и сохранение пользовательских изменений
проверены unit-тестами/ремонтом; настройки реального пользовательского клиента этот
прогон не менял. Стенд остановлен, тестовый мир экспортирован, временные контейнеры и volume удалены.
Кадры и границы: [dj2-skin-visual-2026-11-01.json](validation/dj2-skin-visual-2026-11-01.json).


## Проверки целостности и следующая документация — 0.3.0.dev2

Имена Steve/Alex убраны из основного выбора модели: там только версии Minecraft;
разница моделей остаётся в справке. Начальные 6 ГБ не меняются; верхний предел 16 ГБ
дополнительно ограничивается резервом системы (например, 11 ГБ на ПК с 16 ГБ RAM).

В отдельной полной DJ2 удалены Java, мод, конфиг, файл шрифта и библиотека; ещё один
мод испорчен с сохранением размера. Скачаны только шесть нужных файлов; все 6284 SHA256
после ремонта совпали. Личный круглый JourneyMap с сеткой сохранился после повторных
подготовок и ремонта/обновления; после эксперимента в лабораторном клиенте явно возвращены
наши квадратные настройки без сетки. Исправлена лишняя перезапись неизменённого options.txt.

Пользователь уточнил политику: добавленные моды удаляются перед запуском молча. Очистка
ограничена mods/coremods и не касается миров, карт и ресурспаков. Подписанные файлы
восстанавливаются установщиком; перед процессом проверяются хеши модов. Ссылки/junction
не обходятся при удалении. Это контроль нашего запуска, не доказательство честности чужого
процесса. Серверная проверка объявленного FML-списка — отдельный слой; поддельный клиент
может сообщить разрешённый список. Авторизация UUID/сессии при этом остаётся у Drasl.

Старый OmkalityCore по прямому разрешению владельца архивирован в
`../project-analysis/archives/omkalitycore-legacy-2026-10-30-before-rewrite`.
Новый серверный код развивается в прежней приватной папке `../omkalitycore`; в публичный
репозиторий исходники/артефакты этого мода не добавляются. Старая парольная схема не нужна.

Позже нужна отдельная страница лаунчера «Как играть»: общие правила, затем инструкции
выбранной сборки по приватам, командам и границам, с иллюстрациями. Общая оболочка Qt и
данные/изображения профиля, без сборочных ветвлений в GUI. Сначала проверяем реальные команды
и выбираем моды; непроверенные инструкции не публикуем как готовый гайд.


Новый приватный OmkalityCore **0.2.0** проверен настоящим Forge handshake: разрешённый
список принят, добавленный/отсутствующий ID и другая версия отклонены. Полноценный DJ2
также вошёл с этим Core. Core использует только серверный NetworkCheckHandler; клиентская
парольная передача полностью исключена. После игрового запуска JourneyMap сохранил
`Square`, `showGrid=false`, `TopRight`, configVersion 5.7.1p3. Внешний вид остаётся не
подтверждён: native capture снова дважды завершился тайм-аутом.

`omk lab dj2 --help` теперь описывает повторяемый локальный стенд: новый мир/два аккаунта,
loopback Forge + уникальный tmpfs Drasl, контрольные игроки протокола, затем по желанию
настоящий клиент. Команда прошла реальный запуск после оформления в CLI. Исходный сервер
только читается; старые миры/OP-списки/server.properties не переносятся. Игровые действия
выполняются только на собственной копии. Подробности: [PACK_INTEGRITY.md](PACK_INTEGRITY.md).

FTB DJ2: проверены три home и отказ четвёртому, реальная телепортация домой, запрет обычному
игроку fly/god/op/setwarp и просмотра чужих homes. Два игрока проверили обычное ломание:
неприватный блок ломается, чужой приват защищает, владелец может сломать. Creative выдавался
только для контрольного действия в стенде; OP игроки не получали. Это не проверка всех
машин, NBT, контейнеров, взрывов, прав союзников или всех кулдаунов.

Штатный setwarp — админская глобальная команда, без нашей требуемой модели владения
публичными warp. Не открываем её всем: нужен отдельный безопасный адаптер/мод с владельцем,
лимитами, защитой чужих имён и удалением только своих точек. RTP/границы/ресурсные миры,
модерация и откаты остаются следующими задачами матрицы. Гайд запланирован, пока не реализован.


## Каталог команд

[docs/commands/README.md](commands/README.md) — точка входа для выбора ролей: DJ2 human
README и полный runtime-реестр 438 команд/подкоманд, 23 числовых/ранговых параметра,
326 отдельных permission nodes, семейства блоков/предметов. Есть заводские значения и
наши overrides, home/spawn/warp/tpa/back/rtp warmup/cooldown, лимиты приватов/чанклоадеров,
модерация, особенности глобальных warp, технические команды всех зарегистрированных модов.
GTNH отделён как upstream-справка, без заявления о готовом игровом профиле.

Диагностический экспорт добавлен в приватный Core 0.2.1 и включается только явным lab JVM
флагом. Новый Core прошёл тот же реальный Forge/FTB CLI-стенд; команды не исполнялись
ради перечисления. Полный сырой каталог с 22134 permission entries остался в стенде;
публичный JSON содержит все 438 команд, а повторяющиеся права блоков сводит в семейства
с точными исключениями. Рендерер таблиц: scripts/render_command_catalog.py.


## Диагностика — 0.3.0.dev3

[LOGGING.md](LOGGING.md) описывает ротацию, безопасный экспорт и разбор сбоев.
В меню «Помощь» доступен экспорт по профилю; CLI: `omk diagnostics export`.
Логи Python/Java ограничены, collector не накапливает вывод в памяти, при отказе диска
продолжает дренировать stdout. Crash-report, JVM и runtime metadata отбираются без миров,
конфигов и account-файлов; редактирование секретов не является гарантией обезличивания.
Исходный сервер не изменялся. Найденные Log4j 2.8.1/2.15.0 заменяются в новой подписанной
лабораторной сборке на закреплённый Java 8 Log4j 2.25.5; GTNH отдельно не проверен.

Игровые проверки таймеров/модерации остаются следующим этапом: сначала закрыта
запрошенная диагностика, чтобы последующие сбои было чем разбирать.

Ротация проверена настоящим Java 8 с 40000 сообщений и исключением. Новый Forge
прошёл 11 протокольных проверок + вход полноценного DJ2 с Log4j 2.25.5 и UTF-8;
из-за цветовых кодов/кодировки первый наблюдатель не распознал уже состоявшийся вход,
исправлен collector и повторный полный тест прошёл. Клиент/сервер остановлены, auth
удалён. Локальный подписанный payload `2.21.3-omk.4` (6282 файла), прежний сохранён
в `data/content/releases/dj2/windows-x64-before-logging`. Пользовательские JourneyMap
настройки не изменялись. См. docs/validation/logging-2026-10-30.json.

В CI первый готовый дистрибутив выявил пропущенный `omk.diagnostics` в явном
packaging allowlist; список исправлен, фактический packaged startup проверяется повторно.
JVM fatal reports направляются в корень instance и также получают retention 10 / 32 МиБ
после остановки, с сохранением самого нового отчёта при превышении.


## Администрирование и клиентские сбои — 0.3.0.dev4

По последнему уточнению владельца в лаунчере **вообще нет** меню/экспорта диагностики.
Короткий отчёт о сбое собирается автоматически, без алертов и ручного выбора файлов.
[ADMIN.md](ADMIN.md) описывает `omk admin`: explicit private config, allowlisted server ZIP,
login отдельного Drasl admin, приглашения/отзыв/инвентаризация и закрытый inbox клиентов.
Предыдущий top-level `omk diagnostics export` удалён; exporter/admin/report store не входят
в player bundle. UI содержит только краткое уведомление о возможной автоматической передаче.

Upload-only API `POST /reports/client` выключена без явных CLIENT_REPORTS_ROOT/AUTH_URL.
Реальный Drasl game token подтверждает UUID; нет публичных list/get/admin endpoint.
Утилита читает inbox локально на сервере, управление через SSH можно настроить при развёртывании.
Срок отчётов — до 14 суток от получения, 20/игрок, 1000 всего; DB 128 МиБ + временный WAL.
Очистка при записи/старте/почасово и ручным reports prune. Локальная очередь 20 / 2 МиБ / 14 дней,
один запрос за попытку. Raw game/server журналы остаются volume-rotated, не «за 14 дней».

Регистрация с invite — доступ в сообщество, не готовый per-server ACL и не Minecraft OP.
Публичного auth/report сервиса и operator-аккаунта владельца пока нет. Лабы используют
одноразовые аккаунты/tmpfs; никакие существующие ключи, миры или сервисы не меняются.
Проверено 13 реальных Drasl/Granian/CLI сценариев; crash-report синтетический, отдельный
тест дочернего процесса проверяет автоматический сбор. Полноценный DJ2 в этом этапе
не запускался и намеренно не крашился. Таймеры телепортов, OP-free модерация и остальная
GAME_TEST_MATRIX остаются игровым следующим этапом; не потерять их за новой диагностикой.

Проверки этого этапа: docs/validation/operator-tools-2026-10-30.json. Обособлены
IP-бакеты CDN/отчётов, квота 3/час сохраняется независимо от удаления старых тел отчётов,
конкурентный первый upload не требует предварительно созданной БД.

## Игровые команды и модератор — 0.3.0.dev5

`omk lab dj2 --commands` выполнил 43 сценария/наблюдения на полном Forge/DJ2 с Core 0.2.1,
включая настоящий stop/start отдельного сервера. Протокольные игроки не исполняют клиентские
моды и не симулируют физику; графический Minecraft в этом этапе не запускался.
Seed/площадки фиксированы, команды соблюдают spam limit и ждут завершения консоли.
Изменения и воспроизведение: [commands/dj2/TESTING.md](commands/dj2/TESTING.md).

Проверены home/spawn/warp/TPA/back/RTP с короткими таймерами, home при движении/уроне,
одноразовый back, срок/дубли TPA, non-OP модератор, kick/ban/pardon и отказ эскалации прав.
Home cooldown переживает переподключение, но сбрасывается после перезапуска; движение внутри
одного блока не отменяет home. Эти ограничения описаны, не маскируются обещанием полной защиты.

Stock FTB mute пропускал `/me` и личные сообщения. Приватный Core 0.2.2 добавляет узкий
адаптер тех же FTB mute/NBT и chat.speak для vanilla-команд, без новой БД или аутентификации.
Для него используется отдельный guarded-стенд; исходники и jar остаются в `../omkalitycore`.
Этот стенд прошёл 29 сценариев с Core 0.2.2: запрет всех четырёх vanilla-команд/алиасов,
home под мутом, восстановление после unmute и учёт chat.speak. Итоги:
[validation/dj2-commands-2026-10-30.json](validation/dj2-commands-2026-10-30.json).
На этом этапе сохранение мута после reconnect/restart ещё не проверялось; проверка добавлена в dev6.

RTP реально выбирал точку над магмой, а неудачный поиск при маленькой границе расходовал кулдаун.
На этапе dev5 команду временно отключали. **Владелец отменил это решение:** случай магмы
принимается для запуска, RTP возвращён всем игрокам через `command.ftbutilities.rtp: true`.
Замена реализации по этой причине не блокирует запуск. Следующий приоритет — продолжение матрицы
приватов (контейнеры/машины/взрывы/команды), границы/измерения, ресурсный мир, backup/restore
и откаты построек. Собственные публичные warp с владельцем/квотой всё ещё требуют дополнения.
Старый сервер и миры не изменялись; публичного развёртывания нет.

При следующем content-релизе также убрать `vintagefix/transformerCache/jarDiscoverer.cache`
из локального подписанного DJ2 `2.21.3-omk.4` (сейчас он присутствует) и проверить сброс
кэша обнаружения модов при обновлении. Это generated cache, не настройки игрока.
Новый серверный стенд уже не копирует `vintagefix` из старой установки. Не запрещать
скачивание этого пути у старого подписанного manifest до подготовки и проверки нового релиза.

## Состояние мута и взаимодействия с приватами — 0.3.0.dev6

RTP возвращён по прямому решению владельца, известная особенность магмы принята.
Настоящий обычный игрок прошёл warmup RTP в новом ranks-профиле. Автоматическое
отключение команды из-за этого случая больше не является политикой проекта.

Отдельный `--command-suite persistence --mute-guard` прошёл 21 сценарий с Core 0.2.2:
активный мут переживает reconnect и холодный restart, после unmute чат/личные сообщения
доступны при следующем входе. Новая БД/мод для сохранения состояния не понадобились.
`--command-suite interactions` прошёл 19 сценариев: vanilla-установка блоков и доступ
к окну сундука отклоняются чужому в claim, разрешены владельцу и вне claim.
Базовые проверки auth/Core/домов/ломания повторены в обоих стендах. Все игроки non-OP;
creative для блоковых положительных контролей задаётся только консолью лаборатории.

Это серверные протокольные тесты, без исполнения клиентских модов и физики. Перемещение
предметов, модовые машины/контейнеры, трубы, взрывы и союзники остаются следующими кейсами.
Старый сервер/миры не изменялись, оба новых Forge остановлены, Drasl удалены.
Сводка: [validation/dj2-persistence-claims-2026-10-30.json](validation/dj2-persistence-claims-2026-10-30.json).

## Дополнительные проверки контейнеров — 31 октября 2026

Версия приложения остаётся `0.3.0.dev6`: этот этап расширяет инструменты проверки,
без изменения UI, API, модов или серверных игровых правил. `--command-suite containers`
прошёл 26 сценариев на полном отдельном DJ2/Forge с Core 0.2.2. Два non-OP игрока в
survival проверили vanilla- и Iron Chest: перенос вне claim и владельцем внутри,
отказ чужому при открытии и клике с закрытым window ID, отсутствие дополнительного
слитка после повторного клика закрытого окна. Сверены серверные Items/Inventory и
точное число предметов, а не только сетевые сообщения.

Протокольный наблюдатель не исполняет модовый клиентский код и не предсказывает GUI;
на контрольных переносах он получал коррекцию (`accepted=false`), хотя сервер перемещал
слиток. Это зафиксированная граница теста, не утверждение о совместимости GUI/всех дюпах.
Также исправлена home-площадка: перед `/fill` загружается чанк, наличие пола подтверждается
через сервер. RTP остаётся включённым по решению владельца.

Испытан существующий `ironchest-1.12.2-7.0.72.847.jar` по SHA256; его metadata/client
mod list сообщают `1.12.2-7.0.67.844`. Файл не заменялся, upstream-версия по одному
имени jar не предполагается. Составные сундуки на границе, отзыв прав уже открытого
контейнера, машины/трубы/жидкости и команды/союзники ещё требуют отдельных сценариев.

Отдельный `--command-suite explosions` прошёл 18 сценариев, включая те же 14 базовых
проверок. TNT разрушил контрольный блок вне claim, сохранил блок внутри; на границе
один взрыв разрушил наружный блок и сохранил внутренний. Это проверка урона блокам
от обычного TNT, не урона игрокам/сущностям и не всех модовых взрывов. Оба стенда
штатно остановлены, временный Drasl удалён. Исходный сервер и миры не менялись.
Сводка: [validation/dj2-containers-tnt-2026-10-31.json](validation/dj2-containers-tnt-2026-10-31.json).

## Составные сундуки и исключение из команды — 31 октября 2026

На Core 0.2.2 подтверждены два обхода установленных FTB-приватов. Игрок ставил
внешнюю половину двойного сундука на свободном чанке и доставал слиток из приватной
половины. Исключённый из команды игрок также продолжал брать предметы из ранее
открытого vanilla- или Iron Chest. Полный baseline прошёл 24 сценария; его `ok`
обозначает успешное измерение, а не безопасное поведение stock-защиты.

Приватный Core **0.2.3** добавляет узкий DJ2-адаптер: проверяет обе половины через
FTB и закрывает поддерживаемое окно при исключении участника. FTB продолжает владеть
приватами, отношениями и исключениями прав; нового хранилища нет. Исходники и jar
остаются в `../omkalitycore`, в публичный репозиторий не входят.

`--command-suite claim-edges --mute-guard --claim-guard` прошёл **49** сценариев:
оба обхода отклонены, окна после kick закрыты сервером; владелец и действующий участник
сохраняют доступ. В том же стенде повторены 12 обычных контейнерных проверок и non-OP
модерация/мут. GUI-код клиента и физика не исполнялись. Другие контейнеры/машины/трубы,
альтернативные изменения прав/GUI и произвольные дюпы этим не подтверждены.

Подготовка стенда дополнена: бедрок на дальней home-площадке не подменяется
Underground Biomes, в отличие от stone/cobblestone; координаты протокольного игрока
публикуются после отправки teleport ACK. Членство команды проверяется ответом
`/team status`, потому что уведомления FTB идут через отдельный UI-канал.
Оба завершённых стенда остановлены, временные auth-контейнеры удалены, исходный сервер
не менялся. [Результаты и хеши](validation/dj2-claim-edges-2026-10-31.json).

## Восстановление выделенной базы — 31 октября 2026

`omk lab dj2-recovery` испытал WorldEdit 6.1.10 file 2941712 на новой полной DJ2:
**71 проверка**, в том числе vanilla/Iron Chest, Thermal-печь, полный NBT/ForgeCaps,
соседи в том же чанке, undo/redo, повтор, отсутствие снимка, non-OP отказ и restart.
Восстановленная печь после restart действительно переплавляет предмет. Стенд остановлен,
временный Drasl удалён; существующий сервер/миры не менялись. Python/Qt: 234 passed,
один Windows symlink skip; Ruff/Black прошли.

Подтверждён отдельный дефект старого WorldEdit ZIP reader: в неоднозначном архиве может
выбраться Nether вместо overworld. Проба настоящего класса jar воспроизводит это без
Minecraft. Стенд сохраняет полные backup отдельно, а WorldEdit получает подготовленные
снимки **только dimension 0**; после такой подготовки проба выбирает правильный файл.
Перед применением записывается план с границами/allowlist/хешами и свежей копией.
Все внешние jar закреплены по SHA256; мод WorldEdit добавлен только в новые стенды.

[Результаты](validation/dj2-region-recovery-2026-10-31.json),
[команды](commands/dj2/RECOVERY.md), [ограничения/следующий этап](REGION_RECOVERY.md).
В базовый runtime-реестр 438 команд экспериментальный WorldEdit не включён. Каталог
расширен отдельной страницей только реально испытанного синтаксиса.

Следующий milestone — расширить восстановление на сущности, AE2/EnderIO/многоблоки,
неполные/повреждённые снимки и сбой посреди применения. Затем административный `omk`
plan/apply с проверкой версии/покрытия/границ и возвратом из свежей копии; сейчас таких
эксплуатационных команд нет. Совместимость рабочих FTB-архивов, другие измерения,
автоматическая политика резервирования и все машины DJ2 ещё не подтверждены.
CoreProtect-подобная история автора отдельно: ForgeEssentials PlayerLogger изучен
по исходникам 1.12.2, но не установлен/не испытан. Ядро остаётся авторским Forge.

## Неполные снимки и сущности — 1 ноября 2026

`omk lab dj2-recovery --edge-cases` прошёл **92 проверки** на новой полной DJ2,
включая прежние проверки, restart, переплавку и сравнение полного сохранённого NBT.
Уничтоженная стойка для брони не возвращается, новая внутри выделения остаётся;
контрольная внешняя стойка не меняется, результат сохраняется после restart.
Другие сущности не испытаны; блоковый откат не объявляется полным возвратом базы.

На двух чанках подтверждено частичное изменение при ошибке: ответ WorldEdit —
`Restored; 0 missing chunks and 1 other errors.` Лабораторный read-only preflight
отклоняет тот же неполный снимок до применения, не меняя живые блоки. Намеренный обход
guard выполнен только в новом стенде; немедленный undo вернул оба повреждённых блока.
Это не восстановление после краша. Guard ограничен dimension 0, 4096 блоками/16 чанками,
проверяет покрытие/координаты/базовую NBT-структуру, не всю семантику модов или TOCTOU.

Python/Qt: **251 passed, 1 Windows symlink skip**, фокусные recovery-тесты: 25 passed;
Ruff/Black прошли. Стенд штатно остановлен, временный Drasl удалён, его listeners/Java
отсутствуют. Исходный сервер не менялся. [Обезличенный отчёт](validation/dj2-recovery-edges-2026-11-01.json),
[команды и ограничения](commands/dj2/RECOVERY.md) обновлены.

Следующий milestone: репрезентативные модовые сети/многоблоки и безопасный возврат из
полной копии после сбоя, затем административный plan/apply с явным покрытием/ограничениями.
Рабочего apply нет; политика резервирования, ресурсный мир/граница и остальные пункты
[матрицы](GAME_TEST_MATRIX.md) остаются открытыми. Для текущих изолированных испытаний
VPS не нужен. Аренда потребуется перед публичным HTTPS/auth/CDN и внешним Forge-входом;
публичный сервер дома не запускаем.

## Полная копия в новом сервере — 1 ноября 2026

`omk lab dj2-recovery --edge-cases --full-backup-return` прошёл **111 проверок**.
После прежних сценариев старый стенд чисто остановлен и сохранён ещё один свежий backup.
Снимок до повреждения развёрнут только в пустой папке нового runtime с теми же jar;
исходный мир не заменялся/не перемещался/не удалялся и совпал по хешам после опыта.
Все **266 файлов** копии прочитаны обратно и проверены по SHA256 до запуска Forge.

Подтверждены исходные контейнеры/печь, возврат уничтоженной стойки и исчезновение новой,
инвентарь игрока, настоящий home и FTB-приват с контролями постороннего/владельца.
В установленной DJ2 `Inventory.Count` — TAG_Int (Slot остаётся TAG_Byte), что учтено
по сохранённому NBT; ванильный byte-count давал ложный отказ теста.
Стенд штатно остановлен, его Java/listeners отсутствовали после cleanup, временный Drasl
удалён. [Санитизированная запись](validation/dj2-full-world-return-2026-11-01.json).

Python/Qt: **278 passed, 1 Windows symlink skip**, 52 фокусных recovery-проверки,
включая 27 staging-проверок; Ruff/Black прошли. Проверены небезопасные пути ZIP,
метаданные ссылок, коллизии имён, лимиты, неверный хеш, CRC и сбой записи после первого
файла. Перед записью сохраняется план; при сбое нет маркера готовности и нельзя писать
поверх оставшейся папки. Лимиты 512 МиБ/20000 файлов — для маленького стенда, не production.

Это **round trip чистой world-копии в новый сервер**, а не обрыв Java посреди записи,
рабочий `omk recovery apply`, FTB Backups-архив или переключение публичного сервера.
Баны/OP/whitelist/ранги/config/Drasl находятся вне исторической world-копии; рабочий
процесс обязан сохранять актуальную политику доступа отдельно. Старые FTB-членства
в полной world-копии тоже откатываются и требуют сверки до открытия доступа.
Следующий этап — репрезентативные AE2/EnderIO сети/многоблоки; аварийный cutover,
актуальная политика доступа и остальные пункты матрицы остаются открытыми.

## Небольшие модовые системы после отката — 1 ноября 2026

`omk lab dj2-recovery --runtime linux-docker --mod-systems` прошёл **38 проверок**
на новой полной DJ2. ME-сундук AE2 с ячейкой 1k и два Activated Capacitor Bank EnderIO
проверены до повреждения, после обычного/повторного отката и после четвёртого старта.
AE2 снова принимает именованный предмет через воронку, банки снова питают Thermal-печь.
Возвращаются содержимое, энергия и лимиты; соседний сундук вне выделения сохраняет
изменения. Сохранённые NBT сверены независимо от ответов WorldEdit.

Профиль/JAR не обновлялись; эксперимент использует прежние AE2 UEL 0.56.4 и EnderIO
5.3.72, закреплённые SHA256. Старые миры не подключались. Экспорт и clean stop прошли,
собственный Linux volume и временный Drasl удалены. Startup observer не использовался.
[Сценарий, пути, источники и ограничения](MOD_SYSTEM_RECOVERY.md),
[обезличенные результаты](validation/dj2-mod-system-recovery-2026-11-01.json).

Это выделение 180 блоков, не проверка всех ME-сетей/труб и не готовый рабочий apply.
Далее — большие сети/соединения за выделением и безопасный полный возврат в Linux
после сбоя с сохранением актуальной политики доступа; затем закрытый административный
plan/apply. Ресурсный мир, эксплуатационные бэкапы и остальные пункты матрицы остаются.

## Квоты сообщества и предварительный аудит — 1 ноября 2026

Согласовано: **50 claim-чанков, 3 дома и до 3 отдельных территорий на участника**.
Команда из троих получает 150 чанков и до 9 территорий, дома остаются личными.
Шаблон FTB и строгий env-рендерер новых остановленных копий задают 50/3. Реальный
Linux Forge подтвердил все 50 claims, отказ на 51-й и увеличение бюджета после вступления
второго non-OP участника. Число территорий кодом ещё не ограничено; отдельный адаптер
должен учитывать пакетные claims, снятие мостового чанка и выход участников без удаления баз.

Приоритет до открытия: server-owned FTB-защита спавна без OP у игроков; исправление
RTP в текущем измерении с allowlist и отдельной посадкой Nether; целевые защиты
подтверждённых обходов. Штатный RTP этой версии выбирает spawn dimension: старые
тесты overworld не подтверждают новое требование. Первое приветствие пока не внедрено.
[Правила и план по измерениям](COMMUNITY_POLICY.md),
[квоты и закрытие стендов](validation/dj2-community-quota-2026-11-01.json).

Предварительный риск-аудит сохранён в `../project-analysis/security/DJ2-RISK-REVIEW-2026-11-01.md`
вне публичного репозитория. В новом Linux-стенде подтверждён перенос предметов через
границу FTB механизмом Twilight Forest; механизм создан консолью, путь выращивания
обычным игроком ещё не проверен. Активация бобов не состоялась — отсутствие ущерба
не является доказательством защиты. Доказанного предметного дюпа/краша в этих опытах
нет. Исторические upstream-ошибки отделены от локальных воспроизведений; автоматических
банов предметов/обновлений JAR нет, сохранение квестов — обязательное условие решения.

После квот: Python/Qt **464 passed, 2 Windows symlink skips**, Ruff/Black прошли.
Старый сервер и миры не менялись. GTNH, ресурсный мир, предгенерация и полный Linux
аварийный возврат остаются отдельными этапами; аренда VPS для этих локальных тестов не нужна.

## Server-owned спавн и могилы — 1 ноября 2026

Приватный Core **0.2.4** резервирует спавн через штатные FTB claims только при наличии
явной offline-политики в новом стенде. Квадрат −300…300 покрывается 1444 чанками
с фактическими краями −304…303. Принудительной загрузки/предгенерации нет.
Python создаёт policy эксклюзивно, с bounded `OMK_DJ2_SPAWN_RADIUS` (default 300);
не обновляет исходный runtime и не перезаписывает чужие claims.

`omk lab dj2-spawn` завершил **70 проверок, два старта Linux DJ2**. Внутри защищены
ломание/установка, claim/unclaim и вступление в server-team; внешние контроли работают,
TNT на границе сохраняет внутренний блок. Проверены обе оси/отрицательные координаты.
Restart подтвердил те же 1444 claims, продолжающуюся защиту и личный claim игрока.

Требование владельца к могилам подтверждено: настоящая смерть/возрождение, 17 именованных
предметов и Shift в чужом claim и на спавне. Без Shift вещи остаются, посторонний/хозяин
территории их не получает. Исключение из FTB не потребовалось — работает нативная
проверка Tomb Many Graves. Графический клиент/все слоты/locked/friends этим не проверены.

Обнаружен штатный OP служебного `[Minecraft]`: установленный PlaneFix 1.0.0 добавляет
его при каждом старте. В lab права сняты только с точного известного профиля для
контроля пустого OP-списка; все игровые аккаунты обычные. Рабочий pack не менялся.
AE2 planes и чужие claims требуют отдельной проверки, автоматически удалять PlaneFix нельзя.

Python/Qt: **478 passed, 3 Windows symlink skips**, Ruff/Black прошли. Мир экспортирован,
игра/временный Drasl штатно закрыты, собственный volume удалён. Старые данные сохранены.
[Описание/команда повторения](SPAWN_AND_GRAVES.md),
[обезличенные результаты/хеши](validation/dj2-spawn-graves-2026-11-01.json).

Далее до открытия: RTP в текущем измерении, счётчик территорий/приветствие,
проверка конфликтного bootstrap и automation/модовых обходов, ресурсный мир и безопасный
Linux аварийный возврат. Защита спавна не равна проверке всех прямых записей модов.
VPS пока не требуется; GTNH и полная предгенерация позже.

## Конфигурация перед VPS — уточнение владельца, 1 ноября 2026

До развёртывания провести отдельный аудит Compose, Dockerfile, Python/Java entrypoints
и shell-скриптов: убрать эксплуатационные значения из исходников в проверяемые env
с документированными defaults. Включить порты/адреса, число воркеров, CPU/RAM/heap,
таймауты, интервалы и бюджеты логов/бэкапов/диска. `.env.example` должен соответствовать
реально читаемым настройкам; изменение такой конфигурации не требует коммита.
Проверить некорректные значения, overrides и итоговый `docker compose config`.
Lab остаётся loopback-only и изолированным; ключи доверия/хеши артефактов не становятся
произвольными клиентскими overrides. Этот проход запланирован после текущего RTP,
до аренды/публичного запуска, и пока не объявляется выполненным.

## Выявленный краш остановки WR-CBE — 1 ноября 2026

При выходе последнего тестового игрока из Nether непосредственно перед `stop` пойман
NPE в `WREventHandler.worldTick:170`, WR-CBE 2.3.2.33. На этой ветке обработчик выгрузки
очищает Addons-manager при остановке сервера, затем START-обработчик ещё оставшегося
мира обращается к нему без null-check. Это не доказанный краш обычного перехода/RTP,
не OOM и не подтверждённый предметный дюп. Исправление самого WR-CBE **ещё не внесено**;
до открытия нужно отдельное узкое решение и повтор остановки с игроками в разных мирах.
[Факт и хеш артефакта](validation/dj2-wrcbe-shutdown-crash-2026-11-01.json).

Forge завершился с кодом **0**, поэтому прежний lab назвал завершение чистым — это
ошибка классификации. Новый Linux lifecycle дополнительно читает ограниченный журнал:
фатальный серверный маркер делает `ok=false` и `owned_game_clean_exit=false` и сохраняет
собственный volume для диагностики даже после успешного экспорта мира. Неизвестный
результат чтения тоже не доказывает clean exit. Обычные optional-integration исключения
не считаются фатальным серверным крашем. Сырые прежние отчёты не переписывались.

## RTP в текущем мире — 1 ноября 2026

Приватный Core **0.2.5** по явной offline-политике перехватывает RTP, сохраняя FTB
permission/warmup/cooldown/history. Выбор мира больше не привязан к `spawn_dimension`.
Профиль данных разрешает 0/−1/7; Nether ищется под крышей, story/unknown получают отказ.
Python валидирует env радиусов/доли границы/числа проб/загрузок/интервала повторов и
необязательный JSON-профиль оператора. Настройки создаются только в новой копии.

Новый `omk lab dj2-rtp` завершил **50 настоящих серверных проверок Linux DJ2**:
обычный мир, Nether Y66 под крышей Y127, Twilight Forest; штатные права/таймеры,
вода/неполный пол/занятые claims/малая граница, ненулевой центр, отказ без генерации
region-файлов, движение/смена мира, отключение/повторный вход. Два одновременных
RTP в разных измерениях независимы, фактические миры подтверждены сервером.
Сервер остановился без фатального маркера, мир экспортирован, собственный volume и
временный Drasl удалены. Core/JAR, аккаунты и payload в публичный Git не попали.
Python/Qt: **502 passed, 3 Windows symlink skips**, Ruff/Black прошли.
[Описание и env](DIMENSION_RTP.md), [отчёт](validation/dj2-dimension-rtp-2026-11-01.json).

Это искусственные площадки/кольцо 8…12 и протокольные игроки, не полноценный клиент,
естественная карта или измерение производительности VPS. Далее: краш остановки WR-CBE,
совместный профиль spawn/RTP, счётчик территорий/приветствие, ресурсный мир,
Linux аварийный возврат и полная проверка конфигурации Compose/Dockerfile перед VPS.
Большую предгенерацию и GTNH по-прежнему откладываем.

## WR-CBE shutdown — 2 ноября 2026

Core 0.2.6 (`f832bd77…`) использует уже установленный MixinBooter 10.6 для узкого
server START guard: только отсутствующий менеджер и остановленный сервер. JAR WR-CBE
не менялся. В свежем Linux-контроле Core 0.2.5 воспроизвёл естественный NPE через FML
world tick с exit=0 / OOM=false; журнал и volume сохранены. Исправленный публичный
CLI прошёл **67 проверок / 3 старта**, в том числе настоящее выключение/включение
передатчика с реакцией приёмника после обоих restart. Live-null не скрывается;
12 контролируемых START/END пар после disposal возвращаются штатно.

[Сценарий, хеши и ограничения](WRCBE_SHUTDOWN.md),
[сравнение исходного/исправленного поведения](validation/dj2-wrcbe-shutdown-2026-11-02.json).
Собственные штатные volumes удалены после экспорта, временные Drasl удалены;
существующие серверы/миры не подключались. Локальные unit/UI: **513 passed, 3 skips**,
Ruff/Black прошли; Core собирается с тем же SHA256, пробник не входит в runtime JAR.

Обычный RTP-стенд с Core 0.2.6 **без** диагностического мода также прошёл **50 проверок**
и чистую остановку; [отчёт](validation/dj2-rtp-core-0.2.6-2026-11-02.json).
Следующий P0 — подтверждённые модовые обходы FTB (#29), детали остаются в закрытом
аудите. Полная env-конфигурация (#30) обязательна до VPS; аренда пока не нужна.
