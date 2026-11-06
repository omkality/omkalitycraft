# Исторический Linux-мир с актуальными правами

Полный возврат мира не должен возвращать отозванный OP, разбанивать игрока или
снова делать его союзником чужого привата. `omk.linux_restore_policy` накладывает
проверенную текущую политику на **новую остановленную** копию исторического мира.
Это закрытый data worker и лабораторная интеграция #33, не production restore
и не команда переключения работающего сервера.

## Что откуда берётся

| Данные | Источник |
| --- | --- |
| Мир, вещи, homes, claims | Выбранный исторический owner snapshot |
| `ops.json`, bans игроков/IP, whitelist | Текущий остановленный сервер, точные байты |
| `local/ftbutilities/ranks.txt` | Текущий сервер, точные байты |
| Флаг `white-list` | Текущий сервер |
| Остальные `server.properties`, включая пароли | Подготовленный новый runtime; не копируются из источника |
| Известные членства/владельцы/статусы/правила FTB | Текущий сервер, через адаптер закреплённых версий FTB |
| Drasl/аккаунты/сессии | Существующая актуальная авторизация; worker её не читает и не восстанавливает |

FTB-адаптер требует одинакового набора player/team records и стабильных
Name/UUID, team ID/UID/Type. Неизвестные изменения и несовместимые идентификаторы
блокируют операцию. Это не универсальное слияние любых версий или любых команд.
Версии/SHA-256 JAR проверяются на обоих runtime; правила описаны в
[переносе полномочий FTB](FTB_AUTHORITY_TRANSFER.md).

## Порядок и ограничения

1. Остановить свой лабораторный источник; сохранить свежую копию текущего мира.
   Проверить lifecycle, ownership и отдельные source/target/store volumes.
2. В новом Linux target выполнить raw initialize/stage выбранного снимка
   [Linux worker](LINUX_SERVER_PATHS.md). Backup writers остаются остановленными.
3. `stage-policy`: заново проверить snapshot и raw receipt, текущие права/FTB,
   runtime и reserve; построить ожидаемый результат до изменений.
4. Создать exclusive fsynced план, записать отдельные staging-файлы с readback,
   заменить их с проверкой исходных хешей. Сверить весь inventory мира: разрешены
   только ожидаемые изменения FTB. Повторно прочитать текущий источник и записать receipt.
5. Непосредственно перед Forge выполнить `verify-policy`: заново построить
   ожидаемый результат из snapshot и текущего readonly source, проверить все байты
   и inventory. Host повторяет lifecycle-check источника до/после helper.

При появлении policy-plan прежний raw verifier отказывает: им нельзя обойти
незаконченную операцию. Многофайловая замена не атомарна. Незавершённый target
не запускается и не применяется повторно; нужен новый отдельный target и разбор
ошибки. Worker сам серверы не запускает, не останавливает и данные не удаляет.

Источник и store монтируются readonly; helper без сети/Docker socket, root readonly,
1 CPU/512 МиБ. Windows получает TAR/ZIP без извлечения `con.dat` на NTFS.
План/receipt содержат хеши, а не пароли/токены или содержимое свойств.
Исходные конфиги и экспорты всё равно приватны.

Этот lab ограничен 512 МиБ мира, 128 МиБ одного ZIP-entry и 20 тысячами entries;
FTB — 1000 records, 2 МиБ на распакованную запись и 32 МиБ суммарно.
Проверка большого production-мира, эксплуатационный plan/apply, переключение
endpoint, scheduler, backup-window, общий storage budget и off-host copy остаются
отдельными задачами #33/#38. Само наличие marker не означает успешную приёмку.

## Команда и приватные материалы

`uv run omk lab dj2-linux-policy --server-source … --agent … --core … --mods-json …`
использует только новые изолированные volumes, настоящий Drasl и Linux DJ2,
протокольных LabPlayer. Это не графический клиент и не тест рабочего сервера.

В `.local/linux-policy-lab-<id>/` относительно корня проекта:

- `report.json` — проверки и cleanup;
- `source-checkpoint/world.tar` — исторический мир;
- `current-checkpoint/world.tar` — актуальный мир до восстановления;
- `current-policy-source/policy.tar` — актуальные списки, ranks и свойства;
- `backup-store/` — проверенная выгрузка двух owner snapshots;
- `policy-before-start/policy.tar` — политики и receipts закрытого target;
- `export/world-after.tar`, `replacement/export/world-after.tar` — миры после опыта;
- `.omk-admin/backups/` — cold-copy journals.

Внутри target: `.omk-current-policy-plan.json`, `.omk-current-policy-staged.json`,
`.omk-current-policy-writing/`. Сырые TAR/ZIP, аккаунты/сессии, исходные конфиги
не публикуются в Git/CDN/дистрибутиве. Для публичного протокола используются
обезличенные результаты и хеши.

## Приёмка 6 ноября 2026

Linux DJ2 2.23.4/Core 0.2.10: 19 native условий/3 старта,
25 независимых проверок. Исторические inventory/home/claims возвращены,
текущие ban/whitelist/deop/home quota/отзыв ally сохранены и проверены настоящими
соединениями/командами/ломанием блоков. Исходник неизменен; свои тома очищены,
stop 0/OOM=false. Отдельно 10 synthetic Linux FS/process checks: SIGKILL/гонка/ENOSPC.
Windows unit 977/11 skipped, Linux focused 285.
[Протокол](validation/dj2-linux-current-policy-2026-11-06.json).
