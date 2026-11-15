# Комплект одного остановленного проекта

Внутренний Linux-сборщик `omk.project_export` объединяет данные одного закрытого
сервера в новый приватный каталог. Он использует существующий verified cold ZIP
мира и читает фактические остановленные источники. Новых команд `omk`, расписания,
stop/start или второго writer живого мира нет. Подключение к nightly остаётся #33.

## Состав

| Файлы | Источник и проверка |
| --- | --- |
| `world.zip`, `world.json` | Готовый managed cold backup. Его inventory обязан совпасть с текущим остановленным миром; полный ZIP/CRC/SHA проверяется до копирования |
| `runtime.tar`, `runtime.json` | Фактический game root без настроенного world, logs, crash-reports и backups. Сохраняются файлы конфигурации, моды, библиотеки, bootstrap и обычные executable bits |
| `auth.tar`, `auth.json` | Весь остановленный state Drasl, включая возможные WAL/SHM и ключ подписи. SQLite проверяется в новой временной копии; source остаётся readonly |
| `operator.tar`, `operator.json` | Явно выбранные файлы владельца: конфигурация, credentials и journals. Обязательны `operator.toml` и `drasl.toml`; последний сверяется с хешем фактически подключённой конфигурации Drasl |
| `project.json` | Общий scope, обе stopped identities, время и полный набор размеров/SHA компонентов. Создаётся последним после проверок |

Готовый комплект содержит ровно девять файлов. Отсутствие manifest или лишний
файл означает отказ `verify`; такой каталог нельзя передавать как project backup.
`quarantine_required=true` и `ready_for_players=false` сохраняются всегда.

Выбор operator files принадлежит профилю владельца. Нужно включить все используемые
credential files и описание развёртывания, не только TOML. История journals тоже
принадлежит operator state. Папки offsite/exports/staging не принимаются как его
вход: transport encryption/repository credentials хранятся отдельно. Recovery key
необходимо также сохранить вне VPS и зашифрованного репозитория. Параметры
Compose/env, исходный Git revision и доступность pinned images проверяются при
будущем полном восстановлении; OCI layers этот сборщик не архивирует.

Готовые TAR/ZIP содержат секреты, базы и payload сборки. Они остаются вне Git,
GitHub Releases и диагностики игроков. Каталог создаётся mode 700, внешние файлы
mode 600. Файлы внутри auth/operator TAR нормализуются до 600; runtime сохраняет
обычные mode bits, без setuid/setgid. Извлекать серверный runtime следует на Linux.

## Контракт владельца

Вызывающий controller держит существующий общий owner lock и независимо проверяет
allowlist, labels и соответствие источников реально подключённым volumes/config.
Все входные источники должны быть обычными отдельными путями; output не может
находиться внутри них или включать их в себя. Не использовать этот API для
резервирования работающего Minecraft/SQLite.

`checkpoint()` вызывается до чтения и перед публикацией. Он возвращает `game`
и `auth`: container ID, image ID, volume, StartedAt/FinishedAt, running/restarting,
exit code и OOM. Для auth также нужен `config_sha256`. Оба сервиса должны быть
остановлены чисто, без OOM; identities/время запусков/конфиг должны остаться прежними.
Перезапуск даже того же контейнера внутри окна отказывает. Это не защита от
владельца, который подделывает checkpoints или меняет файлы вне общего lock.

`capture(destination, ..., checkpoint=..., settings=...)`:

1. Проверяет roots, scope, stopped checkpoints, готовый world ZIP и inventories.
2. Рассчитывает место с запасом до первой записи, затем создаёт только новый output.
3. Копирует готовый мир, пишет и полностью перечитывает TAR компонентов, проверяет
   SQLite в отдельной временной папке, повторно сверяет source inventories.
4. Сравнивает новые lifecycle checkpoints; после этого пишет/fsync manifest и
   каталог. Незавершённая папка остаётся для осмотра, автоматически не принимается.

