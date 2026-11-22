# Команды OmkalityCraft

- [Команды и правила для игроков DJ2](dj2/README.md)
- [Снимок серверного реестра DJ2 2.21.3](dj2/REGISTRY.md) и [его JSON](dj2/registry.json)
- [Терминал владельца](../OWNER_TUI.md) и [CLI](../ADMIN.md)
- [Восстановление регионов](dj2/RECOVERY.md)
- [Изолированные игровые проверки](dj2/TESTING.md)

Реестр включает служебные команды модов и уровни доступа, обнаруженные
на стенде. Игрокам доступны только команды, разрешённые текущим профилем.
Для администрирования используется терминал владельца.

После обновления реестра таблица генерируется из JSON:

```console
uv run python scripts/render_command_catalog.py docs/commands/dj2/registry.json docs/commands/dj2/REGISTRY.md
```
