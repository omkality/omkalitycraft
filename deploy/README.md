# Развёртывание OmkalityCraft

Запускайте каждый Compose из корня checkout с явным файлом. Для рабочего
окружения укажите абсолютный путь к приватному env-файлу и используйте прежнее
имя проекта при обновлении существующего стека.

| Потребитель | Файл и имя проекта |
| --- | --- |
| API/CDN | [api/compose.yaml](api/compose.yaml), имя omkalitycraft-api, [пример env](api/example.env) |
| Drasl | [auth/compose.yaml](auth/compose.yaml), рабочее имя omk-auth, [пример env](auth/example.env) |
| TLS ingress | [ingress/compose.yaml](ingress/compose.yaml), рабочее имя omk-ingress |
| Метрики | [metrics/compose.yaml](metrics/compose.yaml), рабочее имя omk-metrics |
| Локальные стенды | [auth-lab](auth-lab/compose.yaml), [tui-lab](tui-lab/compose.yaml), изолированные проекты |

Шаблоны для [терминала владельца и копий](owner/), [Forge](game/) и
[внешнего хранения копий](offsite/) находятся в отдельных каталогах.
Для рабочих стеков сохраняйте существующие приватные пути и имена томов.

Порядок запуска и восстановления описан в
[инструкции закрытого переноса](../docs/LAUNCH_READINESS.md#закрытый-перенос-на-vps).