`verify(directory, settings)` проверяет точный верхний набор, размеры и SHA,
формат декларации закрытых источников и возвращает frozen export для транспорта.
Он не доказывает задним числом прошлый clean stop и не запускает восстановленные
службы. В accepted transport lab дополнительно перечитаны внутренние архивы.
Для полного return потребуются отдельная проверка/extraction и карантин.

## Привязка серверного выпуска

Необязательный `release_context` в `capture` создаёт **schema 2** того же
`project.json`. Число файлов остаётся девять, дополнительные архивы/команды/
writers не добавляются. Без аргумента создаётся прежняя schema 1.

Владелец передаёт проверенные до вызова сведения:

- `source_commit`: полный 40-символьный Git commit, без изменяемого имени ветки;
- `client_manifests`: SHA256 подписанных клиентских манифестов по платформам;
- `declared_state_contract`: короткий идентификатор объявленного контракта
  сохранений, например `dj2-2.23.4-world-v1`.

Сборщик сам дополняет `release_identity` digest фактически остановленного
game image и SHA256 созданных `runtime.tar`/`runtime.json`. Хеши отдельных модов,
скриптов и конфигурации уже находятся в этом runtime inventory: второй список
не создаётся. Данные отделяются от изменяемого входного объекта контроллера.

`verify(..., expected_release_identity=selected_identity)` требует точного
совпадения **заранее сохранённой** полной identity. Подмена image/runtime,
изменённые клиентские ссылки/commit/контракт, удаление identity или понижение
schema дают отказ. Если вместо runtime подставить другую исправную TAR/JSON-пару
и пересчитать обычные верхние хеши, выбор прежнего выпуска всё равно откажет.
Обычный transport signature покрывает также сам `project.json`.

Нельзя получать ожидаемую identity из того же подозрительного каталога прямо
перед проверкой. Она принадлежит доверенному плану/записи выбранного выпуска;
receipt и ожидаемый signature всего экспорта также проверяются существующим
транспортным путём. Старый комплект schema 1 по-прежнему читается как резервная
копия, но не принимается за выбранный schema-2 выпуск. Его исходные байты не
переписываются для приписывания отсутствующего происхождения. Старый читатель,
поддерживающий только schema 1, откажет на schema 2; обновление читающей стороны
требует явной проверки, автоматического понижения формата нет.

Это **запись и проверка связей**, не доказательство происхождения кода:
функция не обращается к Git, не проверяет подпись по одному digest клиента и
не доказывает совместимость мира по строке `declared_state_contract`. Эти
сведения проверяет вызывающий код до capture и перед будущим promotion.
Полный серверный возврат, журнал/классификация изменений и native failure/boot
приёмка остаются в #171. `ready_for_players=false` и `quarantine_required=true`
сохраняются при успешном выборе. Auth-архив не восстанавливается автоматически;
обычный возврат контента не должен оживлять отозванные доступы или прежние пароли.

Следующий отдельный участок — [подготовка runtime + мира](PROJECT_STAGE.md)
по заранее сохранённым identity и SHA256 точного `project.json`. Это файловый
stage в новый target; он сохраняет запрет boot до current-policy и игровой приёмки.

В Linux Docker проверены создание/чтение обоих форматов, выбор/отказ и сохранность
компонентов на синтетических файловых fixtures. Отдельно новый reader перечитал
реальный сохранённый DJ2-export schema 1: девять файлов, runtime TAR 516014080
байт. Вход остался readonly/побайтно прежним; нет распаковки и запуска игры/auth.
[Протокол и ограничения](validation/project-release-binding-2026-11-15.json).

## Регистр путей на Linux

Настоящая DJ2 после запуска содержит 34 пары имён, которые отличаются регистром:
например, `config/DivineRPG/...` и `config/divinerpg/...`. Обе версии должны попасть
в runtime. TAR-компоненты включают явный `case_sensitive=True` только с политикой
`linux-server`. Прежние portable guards и поведение world ZIP не ослаблены.
Точные дубликаты, ссылки, конфликт file/directory, unsafe paths и размеры по-прежнему
отказывают. Это общий файловый режим, не ветка с логикой DJ2.

