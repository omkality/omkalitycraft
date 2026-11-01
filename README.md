# OmkalityCraft

Переносимый лаунчер и CDN API для игры сообщества стримера на модовых Minecraft-серверах.
Лаунчер находится в `launcher/` того же репозитория. Python + Qt, Drasl + authlib-injector,
Forge сборки без гибридных Bukkit-ядер.

Есть регистрация с выданным паролем, запомненная сессия, скины, установка по подписанному
manifest и автообновление самого лаунчера через TUF. На отдельном Windows-стенде проверен
настоящий вход DJ2 RU 2.21.3 на Forge; отдельный Linux Docker-сервер также проверен
настоящим Windows-клиентом. GTNH пока планируется; публичного сервиса ещё нет.
Версия `0.3.0.dev8` — этап разработки, не публичный игровой релиз.

**[Команды, ограничения, таймеры и роли серверов](docs/commands/README.md)** — практический
справочник DJ2, полный реестр 438 серверных команд/подкоманд и отдельная предварительная справка GTNH.

## Разработка

```powershell
uv sync --locked --all-groups
uv run omk doctor
uv run omk server list
docker compose -f deploy/auth-lab/compose.yaml pull
uv run omk lab launcher smoke
uv run omk lab auth expiry
uv run pytest -q
```

Локальный CDN:

```powershell
uv run granian --interface asgi api.app:app --host 127.0.0.1 --port 8000
```

Для локального контента `CONTENT_ROOT` должен указывать на абсолютный путь к папке CDN.
Пустой CDN допустим. БД, Java, модпаки и игровые миры в Git не входят.

Интерфейс из исходников, с отдельными тестовыми данными:

```powershell
uv run omk launcher --auth-url http://127.0.0.1:25586 --api-url http://127.0.0.1:8000 --root .local/player-test --data-dir .local/player-test/userdata
```

Этому запуску нужны Drasl и подписанный контент; `omk lab launcher smoke` сам создаёт
одноразовый стенд аккаунтов. Самостоятельный дистрибутив не требует Python у игрока.
Все файлы приложения, сборки, Java и сессии размещаются в переносимой папке.
Пароль и токен управления аккаунтом не сохраняются.

## Где искать крашлоги и отчёты

У игрока пути ниже отсчитываются от **переносимой папки лаунчера**, содержащей
`instances/` и `userdata/`. При запуске из исходников с `--root .local/player-test`
это `omkalitycraft/.local/player-test/`. Они не находятся в системной `.minecraft`.

| Что нужно | Где находится |
| --- | --- |
| Исходные crash-report DJ2 | `instances/dj2/crash-reports/crash-*.txt` |
| Фатальная ошибка Java, если JVM смогла записать её | `instances/dj2/hs_err_pid*.log` |
| Журнал Minecraft/Forge | `instances/dj2/logs/latest.log` |
| stdout/stderr игры и журнал лаунчера | `userdata/logs/dj2-game.log`, `userdata/logs/launcher.jsonl` и их ротации |
| Ожидающие отправки короткие клиентские отчёты | `userdata/client-incidents/<id>.json`; после подтверждения API запись удаляется |

Лаунчер собирает отчёт автоматически, без меню диагностики и уведомлений. Если API
недоступен, отчёт остаётся в очереди. При успешной доставке исходный crash-report
остаётся локально до ротации; это другой файл. Наличие crash-report не гарантировано
при выключении ПК, принудительном завершении или падении самой JVM/ОС.

**У владельца:** при конфигурации из `deploy/operator.example.toml`, скопированной
в `.omk-admin/operator.toml`, принятые отчёты находятся в
`.omk-admin/client-reports/client-reports.sqlite3`. Фактическую папку задают
`[reports].root` и совпадающий `CLIENT_REPORTS_ROOT` API; это закрытая папка вне CDN.
Публичный приём ещё не развёрнут. Чтение и экспорт выполняются утилитой владельца:

```text
uv run omk admin --config .omk-admin/operator.toml reports list
uv run omk admin --config .omk-admin/operator.toml reports export --id REPORT_ID
```

Список сохраняется в `.omk-admin/client-report-inventory.json`, выбранный отчёт —
в `.omk-admin/report-exports/<id>.json`. Игрокам эти файлы и чтение inbox недоступны.
Хранение ограничено 14 сутками / 20 отчётами на игрока / 1000 всего; локальная очередь
дополнительно ограничена 20 файлами / 2 МиБ. Подробнее: [LOGGING.md](docs/LOGGING.md).

**Сервер Minecraft:** `crash-reports/`, `logs/` и `hs_err_pid*.log` находятся в корне
данных выбранного Forge-сервера. В нашем Linux-стенде это `/srv` внутри контейнера,
а данные хранятся в Docker named volume, который не является обычной подпапкой проекта
в Windows. Рабочая привязка данных VPS ещё не настроена. Папки отдельных стендов и их
`report.json` находятся в `omkalitycraft/.local/`; состояние последнего восстановления —
`.local/recovery-status.json`. Сырые крашлоги, БД и сессии не публиковать в Git.

- [Текущее состояние и следующий этап](docs/DEVELOPMENT.md)
- [Миры, предгенерация, RTP и бюджет диска из env](docs/WORLDS_AND_STORAGE.md)
- [Онлайн серверов и его env-настройки](docs/SERVER_STATUS.md)
- [Релизы и автообновления](docs/RELEASES.md)
- [Команды владельца и выдача приглашений](docs/ADMIN.md)
- [Логи, crash-report и диагностический архив](docs/LOGGING.md)
- [Переносимые сессии](docs/PORTABLE_SESSIONS.md)
- [История изменений](CHANGELOG.md)

Изменения проходят отдельные коммиты и PR в `dev`. `master` сохраняется для проверенных этапов.
Интерфейс и упаковка проверяются на Windows, Linux и macOS; игровой запуск каждой платформы —
отдельная проверка. OmkalityCore остаётся закрытым и в этот репозиторий не входит.
