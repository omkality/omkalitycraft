# Зашифрованная передача готовых архивов

Первый этап #33 — внутренний Python-адаптер restic 0.19.1 для REST/TLS и
проверочного восстановления. Новых команд `omk`, второго игрового backup writer,
таймера и host job нет. Подключение к `nightly` ещё не реализовано. Рабочее
назначение вне диска VPS не настроено; Docker-тома одного хоста не заменяют его.

Транспорт получает небольшой **плоский каталог уже подготовленных архивов**.
Живые Minecraft/SQLite этим интерфейсом не резервировать. Для мира остаются
существующие clean stop/cold-copy проверки, для Drasl —
[согласованная копия всего state](AUTH_STORAGE.md). Наличие SHA исходных файлов
не подтверждает согласованность разных компонентов приложения.

## Инструменты и сборка

Версии, официальные release URLs, хеши загрузок и распакованных Linux/amd64
бинарников закреплены в [manifest](../deploy/offsite-tools.json). Python base
закреплён digest. Инструменты не скачиваются при запуске лаунчера.

```console
python scripts/fetch_offsite_tools.py --output .local/offsite-tools-0.19.1
docker build --platform linux/amd64 --network none -t omk-offsite-tools:0.19.1 .local/offsite-tools-0.19.1
```

Каталог назначения должен быть новым и без ссылок. Fetch проверяет hash/size,
не распаковывает TAR-пути на диск и создаёт build recipe только после проверки
обоих инструментов. Ошибка оставляет неполный каталог для осмотра; автоматически
он не очищается. Linux image — инструменты для worker/лаборатории, не готовый
deployment profile и не установщик расписания. Python-адаптер использует только
стандартную библиотеку; GUI/API dependencies в этот image не нужны.

## Приватные настройки

`Restic` получает `credential_root`, отдельный mode-700 workspace, проверенный
64-символьный repository ID и `policy()`. Worker запускается в ограниченном
Linux Docker-контейнере; source/credentials/code монтируются readonly. Docker
memory/CPU/volume budgets должен обеспечить вызывающий owner workflow.

В `credential_root` находятся только:

- `repository`: одна строка `rest:https://USER:PASSWORD@HOST:PORT/REPOSITORY/`;
- `password`: пароль шифрования репозитория;
- `ca.pem`: доверенный TLS CA, а не приватный ключ сервера.

Repository/password — mode 600, без ссылок; допускается один завершающий LF
или CRLF. URL/пароль не передаются в argv или Docker Env. Дочерний restic получает
только пути файлов и очищенное окружение, без унаследованных proxy/RESTIC hooks.
Raw stdout/stderr при отказе не включаются в исключения или журналы. Ввод/вывод
и время дочернего процесса ограничены; таймаут убивает его process group.

Сервер назначения не должен получать пароль шифрования. Его TLS private key и
HTTP authentication хранятся отдельно от клиентских файлов. Пароль шифрования
и сведения для доступа нужно сохранить у владельца **вне игрового VPS и самого
зашифрованного репозитория**: иначе после потери VPS открыть копию будет нечем.
Файлы/ключи/готовые архивы не входят в Git, release или player diagnostics.

| Переменная | Default | Диапазон |
| --- | --- | --- |
| `OMK_OFFSITE_TIMEOUT_SECONDS` | `900` | 1–7200 на один процесс restic |
| `OMK_OFFSITE_OUTPUT_BYTES` | `262144` | 1024–4194304 на каждый pipe |
| `OMK_OFFSITE_UPLOAD_KIB` | `10240` | 64–1048576 KiB/s |
| `OMK_OFFSITE_GOMAXPROCS` | `1` | 1–4; не заменяет Docker CPU quota |
| `OMK_OFFSITE_MAX_BYTES` | `17179869184` | 1–1099511627776 суммарных байт export |
| `OMK_OFFSITE_MAX_FILES` | `32` | 1–128 обычных файлов без подкаталогов |

Перед staging restore сохраняется общий project reserve из storage policy.
Это preflight, не жёсткая quota файловой системы. Временные/ошибочные restore
каталоги сохраняются внутри workspace; их дальнейший общий бюджет/retention
принадлежит будущему owner workflow. [Пример env](../deploy/offsite.example.env).

## Внутренний интерфейс

| Операция | Результат и граница |
| --- | --- |
| `inspect()` | TLS/auth, закреплённый repository ID и формат 2 |
| `find(operation, frozen_export)` | Единственный snapshot с точными operation/source tags, hostname/path. `data_read_back=false`; это ещё не подтверждение полной копии |
| `upload(source, operation)` | Хеши/лимиты до и после отправки, только exit 0 и ожидаемый ACK. Уже существующий operation отказывает вместо повторной отправки |
| `check()` | Полное чтение данных репозитория с блокировкой; не проверяет, все ли ожидаемые исходные файлы попали в конкретный snapshot |
| `restore(receipt)` | Чтение выбранного immutable ID в новый private staging, restic verify, точный набор путей/размеров/SHA. Возвращает `data_read_back=true`, `ready_for_players=false` |

Метаданные и staging restore используют `--no-lock`, чтобы чтение не требовало
записи в полное/readonly хранилище. Backup и полный check сохраняют блокировки.
Внешний concurrent prune может прервать чтение: ошибка или несовпадение байтов
не получают подтверждения. Действий init/forget/prune/unlock/repair у адаптера
нет. Append-only — свойство отдельно настроенного destination, не обещание
клиентской библиотеки. В лаборатории запрет удаления проверен реальным запросом.

Exit **3** означает частичный snapshot и всегда отказывает. Ненулевой exit,
таймаут или потеря ACK требуют осмотра **того же operation**; повторного upload
и автоматического unlock нет. После exit 3 snapshot может существовать, но
проверочный restore обнаружит недостающие файлы. Повторное совпадение operation
не является concurrency fence: вызывающий coordinator обязан сериализовать jobs,
сохранить durable intent/expected export и доказать завершение прежнего worker.
Этот эксплуатационный workflow ещё не реализован.

## Проверено локально

24 Linux Docker transport-условия: TLS/auth/шифрование, точные файлы, exit 73
после upload до ACK, настоящий exit 3, обрыв peer во время отправки, backend
quota/507, ciphertext canary, pack corruption с исправным control и readonly
repository volume. Клиенты — 1 CPU/512 MiB, server — 1 CPU/128 MiB; сеть internal,
host ports/Docker socket отсутствуют. Клиентский пароль шифрования и server key
разделены разными volumes. После экспорта свои ресурсы удалены, OOM не было.

Независимый Linux verifier без business readers: семь restore, 42 точных файла,
CRC ZIP мира (321 entry), auth TAR/SQLite integrity/signing key/skins и operator
archive (18 файлов). Код проверен 59 новыми cases; полный Windows unit/UI —
2048 passed /48 skipped, Linux focused — 598. [Протокол](validation/offsite-transport-2026-11-12.json).

Входы взяты из **разных** ранее принятых DJ2/auth labs; это проверка передачи
компонентов, не согласованный backup одного проекта. Minecraft/Drasl заново не
запускались. Runtime/modpack payload не включён. Физически отдельный off-host,
production retention и capacity этой маленькой лабораторией не подтверждены.

Далее #33: один согласованный export set с версиями/временем компонентов,
durable owner transfer и recovery после потерянного ответа, подключение к одному
nightly coordinator, отдельное destination/retention и полный application return.
Восстановленные Drasl/operator state сначала проходят карантин и проверку
актуальных bans/roles/отозванных доступов; старые journals не исполняются вслепую.
Перед VPS остаётся аудит владельца. Launcher/player release/Java не менялись.
