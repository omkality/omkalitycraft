# Журнал файлового возврата полного выпуска

`omk.project_return` связывает [raw stage](PROJECT_STAGE.md) и
[актуальную политику доступа](PROJECT_POLICY.md) одной owner-операцией. Повторно
используются общий lock резервных операций, приватные JSON/fsync и оба прежних
file workers. Новых CLI/env/deps/таймеров и второго backup writer нет.

Это внутренний Linux API, не production cutover. Любой результат сохраняет
`boot_allowed=false`, `ready_for_players=false` и quarantine. Завершение файлов
не разрешает запустить контейнер или открыть вход игрокам.
Исполняется в обычном controller environment с прежними зависимостями проекта;
минимальный Python-образ cold file worker не является таким environment.

## Входные данные и доверие

Controller передаёт уже проверенную selection: отдельно сохранённые SHA256
точного `project.json` и release identity из закрытого capture/transport receipt.
Журнал не ищет «самый свежий» export, не принимает произвольный неизвестный
каталог за источник доверия и не производит Git/client-signature attestation.
Подлинность ссылок и совместимость сохранений подтверждает controller до plan.

Текущий сервер совпадает с owner allowlist. Export, target, current и приватный
журнал — четыре отдельных абсолютных корня без links/пересечения. Target новый,
приватный и пустой. Действует прежний явный DJ2/FTB adapter, включая пустой OP.
Текущая политика и все архивные bytes повторно проверяются перед записью.

Обязательный callback `checkpoint` читает реальные whitelisted Docker ownership/
lifecycle metadata: source остановлен, volumes и target принадлежат операции,
других writers/использующих mounts нет. В журнал попадает только digest metadata.
Не передавать Config.Env/Args или credentials. Совпадение digest не заменяет
содержательную проверку внутри callback; file API сам Docker не инспектирует.
Controller удерживает owner lock на всём внешнем lifecycle, обе исходные области
монтируются readonly. Защита не рассчитана на враждебный процесс с тем же доступом.

## Сохранение выбора и применение

`plan` под общим `admin_backups.locked` проверяет источники, current policy,
исходный snapshot, target и fence до/после чтения. До первого изменения target
сохраняет `project-returns/<operation>.json`: paths/server/operation, полный raw
plan с selection/limits, adapter, current/fence digests и UTC lifetime. Запись
ограничена 64 KiB; file, journal directory и private root синхронизируются.

Вместо новых настроек повторно используются `OMK_BACKUP_JOURNAL_COUNT`
(default 256, диапазон 8–1000) и `OMK_BACKUP_PLAN_TTL_SECONDS`
(default 3600, диапазон 60–86400). История не вытесняется автоматически; заполнение
или посторонние entries требуют разбора владельца. Полные byte/reserve limits
файловой подготовки остаются замороженными в raw plan.

```python
operation = project_return.plan(
    config, "dj2", export, target, current_server,
    world=world, selection=trusted_selection, settings=frozen_export_limits,
    checkpoint=checked_docker_fence,
)["operation"]
project_return.run(config, operation, checkpoint=checked_docker_fence)
# После неизвестного результата сначала inspect, а не повтор run:
project_return.verify(config, operation, checkpoint=checked_docker_fence)
```

| Фаза | Что разрешено |
|---|---|
| `planned` | `run` пишет raw intent и начинает первое копирование |
| `raw-requested` | `run` запрещён; `verify` проверяет только готовый raw receipt |
| `raw-staged` | `run` может начать ещё не запрошенный policy этап; `verify` только сверяет raw |
| `policy-requested` | `run` запрещён; `verify` принимает только полный policy receipt |
| `files-verified` | Повторное применение запрещено; доступна повторная проверка |

Перед каждым file worker журнал сохраняет requested intent. Между этапами
повторяются ownership/current/archive checks. Policy plan сохраняется до overlay.
Только после полного policy verify записывается `files-verified`; raw success
не выдаётся за законченный перенос текущих прав.

Обычное чтение status отражает сохранённую фазу и не является новой проверкой
файлов или разрешением boot. Для допуска нужен отдельный controller gate.
Просроченный plan/поворот часов назад запрещает новое применение. Inspect уже
запрошенного результата разрешён и после TTL: это не скрытая достройка.

## Обрывы и recovery

Если raw/policy worker завершил запись, но ответ потерян, новый процесс под тем же
lock проверяет durable receipt и может подтвердить только этот завершённый этап.
После raw recovery продолжение требует отдельного явного `run` и действующего TTL.
Inspect обновляет только owner journal, исходники и staged data не ремонтирует.

Частичные файлы, изменённые inputs/fence/allowlist, неверный intent или неизвестный
результат отказывают. Автоматического удаления, повторного apply, перезаписи
старого target, auth restore или возврата world-only verifier нет. Обе версии
и diagnostics сохраняются; новая попытка использует отдельную явно выделенную область.

Многофайловая запись не атомарна. Intent не делает power loss безопасным сам по
себе; нужны filesystem guarantees и отдельная приёмка внешнего lifecycle.

## Проверки и ограничения

Linux Docker: 110 focused tests, из них 22 новых journal cases. Windows: один
portable identifier check и 21 явный Linux skip. Ruff/Black. Реальные subprocesses
оборваны после raw/policy receipts и первых файлов; OS lock освобождается, но
неизвестный write не повторяется. Второй процесс исключается тем же owner lock.
Проверены stale current/fence/allowlist/intent, TTL/часы, предел записей и отказ
записи intent до входа в worker. Journal ENOSPC здесь моделируется исключением;
это не новый опыт отключения диска или питания.

