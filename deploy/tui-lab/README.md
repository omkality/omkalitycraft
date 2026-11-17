# Два постоянных локальных сервера для TUI

Это минимальный Forge 1.12.2 с одним pinned server-only Prometheus exporter,
свежими отдельными мирами и искусственной CPU-нагрузкой. Серверы явно называются
`lab-alpha` / `lab-beta`, MOTD помечен `OMK TUI LAB`. Это не сборки DJ2 и не VPS.
Метрики настоящие; аккаунтов и выдуманных игроков fixture не создаёт.

По просьбе владельца контейнеры оставляем поднятыми. `unless-stopped` восстанавливает
их после перезапуска Docker. Выход из TUI на них не влияет. Календарный scheduler
проекта остаётся на паузе: CPU-цикл принадлежит только этим тестовым контейнерам.

| Сервис | Minecraft | RCON | Искусственная работа |
|---|---|---|---|
| lab-alpha | 127.0.0.1:25610 | 127.0.0.1:25611 | 12 s каждые 75 s, первый старт через 30 s |
| lab-beta | 127.0.0.1:25620 | 127.0.0.1:25621 | 18 s каждые 110 s, первый старт через 60 s |

Prometheus: `http://127.0.0.1:25690`. Порты опубликованы только на loopback;
Minecraft работает в offline mode для этой локальной фикстуры. Не переносить
этот Compose в публичную эксплуатацию. Значения портов можно изменить в Compose
env, но соответствующие `operator.toml`/`tui.json` надо согласовать вручную.

На сервер: лимит **0,75 CPU / 768 MiB**, heap 128..384 MiB. Искусственная работа —
`sha256sum /dev/zero` с `timeout`, в том же CPU cgroup, что и Java. Она не создаёт
файлов и не меняет мир; две разные фазы дают чередование всплесков. В idle остаётся
сам Minecraft. На слабом хосте можно уменьшить квоты или отключить fixture командой
stop. При старте игры метрики rate требуют нескольких scrape/evaluation интервалов.

Telegraf ограничен 0,10 CPU / 128 MiB, Prometheus — 0,25 CPU / 256 MiB;
TSDB хранит до 4 h / 256 MB, Docker logs ограничены 2×2 MiB на игру и 2×1 MiB
на monitoring service. Два мира и TSDB находятся в именованных Docker volumes;
всем контейнерам не предоставляется Docker socket. Host метрики на Docker Desktop
относятся к его Linux VM. Не используется никакой существующий игровой том.

## Подготовка и управление

Из checkout с Python environment проекта:

```console
uv run --no-sync python scripts/tui_sandbox.py prepare --root /absolute/path/to/.local/tui-sandbox --server-source /absolute/path/to/existing/forge112-server
uv run --no-sync python scripts/tui_sandbox.py up --root /absolute/path/to/.local/tui-sandbox
uv run --no-sync python scripts/tui_sandbox.py status --root /absolute/path/to/.local/tui-sandbox
```

Источник нужен только для Forge/Minecraft JAR и libraries, старые миры/моды/config
оттуда не копируются. Forge, logging runtime и exporter проверяются по pins.
Один общий readonly runtime используется двумя играми. `prepare` отказывается
перезаписывать существующий root и не меняет старые credentials или миры.

TUI подключаем с `--config <root>/.omk-admin/operator.toml`. Секреты RCON остаются
в этой private папке и seed server.properties. Исходные файлы в Git не содержат
operational values. `--root` должен оставаться по тому же пути, пока поднят Compose.

```console
uv run --no-sync python scripts/tui_sandbox.py stop --root /absolute/path/to/.local/tui-sandbox
```

`stop` сначала запрашивает `save-all flush` у обоих серверов, затем останавливает
только этот Compose project. Не удаляет ни root, ни Docker volumes. Вновь запускаем
тем же `up`. Ручное удаление/архивирование выполняется отдельно, после проверки
сохранений; cleanup автоматически не запускается.

Состояние CPU-цикла: `.fixture/load.json` внутри каждого игрового контейнера,
переходы `OMK_TUI_LOAD` также видны в Docker logs. Если `timeout/sha256sum` не
сработали, phase будет `failed`, а не ложное утверждение о созданной нагрузке.
