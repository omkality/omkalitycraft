# Закрытие входа перед обслуживанием

`omk admin ingress` управляет доступом к **одному исходному серверу** через
HAProxy TCP. Это локальный этап подготовки обслуживания: опубликован только
`127.0.0.1`, профиль лаунчера и публичные адреса не переключаются. На тестовый
reset-кандидат этот интерфейс направлять игроков не умеет.

## Что происходит с игроками

При запуске и перезапуске HAProxy вход закрыт. Новые TCP-соединения сразу
закрываются без соединения с Minecraft. Это технический барьер; красивого
игрового сообщения об обслуживании пока нет.

Закрытие входа сохраняет уже установленные соединения. Дальше владелец вызывает
штатную [остановку сервера](OWNER_MAINTENANCE.md): Forge сохраняет мир и отключает
игроков. Счётчик `sessions` показывает TCP-соединения, включая незавершённый вход;
это не число авторизованных игроков и не доказательство эвакуации.

Возврат исходного сервера после обслуживания **не открывает вход автоматически**.
Нужен отдельный новый план открытия. Незавершённое maintenance window,
неотменённый reset-кандидат, unreleased slot или другой pending ingress intent
блокируют открытие. Закрыть вход можно и при наличии такой операции.

## Подготовка

Нужны уже настроенные `operator.toml`, `backups.toml`, `maintenance.toml` и
закрытые RCON credentials. Исходный сервер должен находиться в единственном
собственном bridge; опубликованные game/RCON-порты — только loopback.
`online-mode=true` работает с нашей Drasl/authlib-injector авторизацией.
Drasl и существующие игровые данные здесь не создаются и не мигрируют.

1. Скопируйте [ingress.example.toml](../deploy/ingress.example.toml) в приватный
   `.omk-admin/ingress.toml`. На Unix права файла `600`.
2. Задайте уникальные имена/ownership для proxy container и control volume,
   существующий project bridge и его label. Control volume не может совпадать
   с source, backup или staging volume. Внутренний backend port — игровой,
   никогда не RCON. `config_dir` должен быть внутри `ingress-config/`.
3. Выполните подготовку. Она создаёт единственный несекретный `haproxy.cfg` с LF;
   существующие отличающиеся байты никогда не перезаписывает:

```console
uv run omk admin --config .omk-admin/operator.toml ingress prepare --server dj2
```

На Linux `.omk-admin` остаётся `700`, operator/ingress/RCON credentials — `600`.
В контейнер монтируется только отдельный `config_dir`: его права `755`, у
сгенерированного `haproxy.cfg` — `644`. Без этого container root с ALL capabilities
удалёнными не прочитает конфиг другого host UID. Файл содержит только маршрут и
параметры proxy, без паролей; Unix admin socket сохраняет `600`.

Для старого leaf с `700/600` повторный `prepare` исправляет только права после
сверки точных ожидаемых байтов. Если внутри есть посторонний файл либо содержимое
изменено, подготовка отказывается и не расширяет доступ. Перед owner-командами
сверяются и ожидаемые Unix-права; вручную менять файлы deployment не следует.

4. Подготовьте переменные окружения из
   [Compose](../deploy/ingress/compose.yaml): `OMK_INGRESS_CONTAINER`,
   `OMK_INGRESS_OWNER`, `OMK_INGRESS_CONTROL_VOLUME`, `OMK_INGRESS_CONTROL_OWNER`,
   абсолютный `OMK_INGRESS_CONFIG_DIR` из результата `prepare`,
   `OMK_INGRESS_NETWORK`. Используйте новый собственный control volume;
   конфигурацию с неизвестным существующим volume не разворачивайте.
5. Загрузите точный image из [runtime profile](../profiles/runtime/haproxy-ingress.json).
   Compose с `pull_policy: never` запускает только уже загруженный pin:

```console
docker compose --project-name omk-ingress -f deploy/ingress/compose.yaml up -d
uv run omk admin --config .omk-admin/operator.toml ingress inspect --server dj2
```

HAProxy должен закончить загрузку до `inspect`. Образ, command/entrypoint/env,
сеть, control volume, права/mounts, loopback bindings и ресурсные лимиты
сверяются по immutable identity. Произвольные HAProxy-конфиги не принимаются.
Unix admin socket находится только в приватном control volume, без TCP-порта.
Короткоживущий helper использует pinned Python, read-only mounts, `network=none`,
без Docker socket. У него только фиксированные status/enable/disable команды.

