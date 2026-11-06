# Имена файлов бэкапов Linux-сервера

Ник `CON` проходит текущую проверку регистрации. В Linux FTBLib сохраняет его как
`data/ftb_lib/players/con.dat`; это обычный файл. Windows резервирует такие basename,
поэтому прежняя переносимая проверка отклоняла весь снимок мира.

## Политики архива

`validate_inventory`, `verify_archive`, `BackupStore` и inventory остановленного
мира поддерживают явный `path_policy="linux-server"`. Он разрешает Windows-reserved
basename (`CON`, `NUL`, `AUX`, `COM1` и подобные) как непрозрачные имена Linux-файлов.
По умолчанию остаётся `portable`: прежние ограничения не меняются. Traversal,
абсолютные пути, ссылки/специальные ZIP-entries, дубли/регистровые коллизии,
двоеточия/обратные слеши/управляющие символы, завершающие точки/пробелы, лимиты
числа файлов/размеров/хешей/CRC остаются проверяемыми и в новом режиме.

Linux owner cold worker использует новую политику явно. Она не управляется
пользователем лаунчера или произвольным env override. `owner.json` нового store:
schema 2 с `path_policy=linux-server`. Portable store сохраняет schema 1.
Чтение хранилища с другой политикой отказывает: старые каталоги не усыновляются
и не переписываются автоматически. Для прежних копий нужен отдельный проверенный
перенос в новое хранилище; эта задача не выполняет миграцию существующих данных.

ZIP/manifest Linux-хранилища можно читать и сверять по хешам на Windows, не извлекая
отдельные файлы мира. Generic portable API и старые portable labs остаются прежними.

## Восстановление в Linux

`omk.linux_world_restore` — закрытый data worker для Docker, не команда переключения
рабочего сервера. Владелец монтирует проверенный store readonly и отдельный новый
остановленный Linux-том с подготовленным runtime. Helper без сети/Docker socket;
в тесте 1 CPU/512 МиБ, root read-only. Host проверяет ownership labels, разные тома
и отсутствие активного контейнера на целевом томе. Backup writers должны быть остановлены.

Порядок: initialize нового target с operation/world → проверенный выбор snapshot/hash
→ exclusive план → извлечение в **отсутствующий** каталог мира → полный inventory/hash/CRC
readback → подтверждение. До записи проверяется свободное место с reserve.
Файлы/каталоги синхронизируются. Перед игровым стартом verify повторяет проверки
и требует связанный план/подтверждение. Сам worker сервер не запускает.

Извлечение разрешено только в Linux. Windows-хост получает TAR/ZIP как непрозрачные
файлы; имена вроде `con.dat` появляются лишь внутри Linux-тома. Нет extractall,
перезаписи существующего мира, удаления исходника или автоматического повтора
частичной попытки. При ошибке новая копия может быть частичной и остаётся без
подтверждения. Это не атомарная замена всего мира и не production restore/cutover.
Drasl, текущие bans/OP/ranks/FTB-полномочия и переключение сервиса требуют отдельной
эксплуатационной процедуры #33/#38. Старый host-extract recovery lab остаётся portable;
его нельзя объявлять поддерживающим такие имена на NTFS.

## Проверка и папки

`omk lab dj2-linux-paths` принимает явные `--server-source`, `--agent`, `--core`,
`--mods-json`. Использует только свежие Drasl/game/backup volumes, аккаунт `CON`,
два настоящих старта DJ2 и протокольный LabPlayer. Не графический клиент.

Материалы в `.local/linux-paths-lab-<id>/` относительно корня проекта:

- `report.json`, `source-checkpoint/world.tar` — исходный остановленный мир;
- `backup-store/` — проверенная выгрузка store; `con.dat` остаётся внутри ZIP;
- `replacement/export/world-after.tar` — данные после игры в восстановленной копии;
- `.omk-admin/backups/` — owner cold-copy journal без passwords/tokens.

Внутри нового Linux data volume до игрового старта создаются
`.omk-world-stage-owner.json`, `.omk-world-stage-plan.json`, `.omk-world-staged.json`.
Они связывают operation/world/snapshot/hash/inventory. Исходные аккаунты/сессии и
сырые экспорты приватны, не входят в Git/CDN/дистрибутив лаунчера.

## Приёмка 6 ноября 2026

DJ2 2.23.4/Core 0.2.10: 9 native условий/два старта, 13 независимых проверок
265 файлов. CON зарегистрировался, вошёл, сохранил `con.dat`, прошёл owner backup и
Linux restore, повторно вошёл с 7 изумрудами и работающим home. Исходник неизменен;
все свои game/auth/backup тома очищены, stop 0/OOM=false. Worker с последними
дополнительными проверками повторно восстановил тот же снимок в новом Linux volume.
Unit: Windows 967/10 skipped, Linux 274; 13 real Docker cold CLI регрессий.
[Обезличенный протокол](validation/dj2-linux-server-paths-2026-11-06.json).