## Бюджеты

| Переменная | Default | Максимум |
| --- | --- | --- |
| `OMK_PROJECT_EXPORT_MAX_BYTES` | 16 GiB | 1 TiB суммарного output |
| `OMK_PROJECT_EXPORT_WORLD_BYTES` | 16 GiB | 1 TiB распакованного мира |
| `OMK_PROJECT_EXPORT_RUNTIME_BYTES` | 8 GiB | 1 TiB runtime |
| `OMK_PROJECT_EXPORT_AUTH_BYTES` | 128 MiB | 128 MiB, текущий проверенный offline Drasl helper |
| `OMK_PROJECT_EXPORT_OPERATOR_BYTES` | 64 MiB | 1 GiB operator files |

Все значения — положительные десятичные байты. Общий free reserve берётся из
storage policy. Оценка учитывает TAR/manifest overhead и временную проверку auth;
это preflight, не filesystem quota. Существуют также reviewed file/manifest bounds
общего archive helper. При отказе output автоматически не удаляется.

Суммарные ready export, restore staging, transport scratch и история ещё должны
быть связаны с общим allocator/retention существующего nightly. Одного per-export
лимита для бюджета VPS недостаточно. Автоматическое расписание экспорта этим
изменением не включается. [Переменные транспорта](../deploy/offsite.example.env).

## Проверено 13 ноября 2026

Свежая изолированная DJ2 2.23.4/Core 0.3.6/Fix 0.1.4 и постоянный Drasl
4.0.0-omk.2: два protocol actors вошли, получили разные вещи/XP; затем игра/auth
чисто остановлены. Existing cold writer создал один world snapshot. После исправления
case policy те же закрытые источники успешно дали комплект. Реальный restart
Drasl внутри повторного capture оставил второй каталог без `project.json`.

Тот же комплект прошёл настоящий REST/TLS/restic: процесс завершён exit 73 после
upload до ACK, новый процесс восстановил тот же snapshot, второй upload отсутствует,
полное хранилище перечитано. Отдельный Linux verifier без business readers сверил
9 верхних файлов, 2319 runtime/5 auth/15 operator files (514517369 байт TAR payload),
ZIP CRC 317 entries, все 34 case-пары, фактический runtime source, SQLite и ключ
подписи, связи двух player UUID с аккаунтами. Вещи/XP двух игроков в восстановленном
ZIP дополнительно проверены существующим NBT reader. В этом источнике не было
skin/cape files; новое покрытие текстур здесь не заявляется.

28 новых cases: полный Windows unit/UI 2060 passed /93 skipped, focused Linux
Docker 655. Capture — 2 CPU/1 GiB/no network, transport — 1 CPU/1 GiB, REST server
1 CPU/128 MiB/internal network; independent verifier 1 CPU/512 MiB/no network.
После выгрузки данных свои контейнеры/volumes/network удалены, чужие проекты
не затронуты. У игры/auth clean exit 0, crash/OOM не было. Это не GUI-тест,
не проверка полной нагрузки 20 игроков и не тест отключения питания хоста.

Первый fixture неверно ожидал поле receipt вместо result; второй выявил настоящий
case collision. Ошибочные исходные reports сохранены. Independent verifier сначала
сопоставлял player UUID с users.uuid; исправлен join players→users. Suite Windows
один раз прошёл при изменявшихся source files, stability guard его не принял;
затем выполнен полный свежий стабильный проход. [Протокол](validation/project-export-2026-11-13.json).

Далее #33: durable capture/lifecycle и общий бюджет в одном nightly, внешнее
destination/retention, полноценный boot/cutover в карантине и актуальные права/
отозванные доступы. До VPS остаётся аудит владельца; лаунчер/owned JAR не изменены.
