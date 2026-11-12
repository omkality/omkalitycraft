# Команды, ограничения и роли OmkalityCraft

Состояние на **2 ноября 2026**, этап `0.3.0.dev8`. Это рабочий справочник владельца.
Публичных игровых серверов пока нет. Значения ниже относятся к новой лабораторной
конфигурации; старые списки игроков, ранги и миры не импортировались.

Решение владельца от 9 ноября: игровых аккаунтов с OP и игровых администраторов
не будет, включая аккаунт владельца. Администрирование — через консоль и закрытые
owner-операции `omk`. Наличие команд в реестре ниже не означает выдачу этих прав
игрокам. Rust TUI для владельца рассматривается позже, сейчас не реализуется.

6 ноября (dev12) добавлена воспроизводимая owner-команда `omk lab dj2-mcp` ниже.
Позже в тот же день принята DJ2-операция `omk admin recover-account`:
78 native условий / 8 независимых проверок на постоянном auth volume; команды владельца добавлены ниже.
Снимок полного игрового реестра остаётся датированным своей исходной проверкой;
добавление лабораторного CLI не переаттестует все 438 игровых команд.

11 ноября добавлено owner-only окно `maintenance`: остановка → существующий
backup → возврат того же Docker-контейнера и `reconcile` после прерывания.
34 native / 60 независимых условий полной DJ2; подробности и команды ниже.

## Где смотреть

| Раздел | Содержимое |
| --- | --- |
| [DJ2: команды и настройка ролей](dj2/README.md) | Приваты, home/spawn/warp/RTP, роли, модерация, таймеры, права и недостающий функционал |
| [Полный серверный реестр DJ2](dj2/REGISTRY.md) | **438 команд/подкоманд**, алиасы, синтаксис, уровни OP, permission nodes; остальные моды сборки тоже включены |
| [DJ2: метаданные](dj2/registry.json) | Машиночитаемый снимок для поиска, генерации документации и будущего гайда |
| [DJ2: воспроизведение проверок](dj2/TESTING.md) | Полный Forge-стенд, короткие таймеры, изоляция, опасные точки RTP и модерация |
| [GTNH: предварительная справка](gtnh/README.md) | Проверенные по upstream особенности ServerUtilities; установленный игровой профиль ещё не выбран |
| [Матрица проверок](../GAME_TEST_MATRIX.md) | Какие действия реально проверены, какие ещё предстоят |
| [Команды восстановления DJ2](dj2/RECOVERY.md) | Отдельный Forge/WorldEdit-стенд: выделение, snapshots, undo/redo; ограничения и подготовка измерения |
| [Откат выделенной базы](../REGION_RECOVERY.md) | Требования, результаты испытаний и оставшиеся проверки; рабочего `omk recovery apply` пока нет |

В полном реестре нет пропусков среди полученных 438 записей сервера: 270 корневых и
168 обнаруженных подкоманд Forge CommandTree. Алиасы сгруппированы. Подкоманды, которые
мод разбирает внутри своего `execute`, представлены синтаксисом корня. Клиентские команды,
клавиши и GUI требуют отдельного клиентского каталога и не являются серверными правами.

**Зарегистрирована** не означает **протестирована во всех сценариях**. Runtime-реестр
получен из работающего Forge. Серверные тесты покрывают авторизацию, базовые claims,
дома, таймеры телепортации, TPA/back, перезапуск и отдельную non-OP модерацию.
Они также обнаружили ограничения. RTP включён с принятой владельцем особенностью магмы;
полная проверка всех приватных механик ещё продолжается.

## Общие функции и различия сборок

