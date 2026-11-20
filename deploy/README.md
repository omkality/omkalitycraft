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

Корневой docker-compose.yml переехал в deploy/api/compose.yaml,
а deploy/server-status.example.env — в deploy/api/server-status.example.env.
Имена остальных перенесённых примеров прежние. Ищите их в deploy/owner/
для owner CLI и резервных копий, deploy/game/ для игрового процесса,
deploy/offsite/ для offsite-копий и deploy/ingress/ для входного прокси.
Отдельно скопированные приватные конфиги сохраняют свои рабочие пути.
Имена Compose-сетей и томов Drasl, ingress и метрик сохраняются при выборе
прежнего имени проекта.

Порядок запуска и восстановления описан в
[инструкции закрытого переноса](../docs/LAUNCH_READINESS.md#закрытый-перенос-на-vps).