## Команды и потерянный ответ

`I` — случайный ID, возвращённый командой `plan`:

```console
uv run omk admin --config .omk-admin/operator.toml ingress plan --server dj2 --state closed
uv run omk admin --config .omk-admin/operator.toml ingress apply --operation I
uv run omk admin --config .omk-admin/operator.toml ingress status --operation I
uv run omk admin --config .omk-admin/operator.toml ingress verify --operation I
uv run omk admin --config .omk-admin/operator.toml ingress cancel --operation I
```

`apply` сначала сохраняет durable intent, затем отправляет одну команду.
Если ответа нет, `status` читает сохранённый журнал, а `verify` сверяет текущие
факты без повторной отправки команды. Второй `apply` запрещён. Несостоявшийся
или неподтверждённый intent отменяется только после подтверждения закрытого входа.
Успешный terminal intent повторно не отменяется.

Перезапуск proxy возвращает закрытое состояние и меняет boot identity. Старый
план открытия перестаёт подтверждаться; после проверки закрытия его можно
отменить и создать новый. Новый container, image, config, source, volume или
bridge старым планом не принимаются даже при совпадении имён.

Для открытия используйте `plan --state open`, затем `apply`. Проверяются тот же
запущенный source, `Done` текущей загрузки, Core readiness, игровые/RCON-порты,
online-mode и отсутствие pending операций. Адрес backend из HAProxy должен
совпасть с текущим адресом source в собственном Docker bridge. Ошибка DNS,
неполная готовность или изменившийся fingerprint блокируют подтверждение.

Maintenance plan фиксирует ingress deployment. Его `stop` требует закрытого
входа **до** записи stop intent; во время stop/start барьер проверяется снова.
Если конфигурацию ingress добавили посреди старого maintenance window, утилита
требует пересмотреть план, а не пропускает новую проверку.

## Настройки и журнал

Одни значения env должны применяться при `prepare`, запуске Compose и первом
owner-плане. Активный журнал замораживает policy; менять deployment посреди
операции нельзя.

| Переменная | По умолчанию | Допустимо |
| --- | --- | --- |
| `OMK_INGRESS_HOST_PORT` / `CONTAINER_PORT` | `25580` / `25565` | Явные порты из TOML, `1024..65535` |
| `OMK_INGRESS_CPUS` | `0.5` | `0.1..2`, до трёх десятичных знаков |
| `OMK_INGRESS_MEMORY_MIB` | `64` | `32..256` |
| `OMK_INGRESS_PIDS` | `64` | `32..128` |
| `OMK_INGRESS_MAX_CONNECTIONS` | `128` | `20..1024`, TCP connections |
| `OMK_INGRESS_CONNECT_SECONDS` | `5` | `1..30` |
| `OMK_INGRESS_IDLE_SECONDS` | `3600` | `60..86400` |
| `OMK_INGRESS_TIMEOUT_SECONDS` | `30` | `5..120`, подтверждение состояния |

TTL плана, интервал опроса и число записей используют существующие
`OMK_MAINTENANCE_*` из [maintenance guide](OWNER_MAINTENANCE.md).
Журналы находятся в `.omk-admin/ingress/<I>.json`, до 64 KiB каждый;
при заполнении лимита новые планы отказывают. Terminal history архивируется
владельцем, а не удаляется незаметно. Docker log proxy ограничен `10 MiB × 3`.
Пароли, Drasl management tokens и игровые session tokens в этих журналах не нужны.

## Границы этапа

TCP proxy не переписывает Forge/authlib handshake и не заменяет авторизацию.
Minecraft видит адрес proxy, а не исходный IP игрока: IP-баны/rate limits по
этому адресу нельзя считать индивидуальными. PROXY protocol и сохранение
реального IP требуют отдельного совместимого решения и проверки.

Подтверждение открытия — проверка конкретного перехода, не непрерывный мониторинг.
Контейнер restart policy остаётся `no`. Публичный ingress/firewall/TLS/bootstrap,
cutover к новому миру, online evacuation и общий storage budget ещё требуют
отдельной приёмки. `ready_for_players=false` сохраняется. Это не средство
обхода сетевых блокировок и не обещание доступности из любого провайдера.

[Протокол проверки полной DJ2 в Linux Docker](validation/dj2-owner-ingress-2026-11-12.json): 62 native / 185 independent условий. Два Drasl-аккаунта; графическая приёмка отдельно.