| Функция | DJ2 1.12.2 сейчас | GTNH 1.7.10 |
| --- | --- | --- |
| Приваты/команды игроков | FTB Utilities 5.4.1.131 + FTB Library 5.4.7.2 | Планируется ServerUtilities; точная версия ещё не закреплена |
| Home, spawn, warp, tpa, back, RTP | Таймеры/команды проверены на Forge; RTP включён с известной особенностью магмы | В upstream есть аналогичные группы; на нашем GTNH ещё не проверены |
| Ранговые лимиты | `ftbutilities.*` | Upstream использует `serverutilities.*`; копировать DJ2-конфиг целиком нельзя |
| Роли/командные права | `local/ftbutilities/ranks.txt`, `command.*` | Upstream: `serverutilities/server/ranks.txt`; точные nodes сверить после запуска |
| Резервные копии | Отдельный FTB Backups 1.1.0.1 | Upstream ServerUtilities включает собственные backup-команды |
| Граница мира | Зарегистрирован Minecraft `/worldborder`; лимит ещё не утверждён | Нужна отдельная проверка выбранного решения для 1.7.10 |
| Публичные warp игроков с владельцем и лимитом | Пока нет: штатный `/setwarp` глобальный, админский | В изученном upstream `/setwarp` тоже глобальный/OP; игровой профиль ещё не готов |
| Ресурсный мир и безопасный вайп | `/resource` проверен на новом JED/FTB-стенде; owner-wipe и рабочий профиль ещё не готовы. [Состояние](../RESOURCE_WORLD.md) | Не объявляем готовыми |
| Локальные откаты построек | Отдельные WorldEdit-проверки; полный рабочий процесс восстановления ещё не принят | Не объявляем готовыми |

Общие абстракции нужны для правил: число домов, лимит приватных/загружаемых чанков,
задержка/кулдаун, права модерации. Конкретные команды и keys остаются в адаптере сборки.
Единого игрового `/omk` пока нет; консольный `omk` ниже — инструмент разработки.

## Что можно выбирать для будущих ролей

| Возможность | Что уже умеют моды | Что ещё нужно решить/проверить |
| --- | --- | --- |
| Количество домов | Числовой лимит на ранг, в DJ2 проверено 3 | Одинаковый базовый лимит для всех и возможные будущие дополнительные роли |
| Размер привата | Лимит чанков на команду с учётом её участников | Начальное число чанков, команды/союзники, политика ресурсных измерений |
| Постоянно загружаемые чанки | Отдельный лимит и право загрузки офлайн | Влияние на TPS; это отдельный ресурс, не то же самое, что площадь привата |
| Телепортации | Раздельные warmup и cooldown для home/spawn/warp/tpa/back/rtp | Значения и отмена при движении/уроне; поведение при перезапуске |
| Public warp | Общие админские точки уже есть | Владение, лимиты, запрет перезаписи/удаления чужих точек потребуют дополнения |
| Модерация | Ban/kick Minecraft, mute/unmute FTB | Отдельный `moderator` без OP настроен и проверен; для полного мута нужен приватный Core 0.2.2 или новее |
| Цвет/значок/ник | Есть отдельные косметические права | Ник в чате не меняет UUID/учётную запись; антиимперсонацию всё равно проверяем |

Стример может играть обычным аккаунтом с теми же условиями. Статус владельца проекта
сам по себе не должен означать OP в Minecraft. Готовый профиль пока задаёт `player`
и fallback для OP, а также вручную назначаемый `moderator` с шестью точечными правами.
Платных ролей нет. Для полного мута vanilla-команд нужен проверенный приватный Core 0.2.2;
штатный FTB сам по себе пропускает `/me` и личные сообщения.

## Команды разработки — выполняются в терминале, не в Minecraft

