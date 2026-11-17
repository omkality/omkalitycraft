# Контракт результата owner CLI, версия 1

Это локальный интерфейс для будущей Rust TUI поверх существующих Python services.
Самой TUI, HTTP endpoint, daemon, очереди заданий или нового журнала операций здесь
нет. Доступ определяется прежним private operator config и правами владельца.
Контракт не даёт прав игроку и не входит в player launcher.

## Вызов и совместимость

```text
uv run omk admin --config .omk-admin/operator.toml --result-version 1 backups status --operation <32-hex-id>
```

Без `--result-version` остаётся прежний JSON, exit codes и поведение команд.
Значение версии указывается **до** подкоманды. Версия 1 поддерживает ровно 15 действий:

| Семейство | Действия |
|---|---|
| `backups` | `plan`, `run`, `status`, `finish`, `cancel` |
| `maintenance` | `plan`, `stop`, `status`, `start`, `reconcile`, `cancel` |
| `restores` | `plan`, `apply`, `verify`, `status` |

Остальные действия возвращают `unsupported_action` до чтения конфигурации, prompt
или вызова сервиса. Клиент не должен автоматически переключаться на legacy mode
и повторять действие. Полные inventory/list/diagnostics/access и остальные owner
области не объявляются частью v1. Legacy CLI для них остаётся доступным.

Один процесс выполняет выбранный service один раз и выдаёт один итоговый JSON в
stdout. Stderr не является частью схемы. Вызов завершается с кодом 0 при `ok=true`,
1 при `ok=false`. Неизвестная CLI-версия/неверные аргументы отклоняются argparse
до dispatch: exit 2, stdout без контрактного JSON. Сетевые соединения, Docker/RCON,
проверки плана, блокировки, журнал и действия выполняются существующими services.
Результат проецируется после вызова; он не запускает дополнительное восстановление.

## Смысл полей

Обязательные верхние поля: `schema_version`, `action`, `ok`, `status`, `operation`,
`error`. Версия — целое число 1, не boolean и не значение по умолчанию при чтении.
Неизвестная версия/поле или нарушенные инварианты требуют отказа чтения, а не
догадки о совместимости. Строки ответа ограничены enum/ID полями и фиксированными
сообщениями; raw exception, journal/config, paths и произвольный service payload
в v1 не копируются. Полные подробности плана остаются в legacy owner CLI.

`status` описывает **вызов**: `succeeded`, `failed`, `unknown`. `ok=true` означает,
что вызов успешно вернул распознанный результат, а не завершение долгой операции.
Например, чтение `backups.status` с фазой `incomplete` успешно и даёт exit 0.
`invalid_service_result` означает `unknown`: действие уже могло выполниться.

`operation` содержит `id`, `kind`, nullable `server_id`, nullable `phase`, nullable
`terminal` и nullable `backup_operation_id`. ID — 32 строчных hex символа. Имя
сервера берётся из результата/аргумента, не угадывается дополнительным чтением.
На ошибке известный request ID — только ссылка для последующего поиска, не
доказательство наличия записи. Фаза/terminal на ошибке неизвестны (`null`).
Если ID ещё не получен, `operation=null`; потеря ответа планирования не создаёт
автоматически нового плана. Некоторые успешные native результаты не содержат
имени сервера: `server_id=null` допустимо.

| Семейство | Фазы v1 | Терминальные фазы |
|---|---|---|
| backups | planned, preparing, publishing, published, acknowledging, incomplete, complete, cancelled | complete, cancelled |
| maintenance | planned, stop-requested, stopped, start-requested, complete, cancelled | complete, cancelled |
| restores | planned, applying, incomplete, staged | staged |

`terminal=true` относится только к этому workflow. В частности, restore `staged`
не означает promotion или открытие доступа игрокам. Готовность сервера/ingress
этот контракт не подтверждает. Неизвестная фаза не превращается в `complete`.

## Ошибки и повтор вызова

| code | Основание | next_step |
|---|---|---|
| invalid_configuration | ошибка до завершения load_operator_config | fix_configuration |
| owner_busy | конкретный тип OwnerBusy из существующей блокировки | wait_then_inspect |
| operation_rejected | AdminError при выполнении сервиса | inspect_operation |
| io_failure | OSError или subprocess.SubprocessError | inspect_operation |
| operation_failed | другая ошибка или явный неуспешный service result | inspect_operation |
| invalid_service_result | отсутствующий/невалидный результат, другой ID/server, неизвестная фаза | inspect_operation |
| unsupported_action | действие вне v1 | none |

Коды выбираются по этапу и типу, без разбора английского текста исключения.
Сообщения фиксированы; TUI принимает решения по `code`, не по `message`.
`effect=none` означает отсутствие операционной мутации **этим вызовом** для config,
busy, unsupported и status. Это не утверждение о предыдущей попытке; audit запись
может появиться. Для остальных ошибок `effect=unknown`: отказ мог произойти после
публикации/stop/apply. Даже AdminError не доказывает отсутствие частичных действий.

Ни один `next_step` не является разрешением на автоматический повтор мутации.
После таймаута, сигнала, потери/повреждения stdout или неизвестного формата клиент
считает результат неизвестным и запрашивает прежний `status` с известным ID.
Дальнейшие `finish`, `verify`, `reconcile` выполняются явно с прежними guards.
Не делать shell-конкатенацию, не удалять lock/journal и не заменять service
прямым `docker start`/повторным apply. Сам Rust process client здесь не реализован.

## Схема, примеры и проверки

[JSON Schema](contracts/owner-result-v1.schema.json) фиксирует форму и типы.
Cross-field правила дополнительно проверяет `OwnerResult`: `ok=true` требует
`status=succeeded`, `error=null`, известную action и operation/phase; неуспех
требует error и не допускает `status=succeeded`. Вид операции ограничивает фазы,
terminal вычисляется по таблице; при `phase=null` terminal тоже null.
Эти семантические правила обязательны и для Rust consumer: одной проверки формы
JSON недостаточно. Схема содержит phase/terminal maps и supported actions.

[Семь примеров](contracts/owner-result-v1.examples.json) проходят строгий Python
decoder и доступны для будущих Rust contract tests. Документ/схема/модели меняются
согласованно; изменение обязательных полей/смысла не скрывается под версией 1.

Unit-контроли используют временные operator files, реальные backup journals,
BackupStore и публикацию ZIP с подменённым Docker transport. Проверены потеря
записи результата после публикации, status/finish с одной копией, сохранность
исходного дерева, все 15 dispatch routes, malformed/secret-bearing results,
ошибки, версия и прежний JSON. Отдельный настоящий процесс CLI прочитал
временный журнал и вернул один JSON без Docker; исходный journal прежний.
Это не сетевой обрыв Rust client, Linux Docker/Minecraft/VPS приёмка и не
проверка настоящего Rust consumer. Scheduler и общий config-аудит здесь не меняются.
