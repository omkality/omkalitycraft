# OmkalityCraft

Переносимый лаунчер и CDN API для игры сообщества стримера на модовых Minecraft-серверах.
Лаунчер находится в `launcher/` того же репозитория. Python + Qt, Drasl + authlib-injector,
Forge сборки без гибридных Bukkit-ядер.

Есть регистрация с выданным паролем, запомненная сессия, скины, установка по подписанному
manifest и автообновление самого лаунчера через TUF. На отдельном Windows-стенде проверен
настоящий вход DJ2 RU 2.21.3 на Forge. GTNH пока планируется; публичного сервиса ещё нет.
Версия `0.3.0.dev2` — этап разработки, не публичный игровой релиз.

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

- [Текущее состояние и следующий этап](docs/DEVELOPMENT.md)
- [Релизы и автообновления](docs/RELEASES.md)
- [Переносимые сессии](docs/PORTABLE_SESSIONS.md)
- [История изменений](CHANGELOG.md)

Изменения проходят отдельные коммиты и PR в `dev`. `master` сохраняется для проверенных этапов.
Интерфейс и упаковка проверяются на Windows, Linux и macOS; игровой запуск каждой платформы —
отдельная проверка. OmkalityCore остаётся закрытым и в этот репозиторий не входит.
