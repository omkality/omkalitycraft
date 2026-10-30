# GTNH: предварительная справка по командам

**Наш GTNH ещё не установлен и не проверен.** Версия профиля не выбрана, поэтому это
справка upstream, не перечень уже работающих возможностей сервера OmkalityCraft.

Изучен [ServerUtilities](https://github.com/GTNewHorizons/ServerUtilities) на commit
`7e113d6df879dd21556fad75dffbfb52c0e675fd` от доступного на 30.10.2026 состояния репозитория.
Это не утверждение, что именно этот commit входит в стабильную GTNH 2.8.4.

ServerUtilities переносит на 1.7.10 идеи FTB Utilities/Library. Общие понятия остаются:
команда игроков, приваты чанков, загрузка чанков, home/spawn/warp/tpa/back/rtp, ранги и
модерация. Точные команды и конфиги закрепим после выбора сборки и runtime-выгрузки.

## Основные соответствия

| Возможность | Изученный upstream ServerUtilities | DJ2 |
| --- | --- | --- |
| Число домов | `serverutilities.homes.max` | `ftbutilities.homes.max` |
| Home warmup/cooldown | `serverutilities.homes.warmup` / `.cooldown` | `ftbutilities.homes.warmup` / `.cooldown` |
| Spawn/warps/tpa/back/rtp | Аналогичные keys с префиксом `serverutilities` | Префикс `ftbutilities` |
| Лимит привата | `serverutilities.claims.max_chunks` | `ftbutilities.claims.max_chunks` |
| Лимит загрузки | `serverutilities.chunkloader.max_chunks` | `ftbutilities.chunkloader.max_chunks` |
| Файл рангов | `serverutilities/server/ranks.txt` | `local/ftbutilities/ranks.txt` |
| Главный конфиг | `serverutilities/serverutilities.cfg` | `config/ftbutilities.cfg` |
| Выгрузка прав | В upstream есть `/dump permissions` | В этой DJ2 такого универсального экспорта не зарегистрировано; используем наш диагностический снимок |
| Бэкапы | Внутри ServerUtilities, семейство `/backup` | Отдельный FTB Backups 1.1.0.1 |

Изученный upstream задаёт обычному игроку исходно 1 home, 100 claim-чанков, 50 загружаемых
чанков. Таймеры по умолчанию: warmup 5s у home/spawn/warp/tpa/back/rtp; cooldown home 5m,
spawn/warp 1m, tpa/back 3m, RTP 10m. В готовой GTNH конфигурация может отличаться —
эти значения нельзя выдавать за уже принятые лимиты нашего сервера.

## Что есть в коде, но ещё не проверено у нас

- Семейства `/home`, `/sethome`, `/delhome`, `/spawn`, `/warp`, `/setwarp`, `/delwarp`,
  `/tpa`, `/tpaccept`, `/back`, `/rtp`, `/chunks`, `/team`, `/ranks`.
- Модерация `/mute`, `/unmute`, косметические nick/rec, технические heal/fly/god/nbtedit.
- Дополнительные включаемые команды: выгрузка разрешений/статистики, vanish, поиск блока,
  предварительная генерация; они зависят от конфигурации и версии мода.
- Upstream `/backup start`, `/backup stop`, `/backup getsize`, `/backup list`,
  `/backup prune preview` описаны в [документации бэкапов](https://github.com/GTNewHorizons/ServerUtilities/blob/7e113d6df879dd21556fad75dffbfb52c0e675fd/wiki/Backups.md).
  Не переносить этот синтаксис в DJ2: там другой backup-мод.

В изученном `CmdSetWarp` создание точек всё ещё глобальное и OP, а не система личного
владения публичными warp. Поэтому наша задача с безопасными warp и лимитами не исчезает
от смены имени FTB Utilities на ServerUtilities.

После установки GTNH сюда добавим отдельный фактический реестр, конкретные permission
nodes, переопределения профиля и результаты тестов. DJ2 Java-мод Core для 1.12.2 не
считается автоматически совместимым с 1.7.10; понадобится соответствующий адаптер.
