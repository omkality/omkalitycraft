# OmkalityCraft

Основа лаунчера для игры сообщества стримера на модовых Minecraft-серверах.
Текущий этап: интерфейс аккаунта, переносимый вход, скины и CDN API.
Установка сборки и запуск Minecraft ещё не подключены.

## Запуск разработки

Нужны Python 3.14.2 и uv; для стенда авторизации — Docker Desktop.

```powershell
uv sync --locked --all-groups
uv run omk doctor
uv run omk server list
docker compose -f deploy/auth-lab/compose.yaml pull
uv run omk lab auth smoke
uv run omk lab auth expiry
uv run omk lab launcher smoke
uv run pytest
```

CDN API локально:

```powershell
uv run granian --interface asgi api.app:app --host 127.0.0.1 --port 8000
```

Без опубликованного контента `/instances` возвращает пустой список. Игровые сборки,
Java, миры, сессии и содержимое CDN не входят в репозиторий.

## Разработка

- `master` — проверенные этапы; `dev` — интеграция разработки.
- Небольшие изменения идут отдельными коммитами; крупные задачи — в отдельных ветках с PR в `dev`.
- Версия `0.2.0.dev1` обозначает незавершённую разработку, не готовый релиз.
- Аутентификация: Drasl + authlib-injector. Telegram и собственная реализация паролей удалены из текущей основы.
- Общие команды и профили — Python; интеграция с конкретной версией Forge — отдельные адаптеры и Java по необходимости.

Подробности: [текущее состояние](docs/DEVELOPMENT.md), [история изменений](CHANGELOG.md).

## Интерфейс аккаунта

```powershell
uv run omk launcher --auth-url https://YOUR-TRUSTED-DRASL-ORIGIN
```

Для локального стенда используйте `http://127.0.0.1:25586` и явно созданное тестовое
приглашение. Рабочий публичный адрес авторизации пока не настроен.
`omk lab launcher smoke` сам создаёт одноразовый стенд, проверяет интерфейс и удаляет тестовые данные.

Лаунчер рассчитан на Windows, Linux и macOS. Сессия сохраняется в собственной папке
`userdata`; другой путь можно передать через `--data-dir`. Файл содержит игровой токен,
а не пароль или токен управления аккаунтом. [Выбранная модель хранения](docs/PORTABLE_SESSIONS.md).

Сейчас это запуск из исходников. Самодостаточные пакеты с Python/Java для трёх ОС ещё не собраны.
