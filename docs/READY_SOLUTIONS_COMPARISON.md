# Сравнение готовых средств эксплуатации

Решение владельца от 13 ноября 2026: упрощать собственную инфраструктуру только
после проверки подходящего готового варианта; все серверные опыты — в Docker.
Общий результат: [Prometheus + Telegraf](RESOURCE_HISTORY.md), одноразовая
[активация nightly](NIGHTLY_BACKUPS.md); текущий локальный snapshot format сохранён.

## Мониторинг

Prometheus 3.16.0 и cpburnz 1.12.2-forge-1.0.0 сначала проверены на двух стартах DJ2
рядом с прежним collector. Node exporter 1.12.1 дал host counters, cAdvisor 0.60.6
без privileged/socket — CPU/RAM cgroup. Но cAdvisor сохранил OOM=0 после настоящего
`memory.events oom_kill=1`; отдельный повтор с readonly kmsg/SYSLOG также не дал
эквивалентного counter. Это результат нашего Linux Docker/WSL lab, не утверждение,
что cAdvisor нигде не умеет OOM. Для выбранной конфигурации он отвергнут.

Telegraf 1.40.3 напрямую прочитал cpu.stat/memory.current/memory.events/io.stat.
Управляемый child получил exit137, counter 0→1 совпал с cgroup. Он также заменяет
host collector, поэтому node_exporter/cAdvisor одновременно с ним не нужны.
DimensionType не выдаётся за world ID: реальные ID добавляются только по явному
проверенному профилю. Необязательная chunks gauge отфильтрована, чтобы одинаковые
labels миров общего типа не портили весь scrape; этот случай проверяет CI.
Финальная композиция Prometheus + Telegraf испытана с DJ2, двумя non-OP protocol
actors и независимыми Core/NBT checks. Собственные Python sampler/SQLite/aggregation
удалены; Core JSON producer остаётся выключенным compatibility кодом старого мода.

Выигрыш — стандартный storage/query API и меньше своего движка, а не меньше RSS:
в одном full lab agent+Prometheus примерно 119 MiB против 20 MiB старого collector.
Это не capacity benchmark поздней игры. Стандартный retention blocks не является
жёсткой квотой всей TSDB; бюджет/резерв и query limits описаны в RESOURCE_HISTORY.

## Таймер

Убран постоянный календарный цикл ожидания. systemd выполняет короткий trigger,
Python координирует ровно один безопасный business cycle. Не заводим отдельное daily
OnCalendar с другой копией timezone/warning arithmetic: UTC minute activation +
прежние date fences исключают такое расхождение. Ничего на host не установлено.

## Restic и локальный ZIP

Restic 0.19.1 уже является готовым encrypted offsite engine проекта. Проверено,
имеет ли смысл расширять его роль вместо самостоятельного локального ZIP-store.

Docker experiment: frozen мир из изолированного DJ2 lab, 318 файлов / 14 322 181
байт. Три снимка, между ними менялся **только искусственный sidecar 128 KiB**.
Рецепты, регионы и NBT не изменялись, Minecraft в этом опыте не запускался.

| Хранение restic | Первый data_added_packed | Каждое последующее добавление | Repo после трёх снимков |
|---|---:|---:|---:|
| Отдельные файлы | 8 535 482 B | 132 140 /132 141 B | 8 811 987 B |
| ZIP того же дерева | 8 507 697 B | 2 295 146 /2 295 148 B | 13 101 475 B |

Для обоих вариантов прошли check, forget keep-last=2/prune, повторный check и
побайтовое восстановление. Отдельный repo в tmpfs 8 MiB намеренно переполнен:
новый backup отказал, предыдущий годный snapshot восстановлен без потери байтов.
Пароль случайный, оставался внутри одноразового контейнера; network none.

Выигрыш raw tree доказан для этого опыта, но не обещает такой же коэффициент на
большом изменяющемся игровом мире. Локальный ZIP — ещё и принятый формат current-
authority restore/staging и проверенных WorldEdit snapshot опытов, с manifest/CRC
и гарантией сохранения прежней годной копии. Restic repo не заменяет этот application
contract автоматически; переход потребовал бы нового materialization/restore слоя.

**Решение до первого запуска:** не переписывать локальный snapshot/recovery format
ради одной дедупликации. Сохраняем один nightly writer, проверенный ZIP-store и
готовый restic для внешней копии. Не включаем FTB Backups вторым writer.
При росте реальных миров/offsite traffic вернёмся к raw-tree export отдельным
совместимым шагом; сначала будет повторная полная application restore приёмка,
а не только удачный `restic restore`. Это не новая обязательная миграция до DJ2.

Loki/Grafana/Sentry не добавлялись. Ограниченные технические логи и закрытые crash
reports уже решают текущую задачу; история всего чата/действий имеет отдельную
семантику и остаётся в #58/#52. Новых player UI и россыпи omk-команд нет.
