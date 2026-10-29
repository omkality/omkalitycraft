# OmkalityCraft

Основа лаунчера для игры сообщества стримера на модовых Minecraft-серверах.
Текущий этап: подготовка разработки, CDN API и проверенный стенд Drasl.
Готового игрового лаунчера в этой ветке пока нет.

## Запуск разработки

Нужны Python 3.14.2 и uv; для стенда авторизации — Docker Desktop.

```powershell
uv sync --locked --all-groups
uv run omk doctor
uv run omk server list
docker compose -f deploy/auth-lab/compose.yaml pull
uv run omk lab auth smoke
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
- Версия `0.2.0.dev0` обозначает незавершённую разработку, не готовый релиз.
- Аутентификация: Drasl + authlib-injector. Telegram и собственная реализация паролей удалены из текущей основы.
- Общие команды и профили — Python; интеграция с конкретной версией Forge — отдельные адаптеры и Java по необходимости.

Подробности: [текущее состояние](docs/DEVELOPMENT.md), [история изменений](CHANGELOG.md).
