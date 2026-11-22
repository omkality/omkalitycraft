# Разработка OmkalityCraft

Изменения обсуждаются в [GitHub Issues](https://github.com/omkality/omkalitycraft/issues)
и попадают в `dev` через пул-реквесты. В `master` входят проверенные изменения.
Правила репозитория описаны в [AGENTS.md](../AGENTS.md).

## Структура репозитория

| Папка | Назначение |
| --- | --- |
| `launcher/` | Переносимое приложение Python/Qt, установка и обновление |
| `api/` | Litestar API для игровых файлов, статуса и диагностики |
| `omk/` | CLI и сервисы владельца. `accounts` — Drasl, `owner` — управление, `worlds` и `backups` — сохранения, `deployment` — инфраструктура, `distribution` — релизы, `observability` — метрики, `labs` — тестовые стенды |
| `tui/` | Терминал владельца на Rust/Ratatui поверх Python CLI |
| `mods/` | Исходники Forge Core, DJ2Fix и клиентских компонентов |
| `profiles/` | Профили серверов и настройки сборки |
| `deploy/` | Compose и примеры настроек окружения |
| `tests/` | `unit`, `ui`, `integration` и общие фикстуры в `fixtures` |

Точки входа — `uv run omk` и `uv run python -m api`. Публичные репозитории
содержат исходники, профили и шаблоны. Рабочие конфиги, ключи, игровые миры и
артефакты сборок хранятся вне Git.

## Локальная проверка

Из корня репозитория с Python 3.14.2 и `uv`:

```console
uv sync --locked --all-groups
uv run omk doctor
uv run omk server list
uv run --no-sync ruff check
uv run --no-sync pytest tests/unit -q -n 4 --dist=loadfile
uv run --no-sync pytest tests/ui -q -n 0
```

Qt и игровые сценарии выполняйте последовательно. Для Drasl и игровых
проверок нужны изолированные тестовые контейнеры. `uv run omk lab --help`
показывает доступные стенды. Проверка запуска пакета и входа в Minecraft
проводится отдельно от проверки лаунчера и API.

| Задача | Документация |
| --- | --- |
| Локальный API и Compose | [API Runtime](API_RUNTIME.md), [развёртывание](../deploy/README.md) |
| Сборка лаунчера и публикация пакета | [Релизы](RELEASES.md) |
| Операции владельца | [TUI](OWNER_TUI.md), [CLI](ADMIN.md) |
| Forge и игровая приёмка | [Моды](../mods/README.md), [матрица проверок](GAME_TEST_MATRIX.md) |
| История изменений | [CHANGELOG](../CHANGELOG.md), [журнал разработки до 0.3.3](https://github.com/omkality/omkalitycraft/blob/820fc8dac3e452755cd2c97d2b23ad73fb4e7f88/docs/DEVELOPMENT.md) |
