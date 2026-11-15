# Актуальные права на выбранной копии серверного выпуска

`omk.project_policy` продолжает [подготовку runtime + мира](PROJECT_STAGE.md).
Он использует прежний FTB adapter и общий writer из `linux_restore_policy`.
Новых CLI, env, зависимостей, writers резервного копирования и таймеров нет.

Это внутренний файловый этап #171. Даже успешная проверка оставляет
`quarantine_required=true`, `boot_allowed=false`, `ready_for_players=false`.
`current_policy_reconciled=true` означает только соответствие файлов принятой
политике; оно не разрешает lifecycle, promotion или открытие входа.

## Источники и ответственность controller

Controller держит общий owner lock, подтверждает остановку/владение источниками,
монтирует export и актуальный сервер readonly, исключительно владеет новым
target. Проверки этого API не заменяют Docker lifecycle fence. Все три корня
абсолютные, без links/пересечения; исторический target уже должен пройти raw stage.

`raw_expected` независимо сохранён до распаковки и выбирает точный project snapshot,
а не произвольный исправный архив. Актуальный источник тоже должен быть известен
controller: API не выбирает его по времени изменения или имени каталога.
Исходный архив и актуальный сервер не изменяются. Drasl/operator TAR не извлекаются,
база аккаунтов не откатывается.

Поддержан только явный `dj2-ftb54-current-v1`: JAR FTBLib 5.4.7.2 и FTBUtilities
5.4.1.131 проверяются по прежним SHA256 в обеих версиях. Совместимость остальных
модов/скриптов и сохранений по-прежнему должна быть принята до candidate boot.
Это не автоматическое разрешение запустить старый JAR на преобразованном мире.

## Что возвращается и что берётся из текущего состояния

- Выбранный архив даёт runtime, моды/скрипты/config и исторический мир, включая
  инвентарь/XP, прогресс, claims/homes и остальную карту.
- Текущий сервер даёт `ops.json`, обе ban lists, `whitelist.json`, определения
  ranks и известные FTB authority fields. В этой политике текущий OP-список
  обязан быть пустым: все игроки работают без OP, владелец использует консоль.
- FTB reconciliation сохраняет исторический прогресс, переносит известные текущие
  owner/TeamID/status/invites/fake-player/interaction rules. Применяется прежняя
  строгая модель: новый/исчезнувший игрок или команда, другой UUID/UID и неизвестные
  отличия требуют отдельного разбора, а не выдуманного слияния.
- Из текущих `server.properties` переносятся только `online-mode`, `white-list`,
  `server-ip`, `server-port`, `enable-rcon`, `rcon.port`, `rcon.password`, `pvp`,
  `difficulty`, `max-players`. Остальные свойства остаются историческими.

Свойства должны быть каноническими UTF-8 `key=value`, не более 1 MiB. Неоднозначные
ключи/разделители, duplicates, escaped keys и продолжения строк отказывают.
Оба `level-name` совпадают с выбранным world root. Текущая политика требует
online-mode/RCON, пустой server-ip, PvP/Hard; корректные разные game/RCON ports,
ограничение max-players и printable ASCII RCON secret от 16 до 1024 символов без
пробелов/backslash. Неизвестный формат не переписывается наугад.

RCON secret передаётся только в памяти и приватный `server.properties` (`0600`).
Планы/receipts хранят хеши, а не значение пароля. Нельзя печатать исходные файлы
или raw payload в журналы. Исторический пароль не становится актуальным после
возврата полного runtime.

## Внутренний API и проверка

```python
expected = project_policy.plan(
    export, target, current_server,
    raw_expected=raw_expected,
    adapter=project_policy.ADAPTER,
)
# Controller сохраняет expected до применения.
project_policy.stage(
    export, target, current_server,
    raw_expected=raw_expected, expected=expected,
)
# Новый процесс после потерянного ответа, с теми же readonly источниками:
project_policy.verify(
    export, target, current_server,
    raw_expected=raw_expected, expected=expected,
)
```

`plan` только читает: повторно проверяет raw target и полные архивы, строит
ожидаемый FTB результат, связывает текущие файлы/FTB/runtime, before/after и
будущие runtime/world inventories. Изменённый current source делает план устаревшим.

`stage` повторяет preflight и проверку свободного места с прежним reserve,
пишет/fsync `.omk-project-policy-plan.json`, подготавливает новые файлы отдельно,
проверяет их и заменяет только ожидаемые before. Все изменённые файлы — `0600`.
Проверяются полный runtime/world inventory, mode bits, исходные raw receipts,
неизменность текущего источника, точный корень target и пустое известное staging.
Только затем публикуется `.omk-project-policy-staged.json`.

Операция многофайловая и не атомарная. Обрыв до результата оставляет обе копии
и diagnostics; автоматического повтора/достройки/отката файлов нет. Нужна новая
явно выделенная область. Raw verifier отказывает после начала policy overlay,
поэтому его нельзя использовать для обхода отказа reconciliation.

После durable receipt `verify` в новом readonly процессе заново вычисляет
ожидания и сверяет весь результат. Он не ремонтирует файлы. Изменённый пароль,
JAR, мир, права, receipt, лишний root/staging entry или позднее изменение current
source даёт отказ. Полная файловая проверка не заменяет реальный boot/join/gameplay.
Защита рассчитана на сериализованного владельца и отдельные mounts, не на
враждебный процесс с тем же доступом к Docker/файловой системе.

## Проверки и следующий этап

Linux Docker: 88 focused tests (33 новых policy, 11 прежнего world-only adapter,
44 raw stage). Windows: 23 portable checks, 21 явный Linux skip для двух policy
модулей. Ruff/Black. Проверены current ban/deop/ranks/secret, старый прогресс и JAR,
FTB revoke, несовместимые identity/поля/версии, stale plan, low space, частичная
замена, потеря ответа, поздние изменения и неоднозначные properties.

На отдельной копии настоящих DJ2 payload проверены 2319 runtime +317 world files,
528012910 raw bytes. Metadata schema 2 и изменённые current policy явно
синтетические fixtures: это file consumer acceptance, не новый capture provenance.
Восемь ожидаемых файлов изменены, весь остальной выбранный состав совпал.
Действительные `os._exit(23/24)` после receipt/первой замены и новый readonly
процесс подтвердили полный результат и отказ partial/retry/raw fallback.
Исходные девять архивных файлов неизменны; свои scopes удалены.

Minecraft/Drasl/ingress не запускались, power loss не моделировался. Не закрыты
доверенный producer/journal, loopback candidate boot с обычным authenticated
join/gameplay, поздний отказ, promotion и полный application return #171.
Player manifest/Release/VPS/календарь не переключены.
[Обезличенный протокол](validation/project-policy-2026-11-15.json).
