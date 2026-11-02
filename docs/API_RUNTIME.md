# Настройки запуска API

Часть [#30](https://github.com/omkality/omkalitycraft/issues/30), отдельная задача
[#48](https://github.com/omkality/omkalitycraft/issues/48). Это конфигурация CDN API,
не завершённая конфигурация production auth/Minecraft/VPS.

## Единый запуск

```powershell
uv run python -m api
```

Запуск читает Settings, валидирует значения и заменяет процесс на Granian без shell.
И Dockerfile использует этот же entrypoint. Порт и число воркеров теперь действительно
действуют; раньше Dockerfile передавал фиксированные 8000/1 независимо от Settings.
Ошибка настройки завершает процесс с кодом 2, без входных значений и traceback.

Порядок: окружение процесса → `.env` из текущей рабочей папки → defaults.
Прямой вызов `granian --port ...` по-прежнему управляется аргументами самого Granian;
для согласованного запуска из наших env используйте `python -m api`.

| Переменная | Default | Допустимо / смысл |
| --- | --- | --- |
| `API_HOST` | `127.0.0.1` | Числовой IPv4/IPv6, например `::1`, без URL/скобок |
| `API_PORT` | `8000` | 1…65535 |
| `WORKERS_NUM` | `1` | 1…32 |
| `API_REQUESTS_PER_SECOND` | `128` | 1…10000; bucket штатного middleware в каждом worker |
| `CLIENT_REPORTS_PRUNE_INTERVAL_SECONDS` | `3600` | 60…86400; очистка только при включённом inbox |
| `CONTENT_ROOT` | `data/content` | Для native — папка CDN относительно cwd или абсолютный путь |
| `OMK_API_CPUS` | `1.0` | 0.1…64 CPU, фактически ограничивает Docker |
| `OMK_API_MEMORY_MIB` | `1024` | 128…65536 МиБ, фактически ограничивает Docker |
| `OMK_API_LOG_MIB` | `10` | 1…1024 МиБ на файл Docker local logs |
| `OMK_API_LOG_FILES` | `3` | 1…30 файлов Docker local logs |

CPU/RAM/ротация валидируются Settings, но native-процессу они не создают системные
квоты. Их применяет Docker. Несколько workers имеют отдельные память, кеш онлайна
и rate-limit buckets: это не единая распределённая квота на весь сервис.
Необходимость нескольких workers выбирается по нагрузке; default остаётся 1.
Интервал очистки inbox не меняет сроки/квоты самих отчётов и не включает их приём.

Необязательные параметры inbox и онлайна перечислены в [.env.example](../.env.example),
[LOGGING.md](LOGGING.md) и [SERVER_STATUS.md](SERVER_STATUS.md).
Постоянные данные Drasl/HTTPS/закрытый inbox не подключены к CDN-only Compose.

## Development Compose

`docker-compose.yml` читает env через Compose, затем передаёт явные значения процессу.
Окружение оболочки выше выбранного `--env-file`; без `--env-file` Compose использует
свою стандартную `.env`. Settings внутри образа читает переданное окружение, рабочая
`.env` в образ не копируется. Явные env защищают от случайного наследования host-путей.

- Публикация строго на `127.0.0.1`, с одинаковым `API_PORT` внутри/снаружи.
- Внутри контейнера `API_HOST=0.0.0.0` — сетевой инвариант, а не открытие host-интерфейса.
- `CONTENT_ROOT=/data/content` — внутренний путь read-only mount.
- `OMK_API_CONTENT_SOURCE` задаёт исходную папку, default `./data/content` относительно
  Compose-файла. Папка должна существовать: автоматическое создание опечатанного пути отключено.
- CPU/RAM и Docker local logs берутся из env. Ротация приблизительно ограничивает
  объём файлов `OMK_API_LOG_MIB × OMK_API_LOG_FILES`; служебные данные Docker учитываются отдельно.
- Контекст сборки исключает `.env`, `.git`, `.local`, `.omk-admin`, runtime/data и сессии.
  Образ, Java и моды не заменяются произвольными клиентскими env.

Проверка примера без изменения рабочей `.env`:

```powershell
docker compose --env-file .env.example config --quiet
```

## Реальная проверка Linux

```powershell
uv run python scripts/smoke_api_container.py
```

Стенд собирает закреплённый `Dockerfile.api`. Проверяет default в контейнере без
публикации порта, затем настоящий Compose с новым loopback-портом, двумя workers,
fixture-контентом read-only, 0.75 CPU / 512 МиБ и ротацией 4 МиБ × 2. Проверяются
ошибки настроек без эха значения, отсутствие приватных host-папок в образе и
чистый SIGTERM без OOM. Ни auth, ни игровой мир, ни рабочая `.env` не подключаются.
Удаляются только UUID-проект/контейнер/тег этого запуска, без глобального prune.

Отчёт: `.local/api-runtime-<id>/report.json`, `build.log` и `server.log`.
Это проверка Linux API/Compose, не тест Minecraft и не готовность VPS.

[Локальный отчёт 2 ноября 2026](validation/api-runtime-config-2026-11-02.json):
16 условий прошли, включая оба запуска/остановки и удаление только своих ресурсов.
Unit/UI после изменений: 545 passed, 3 Windows symlink skips; проверка CI выполняется
для точного head PR. Полный аудит env других сервисов #30 остаётся открытым.