| Команда | Назначение |
| --- | --- |
| `uv run omk --help` | Все группы команд CLI |
| `uv run omk lab dj2-mcp --help` | Свежий Windows-клиент с MCMCP, Linux DJ2/Drasl, повторный запуск клиента и очистка своих scope. Два client starts прошли; [входы, управление и ограничения](../MINECRAFT_MCP.md) |
| `uv run omk lab pack-install --help` | Новые собственные копии двух подписанных клиентов: HTTP-обрыв, докачка, repair, сохранность настроек. 22 условия на полной DJ2 прошли; [аргументы и границы](../SIGNED_PACK_INSTALL.md) |
| `uv run omk lab pack-install --hard-kill …` | Принудительное завершение собственного процесса установки и докачка новым процессом; 15 условий на полной DJ2. Не потеря питания, не существующие instances; [границы](../SIGNED_PACK_INSTALL.md) |
| `uv run omk admin --config .omk-admin/operator.toml access revoke-invite --invitation-file <файл>` | Отозвать один неиспользованный код регистрации. Drasl отклоняет этот код; другие приглашения и аккаунты сохраняются. Не блокировка уже зарегистрированного игрока; [инструкция](../ADMIN.md) |
| `uv run omk admin --help` | Закрытая утилита владельца: серверная диагностика, клиентские отчёты, приглашения; [инструкция](../ADMIN.md) |
| `uv run omk admin --config .omk-admin/operator.toml recover-account plan --username PlayerName` | Проверить существующий аккаунт, игровые UUID и все настроенные серверы; создать приватный план без изменения аккаунта. [Настройка](../ACCOUNT_RECOVERY.md#утилита-владельца) |
| `uv run omk admin --config .omk-admin/operator.toml recover-account run --account ACCOUNT_UUID` | Сброс с отзывом токенов и активных/незавершённых подключений; один новый пароль в приватном терминале. Требуются Drasl admin и Core 0.2.10/RCON-only адаптер каждого сервера. Это account UUID из плана, не игровой UUID. |
| `uv run omk admin --config .omk-admin/operator.toml recover-account status --account ACCOUNT_UUID` | Прочитать приватный journal этапов без пароля; не считать потерянный ответ доказательством lock/unlock. |
| `uv run omk admin --config .omk-admin/operator.toml recover-account resume --account ACCOUNT_UUID` | Явно продолжить проверенную незавершённую операцию с новой сменой секрета; успешную операцию повторять нельзя. |
| `uv run omk admin --config .omk-admin/operator.toml storage inspect --server dj2` | Read-only учёт active/retained/logs/pack backups, managed store и настроенных reset/restore volumes; общий filesystem reserve без повторного сложения. Ничего не удаляет. [Настройки и границы](../OWNER_STORAGE.md) |
| `uv run omk admin --config .omk-admin/operator.toml storage estate` | Общий учёт всех настроенных серверов и явных auth/content/reports/exports volumes, проектные бюджеты и reserve, неизвестный занятый объём и сопоставление заявленных per-server caps. Без записи/очистки. [Реестр и расчёт](../PROJECT_STORAGE.md) |
| `uv run python -m omk admin --config .omk-admin/operator.toml nightly preview` | Календарь ближайшего ночного окна и предупреждений из env, без Docker/рассылки/restart. Пропускает опоздавшее окно и несуществующее DST-время; повторяющееся время использует один раз. [Настройки](../NIGHTLY_BACKUPS.md) |
| `uv run python -m omk admin --config .omk-admin/operator.toml nightly inspect --server dj2` | Read-only проверка закреплённого FTB JAR, отключённых enabled/shutdown на диске и неизменности runtime/контейнера/томов. Не подтверждает настройки в памяти или отсутствие чужих jobs, не разрешает включение расписания. [Allowlist и границы](../NIGHTLY_BACKUPS.md) |
| `uv run omk admin --config .omk-admin/operator.toml ingress prepare --server dj2` | Создать приватный закрытый HAProxy template; контейнер не создаёт. [Подготовка и env](../OWNER_INGRESS.md) |
| `uv run omk admin --config .omk-admin/operator.toml ingress inspect --server dj2` | Текущие closed/TCP sessions и immutable fingerprint; loopback only |
| `uv run omk admin --config .omk-admin/operator.toml ingress plan --server dj2 --state closed` | План закрытия входа; для открытия `--state open`, только после готовности source и завершения pending операций |
| `uv run omk admin --config .omk-admin/operator.toml ingress apply --operation I` | Одна фиксированная enable/disable команда после durable intent; повтор запрещён |
| `uv run omk admin --config .omk-admin/operator.toml ingress status --operation I` | Только сохранённая сводка, без Docker; не непрерывный мониторинг |
| `uv run omk admin --config .omk-admin/operator.toml ingress verify --operation I` | Подтвердить факты после потерянного ответа без повторной записи |
| `uv run omk admin --config .omk-admin/operator.toml ingress cancel --operation I` | Отменить незавершённый intent только при проверенном закрытом входе; не открывает сервер |
| `uv run omk admin --config .omk-admin/operator.toml maintenance plan --server dj2` | План обслуживания запущенного owned Docker-контейнера, точный loopback RCON binding и runtime hash. [Порядок и границы](../OWNER_MAINTENANCE.md) |
| `uv run omk admin --config .omk-admin/operator.toml maintenance stop --operation M` | Штатная `stop`, durable intent, ожидание exit 0 и чистого stop log; без force kill |
| `uv run omk admin --config .omk-admin/operator.toml maintenance start --operation M --backup-operation B` | Только тот же immutable container ID после завершённой копии этой остановки; readonly повторная проверка данных/архива и стабильной готовности |
| `uv run omk admin --config .omk-admin/operator.toml maintenance status --operation M` | Приватный stage без паролей и содержимого Docker Env/Args |
| `uv run omk admin --config .omk-admin/operator.toml maintenance reconcile --operation M` | Подтвердить уже выполненный stop/start после прерывания утилиты, без повторной отправки lifecycle-команды |
| `uv run omk admin --config .omk-admin/operator.toml maintenance cancel --operation M` | Закрыть неизменённый `planned`/`stopped`; остановленный сервер остаётся выключенным |
| `uv run omk admin --config .omk-admin/operator.toml backups plan --server dj2` | Приватный план копии остановленного Docker-мира: image/container/volumes, inventory/runtime hash и env-политика. [Настройка](../COLD_BACKUPS.md) |
| `uv run omk admin --config .omk-admin/operator.toml resource-resets inspect --server dj2 --dimension -18000` | Read-only сводка player/FTB/JED ссылок ресурсного мира в остановленном Linux Docker volume. [Настройка и границы проверки](../RESOURCE_RESET_INSPECTION.md). Сброс не выполняет. |
| `uv run omk admin --config .omk-admin/operator.toml resource-resets inspect --server dj2 --dimension -18000 --preflight` | Дополнительно: консервативная точка около защищённого спавна, сохранённые NBT-ссылки модов и ID RFTools. [Лимиты и неполное покрытие](../RESOURCE_RESET_PREFLIGHT.md). Только владелец, read-only, без wipe/отвязки. |
| `uv run omk admin --config .omk-admin/operator.toml resource-resets plan --server dj2 --dimension -18000 --maintenance-operation M --backup-operation B` | Заморозить план отдельного пустого target, остановленного окна и его завершённого backup. [Настройка и границы](../OWNER_RESOURCE_STAGING.md). Исходник read-only, запуска/переключения нет. |
| `uv run omk admin --config .omk-admin/operator.toml resource-resets stage --operation R` | Один раз подготовить data-only копию без старого ресурса, его известных ссылок, homes/claims; игроки ресурса сохраняются у проверенной высадки. Исходный сервер остаётся выключенным. |
| `uv run omk admin --config .omk-admin/operator.toml resource-resets verify --operation R` | Read-only полная сверка receipt и файлов, в том числе после потери ответа. Частичный target не принимается; повторное извлечение не выполняется. |
| `uv run omk admin --config .omk-admin/operator.toml resource-resets status --operation R` | Приватная сводка состояния/плана без raw NBT и credentials; `ready_for_start=false`, `ready_for_players=false`. |
| `uv run omk admin --config .omk-admin/operator.toml resource-resets list --server dj2` | Найти operation ID и состояния после потери вывода CLI; Docker для чтения истории не нужен. |
| `uv run omk admin --config .omk-admin/operator.toml resource-resets abandon --operation R` | Явно отказаться от кандидата, сохранив его файлы. Только после этого снимается барьер `maintenance start/cancel` исходного окна. Не запускает сервер. |
| `uv run omk admin --config .omk-admin/operator.toml resource-resets runtime-plan --operation R` | После data stage зафиксировать точный runtime, текущие списки доступа и EULA остановленного источника; общий бюджет мира и окружения. [Порядок и пределы](../OWNER_RESOURCE_STAGING.md#проверенная-копия-серверного-окружения) |
| `uv run omk admin --config .omk-admin/operator.toml resource-resets runtime-stage --operation R` | Один раз скопировать известные JAR/config/права вокруг кандидата, сохранив мир побайтно. Не создаёт и не запускает игровой контейнер. |
| `uv run omk admin --config .omk-admin/operator.toml resource-resets runtime-verify --operation R` | Read-only сверка всех runtime/world-файлов и полного receipt, включая восстановление потерянного ответа. Не разрешение cutover; повторять частичную запись нельзя. |
| `uv run omk admin --config .omk-admin/operator.toml resource-resets slot-plan --operation R` | После `runtime-ready` заморозить reviewed Forge template, public Drasl metadata, owned bridge и loopback-порты. Возвращает новый ID `S`. [Настройка и пределы](../OWNER_CANDIDATE_SLOTS.md). |
| `uv run omk admin --config .omk-admin/operator.toml resource-resets slot-create --operation S` | Один раз создать отдельный контейнер без запуска, сверить immutable ID, sandbox и полный readonly runtime proof. Исходный сервер остаётся выключенным. |
| `uv run omk admin --config .omk-admin/operator.toml resource-resets slot-start --operation S` | Один раз запустить созданную копию; подтвердить текущий boot `Done`/Core и стабильное окно. Только loopback, без public cutover и `ready_for_players`. |
| `uv run omk admin --config .omk-admin/operator.toml resource-resets slot-status --operation S` | Сохранённая приватная сводка без credentials/Env/Args; успешная readiness не означает непрерывный мониторинг. |
| `uv run omk admin --config .omk-admin/operator.toml resource-resets slot-stop --operation S` | Штатная RCON-остановка копии и clean Docker checkpoint; без force kill. |
| `uv run omk admin --config .omk-admin/operator.toml resource-resets slot-reconcile --operation S` | Подтвердить результат прерванного create/start/stop/release по фактам, не отправляя lifecycle-команду повторно. |
| `uv run omk admin --config .omk-admin/operator.toml resource-resets slot-release --operation S` | После clean stop либо до первого запуска удержать bounded private log и удалить только контейнер, сохранив volume. Затем разрешён `abandon R`, после него — возврат исходника. |
| `uv run omk admin --config .omk-admin/operator.toml world-cutovers plan --resource-operation R` | План установки sealed мира в тот же остановленный source; backup, закрытый вход и ноль соединений обязательны. [Порядок и восстановление](../OWNER_WORLD_CUTOVERS.md) |
| `uv run omk admin --config .omk-admin/operator.toml world-cutovers apply --operation C` | Одна копия нового мира и два fsynced перемещения; прежний мир сохраняется, Forge не запускается. |
| `uv run omk admin --config .omk-admin/operator.toml world-cutovers status --operation C` | Сохранённый этап без Docker; не проверка текущей готовности. |
| `uv run omk admin --config .omk-admin/operator.toml world-cutovers verify --operation C` | Read-only полная сверка после прерывания и отзыв старой попытки записи; повторного копирования нет. |
| `uv run omk admin --config .omk-admin/operator.toml world-cutovers recover --operation C` | Явно завершить оставшиеся перемещения полных проверенных поколений. Частичную копию не достраивает. |
| `uv run omk admin --config .omk-admin/operator.toml world-cutovers revert --operation C` | Вернуть прежний мир только до первого start; новый мир сохраняется в `rejected`. После boot отклоняется. |
| `uv run omk admin --config .omk-admin/operator.toml world-cutovers cancel --operation C` | Отменить попытку только при нетронутом прежнем мире и отсутствии перемещений; частичные файлы сохраняются. |
| `uv run omk admin --config .omk-admin/operator.toml world-cutovers commit --operation C` | После `maintenance start M --backup-operation B` подтвердить установленный мир двумя журналами. Повтор после обрыва не меняет world; вход открывается отдельно. |
| `uv run omk admin --config .omk-admin/operator.toml backups run --operation ID` | Подготовить и проверить world ZIP, повторно сверить lifecycle, опубликовать новую копию до ротации старых. Контейнер остаётся остановленным. |
| `uv run omk admin --config .omk-admin/operator.toml backups status --operation ID` | Прочитать journal с проверкой схемы/identity; не содержит исходных runtime credentials. |
| `uv run omk admin --config .omk-admin/operator.toml backups list --server dj2` | Проверенная история snapshots и признак незавершённого staging, не список миров для игроков. |
| `uv run omk admin --config .omk-admin/operator.toml backups finish --operation ID` | Явно подтвердить уже опубликованную копию после обрыва без перепубликации/повторной ротации. |
| `uv run omk admin --config .omk-admin/operator.toml backups cancel --operation ID` | Отменить только неопубликованный staging при неизменной истории и отсутствии работающего helper; подтверждённые snapshots/source не удаляются. |
| `uv run omk admin --config .omk-admin/operator.toml restores plan --server dj2 --snapshot SNAPSHOT_ID` | Readonly план отдельного Linux target; требует свежий backup текущего мира и совместимый runtime. [Настройка/ограничения](../OWNER_RESTORES.md) |
| `uv run omk admin --config .omk-admin/operator.toml restores apply --operation ID` | Один раз подготовить historical world с текущими правами в отдельном volume; сервис не запускается/не переключается. |
| `uv run omk admin --config .omk-admin/operator.toml restores verify --operation ID` | Заново проверить полный результат; подтвердить завершённую запись после потери acknowledgement. Частичный target не принимается. |
| `uv run omk admin --config .omk-admin/operator.toml restores status --operation ID` | Приватный журнал состояния/фиксированной причины отказа без credentials. |
| `uv run omk lab dj2-account-recovery --operator-workflow …` | Свежие Linux DJ2/Drasl + loopback RCON, 73 условия и экспорт для независимой сверки; не принимает реальный account UUID. |
| `uv run omk lab admin smoke` | Реальные Drasl/HTTP и проверки границы игрок/владелец |
| `uv run omk lab client-crash --help` | Настоящий управляемый краш DJ2, очередь без сети и закрытый экспорт; [аргументы и изоляция](../CLIENT_CRASH_TESTING.md), 27 проверок прошли |
| `uv run omk lab dj2-recovery --help` | Отдельный стенд отката выделенной базы из снимка, никогда не рабочие миры |
| `uv run omk lab dj2-recovery --edge-cases …` | Дополнение того же стенда: сущности, read-only покрытие и намеренное частичное применение неполного снимка; все обязательные пути из [TESTING](dj2/TESTING.md) |
| `uv run omk lab dj2-recovery --runtime linux-docker --edge-cases …` | Те же игровые сценарии в Linux volume: 93 проверки прошли, включая повтор после startup-обхода. Java внутри закреплённого образа, [параметры/границы](dj2/TESTING.md) |
| `uv run omk lab dj2-recovery --runtime linux-docker --mod-systems …` | Отдельные 38 проверок ME-сундука AE2/двухблочного накопителя EnderIO, повторного отката и работы после restart; [условия и ограничения](../MOD_SYSTEM_RECOVERY.md) |
| `uv run omk lab dj2-recovery --runtime linux-docker --edge-cases --full-backup-return …` | Полный мир в новом Linux volume: 112 серверных условий / 6 проверок файлов, исходник не меняется. Откатывается весь мир; рабочего apply/cutover нет. [Границы](../LINUX_WORLD_RETURN.md) |
| `uv run omk lab dj2-recovery --runtime linux-docker --edge-cases --full-backup-return --access-policy …` | Проверка текущих bans/OP/whitelist при возврате старого мира: 120 серверных условий, 12 проверок файлов. Только новый стенд; [границы](../LINUX_WORLD_RETURN.md) |
| `uv run omk lab dj2-recovery --runtime linux-docker --edge-cases --full-backup-return --access-policy --rank-policy …` | Дополнительно текущие определения FTB-рангов и реальная home-квота: 125 серверных условий, 16 проверок файлов. Исторические назначения ролей/членства не сверяются; только новый стенд. [Границы](../LINUX_WORLD_RETURN.md) |
| `uv run omk lab dj2-recovery --runtime linux-docker --edge-cases --full-backup-return --access-policy --rank-policy --managed-backups …` | Управляемое хранилище реального мира в Linux volume: 133 игровых условия / 25 проверок файлов, отказ квоты, публикация до ротации, полный возврат из выбранной копии и сохранность текущих допусков. Это lab, не рабочий scheduler/apply. [Параметры/папки](../LINUX_WORLD_RETURN.md#управляемые-копии-остановленного-мира) |
| `uv run omk lab dj2-claims --suite all …` | Существующие claim/container/mute/TNT регрессии в новом Linux volume: DJ2 2.23.4 / Core 0.2.8, 54 серверных условия / 8 проверок файлов. Можно отдельно `claim-edges` или `explosions`; [параметры и границы](../DJ2_CLAIM_REGRESSIONS.md). Не команда рабочего сервера. |
| `uv run omk doctor` | Проверка локального окружения |
| `uv run omk storage plan` | Расчёт бюджета VPS из env/defaults; ничего не применяет и не удаляет. [Миры, предгенерация и диск](../WORLDS_AND_STORAGE.md) |
| `uv run omk policy dj2-territories` | План квоты территорий из env/defaults, без записи. `--config-directory PATH_TO_STAGING/config` создаёт только новый файл политики в остановленной копии. [Правила и состояние приёмки](../CLAIM_TERRITORIES.md) |
| `uv run omk policy dj2-resource` | План отдельного ресурсного мира без записи. `--source-config PATH_TO_STOPPED_COPY/config --output NEW_BUNDLE` готовит только новую папку конфигурации с SHA; не применяет её и не выполняет вайп. [Файлы, env и оставшаяся приёмка](../RESOURCE_WORLD.md) |
| `uv run omk locale audit --source en_us.lang --locale ru_ru.lang --previous-source old/en_us.lang` | Read-only проверка ключей/параметров перевода и изменённых исходных строк; предыдущий файл необязателен. Не заменяет смысловую и игровую проверку. [Обновление сборки](../PACK_UPGRADES.md) |
| `uv run omk upgrade registry-audit --source old-level.dat --target fresh-level.dat` | Сравнение сохранённых реестров Forge из остановленных копий: исчезнувшие/новые имена и число изменённых числовых ID, SHA256 входов. Только чтение; удалённые имена дают exit 1 и требуют разбора. Не конвертирует мир и не разрешает обновление. [Проверка миграции](../DJ2_MIGRATION_REGISTRIES.md) |
| `uv run python -m omk lab backup-safety` | Проверка ротации, настоящего ENOSPC и SIGKILL в одноразовом Linux Docker; не принимает рабочие миры. [Устройство и ограничения](../BACKUP_SAFETY.md) |
| `uv run omk lab cold-backups` | 13 real Docker/CLI условий на синтетических данных: race/process death/finish/cancel/source restart/600 MiB при ограниченной памяти. [Процедура](../COLD_BACKUPS.md) |
| `uv run omk lab dj2-recovery --runtime linux-docker --edge-cases --full-backup-return --access-policy --rank-policy --managed-backups --operator-backups …` | Четыре холодных owner plan/run на настоящем Forge: 137 игровых условий/30 проверок файлов; новый volume для полного возврата. Не готовый restore/cutover рабочего сервиса. |
| `uv run omk lab dj2-recovery --runtime linux-docker --edge-cases --full-backup-return --access-policy --rank-policy --ftb-authority-policy …` | Полный лабораторный возврат только при совпадающих текущих полномочиях FTB. `--ftb-authority-conflict` проверяет отказ при отозванном союзнике. Не рабочая restore-команда. [Покрытие/папки](../FTB_RESTORE_AUTHORITY.md) |
| `uv run omk lab dj2-recovery --runtime linux-docker --edge-cases --full-backup-return --access-policy --rank-policy --ftb-authority-policy --ftb-authority-conflict --reconcile-ftb-authority …` | Явный перенос известных текущих полномочий при стабильных identity; исторические homes/claims сохраняются, частичный перенос не запускается. Только новый Docker lab. [Порядок/журналы](../FTB_AUTHORITY_TRANSFER.md) |
| `uv run omk lab dj2-linux-paths --server-source … --agent … --core … --mods-json …` | Новый CON account, Linux Forge и owner cold backup; восстановление в Linux volume, повторный вход/inventory/home. Только свежие lab volumes. [Параметры/папки](../LINUX_SERVER_PATHS.md) |
| `uv run omk lab dj2-linux-policy --server-source … --agent … --core … --mods-json …` | Исторический Linux-мир с текущими bans/OP/whitelist/ranks/FTB; проверка перед Forge. Только свежие lab volumes. [Порядок/ограничения/папки](../LINUX_CURRENT_POLICY.md) |
| `uv run omk lab dj2-owner-restore --server-source … --agent … --core … --mods-json …` | Реальный Linux DJ2/Drasl/CON через owner restore CLI, отдельный target и текущие права. Только fresh lab volumes; [папки/приёмка](../OWNER_RESTORES.md) |
| `uv run python scripts/smoke_api_container.py` | Настоящий Linux API/Compose: env, лимиты, два workers и чистый stop; [17 условий на Granian 2.8.6](../API_RUNTIME.md) |
| `uv run python scripts/diagnose_api_shutdown.py --cycles 3` | Изолированные остановки API со сбором раздельных стеков при задержке; не подключает auth/игроков |
| `uv run python scripts/diagnose_api_shutdown.py --race --cycles 3` | Синтетическая регрессия гонки Granian в отдельном ASGI fixture, без изменения приложения API; [сравнение и границы](../API_RUNTIME.md) |
| `uv run python -m omk lab dj2-startup --help` | Наблюдение повторных стартов полного DJ2 в новом Linux volume; ресурсы/OOM, стек исключения деобфускатора, opt-in байткод. [Аргументы, пути и границы](../DJ2_STARTUP_DIAGNOSTICS.md) |
| `uv run omk server list` | Настроенные профили и их статус |
| `uv run omk launcher --help` | Адреса/API и отдельная переносимая папка лаунчера |
| `uv run omk lab auth smoke` | Одноразовый Drasl: регистрация, UUID, сессии, скины |
| `uv run omk auth configure --output .omk-admin/drasl.toml` | Создать приватный конфиг постоянного Drasl из валидированных `OMK_AUTH_*`; существующий не перезаписывать. [Настройки и запуск](../AUTH_STORAGE.md) |
| `uv run omk lab auth-storage` | Свежие Linux volume: recreate/SIGKILL, SQLite/скины/ключи, полный backup, новый том и изолированный restore с отзывом прежних доступов. Никаких рабочих аккаунтов. |
| `uv run omk lab auth expiry` | Настоящее истечение токена |
| `uv run omk lab launcher smoke` | Qt + настоящий временный Drasl |
| `uv run omk lab dj2 --help` | Новый loopback Forge/FTB/Core-стенд с двумя тестовыми игроками |
| `uv run omk lab dj2-linux --help` | Проверенный запуск полного DJ2 в Linux Docker и вход Windows-клиента; [изоляция, параметры и границы](../SERVER_CONTAINERS.md) |
| `uv run omk lab dj2-spawn --help` | Новый Linux-стенд: server-owned FTB-спавн, границы, TNT и возврат своей могилы через Shift в чужом/серверном claim; [параметры и ограничения](../SPAWN_AND_GRAVES.md) |
| `uv run omk lab dj2-rtp --help` | Linux DJ2: RTP текущего мира, Nether/TF, ограничения и два одновременных запроса; [конфигурация и проверки](../DIMENSION_RTP.md) |
| `uv run omk lab dj2-wrcbe --help` | Изолированный Linux DJ2: callback WR-CBE при остановке и связь после restart; default 2.21.3, проверенный `--pack-version 2.23.4` выбирает точные target pins. [Артефакты/параметры/границы](../WRCBE_SHUTDOWN.md) |
| `uv run omk release pack --help` | Подписать подготовленный релиз сборки локально |
| `uv run omk release launcher --help` | Подготовить подписанное обновление лаунчера |

Команд CLI для вайпа рабочего мира/сервера пока нет. Игровые административные команды
в справочнике не запускались на исходном сервере ради составления списка.

## Обновление справочника

Внутренний main-thread maintenance bridge Core 0.3.6 не добавляет новых
пользовательских/CLI-команд. Его probe/warning вызывают существующие Python
services для будущего ночного coordinator и TUI; не требуется запоминать
дополнительные transport-команды. [Назначение и границы](../NIGHTLY_BACKUPS.md).

Диагностический режим приватного OmkalityCore 0.2.1 выгружает реестр только при явном
JVM-флаге `-Domkality.lab.commandCatalog=true`; `omk lab dj2` задаёт его своей копии сервера.
В каталоге стенда появляется `server/omk-command-catalog.json`, без учётных данных.
Публикуемый снимок сохраняет все команды, 23 параметра рангов и 326 отдельных прав;
тысячи однотипных блочных/предметных прав сведены в семейства с точными исключениями.

После утверждения снимка таблицы пересобираются:

```text
uv run python scripts/render_command_catalog.py docs/commands/dj2/registry.json docs/commands/dj2/REGISTRY.md
```

Будущий гайд в лаунчере будет отдельной страницей с общими правилами, материалами
конкретного профиля и картинками. Его создаём после проверки команд и выбора модов.