Доверенный release producer/client provenance, production lifecycle integration,
ingress promotion и полный acceptance #171 остаются отдельными требованиями.
Календарь, public player manifest/Release и VPS до аудита не включаются.

## Реальная игровая репетиция

DJ2 2.23.4 / Core 0.3.8 / DJ2Fix 0.1.4, pinned Linux Java 8 Docker, persistent
Drasl и два protocol actors. Новый coherent capture каждого остановленного
состояния выполнен прежним world backup/project export; SHA точного project.json
и identity сохранены вне export до подготовки target. Это свежие capture,
не переименование прежнего schema-1 архива. Git commit — owner declaration;
клиентская ссылка — явно lab fixture, не доказательство полного player bundle.

Исторический союзник действительно меняет блок в claim. Затем отозваны его
полномочия, выставлены ban/whitelist/deop/лимит одного дома, удалён старый home,
семь изумрудов заменены одним. Journal подготавливает отдельный полный target
из исторического выпуска с текущей политикой. В настоящей игре:

- Тот же действительный Drasl session блокируется ban; явный pardon даёт вход,
  удаление из whitelist снова запрещает его.
- Старые OP-права не возвращаются; текущая квота применяется к старому home,
  семь изумрудов возвращены, `/home old` действительно перемещает игрока.
- Бывший союзник не меняет historical claim, владелец без OP меняет; внешний
  блок остаётся доступен гостю как положительный контроль.
- После успешных health/gameplay controller стенда намеренно отвергает кандидата.
  Отдельная копия pre-change current state проходит тот же journal и обычный вход:
  один изумруд, удалённый home отсутствует, ban и отсутствие OP сохранены.

Готовый file receipt не использован как production boot permit: стенд явно
запускает только свои loopback candidates и восстанавливает runtime empty dirs
`.omk/tmp`/`java-home`. Публичного ingress/promotion нет. Старый и новый JVM
не пишут в один том.

Проверка пустого OP отказала реальному current snapshot до записи target:
pinned PlaneFix добавил известный служебный Forge profile. Guard не ослаблен;
применён существующий точный `dj2_spawn_lab._check_operators` с явным console deop,
после чего снят новый current snapshot. Это процедура isolated fixture, не
автоматическая очистка неизвестных production operators. Финальный boot gate
должен отдельно принять такую политику до допуска игроков.

34 native conditions и 20 независимых readonly Linux NBT/journal checks:
inventory 7→1→7→1, homes old→none→old→none, текущая FTB authority в обеих
сохранённых копиях и три завершённых журнала. Отдельный nonroot reader сверил
все 344 current world files и 2320 runtime files/modes с сохранённым capture:
источник не изменён. Предварительные ошибки orchestration fixture сохранены
отдельно; SIGTERM-stop одного такого fallback не объявлен clean acceptance.
Финальный fallback на новом target завершился штатным stop 0 без OOM/fatal.
Свои scopes удалены после сохранения закрытых архивов/diagnostics; оригинальные
миры и VPS не использовались.

Это не графический клиент, не отказ питания, не новая версия модов или миграция
save format. Автоматический producer/client provenance, внешний owner lifecycle/
ingress и все варианты несовместимых данных остаются в #171.
[Обезличенный протокол](validation/project-return-2026-11-15.json).

## Связка с реальным клиентским выпуском — 15 ноября 2026

После checked capture #205 проверена связка его настоящего schema-2 экспорта,
`project_stage` и `project_return`. Положительный client ref теперь реальный:
windows-x64 2.23.4-omk.3-rc.1, `4ea6af7a476e1bed67d75a95e3bcdbf19ba4c35e18fb995b0fff6af762c63a31`.
ReleaseStore проверил подпись и все 5971 файлов/759730113 байт до и после опыта.
Это private lab trust, не активация production signer или player manifest.

В отдельных Linux Docker volumes сначала подготовлена current file copy того же
закрытого снимка, затем отдельный новый target прошёл raw/current-policy journal.
Другой процесс подтвердил завершённые receipts. Callback читает фактические
labels, immutable image и mount/RW metadata, исключает других пользователей volumes;
это fence копий файлов, не имитация остановленного production game container.
Подмена выбранного client ref отказала до journal/target data. Восемь условий
стенда прошли; исходные девять архивов остались прежними, свои scopes удалены.

17 независимых readonly Linux checks перечитали все 2629 game files (2320 runtime,
309 world), runtime modes и шесть объявленных policy files, journal intent,
точную selection, PvP/Hard/пустой OP и сохранённый NBT трёх алмазов. Все 34 пары
регистра и Linux-файл `con.dat` сохранены внутри TAR; auth/operator payload не
извлекался в game. Полный policy receipt и пустая разрешённая структура attempt
marker проверены: marker не удаляется автоматически и не означает незавершённость
при наличии принятого receipt.

Первый collector ошибочно попробовал directory Docker cp на Windows и отказал
на CON filename; его failed report сохранён, новая попытка использовала свежие
тома и Linux TAR. Первый reader неверно ожидал отсутствия сохранённого marker;
исправлена только проверка, API/guards прежние. Эти ошибки не скрыты.

Игра/auth здесь не запускались. Current — копия того же закрытого снимка;
это не новый historical/current authority или authenticated gameplay опыт.
Boot/ready по-прежнему false. Внешний controller/lifecycle/ingress/post-boot policy
и несовместимые данные #171 остаются открытыми.
[Протокол и границы](validation/project-current-client-return-2026-11-15.json).
