# Drasl с атомарным использованием приглашений

Это Drasl 4.0.0 с одним небольшим исправлением транзакции приглашения,
образ `omkalitycraft-drasl:4.0.0-omk.1`. Пароли, токены, скины, Yggdrasil API
и схема БД остаются у Drasl; отдельная система авторизации не добавляется.
Версия в upstream API по-прежнему 4.0.0; вариант образа определяется tag/labels
и записанным digest, а не только этой строкой.

Файл `one-use-invites.patch` требует, чтобы в транзакции создания пользователя
была действительно удалена одна строка приглашения. Если другой запрос уже
использовал или отозвал код, откатываются и пользователь, и игровой профиль.
Код после регистрации удалён; пожизненной связи с аккаунтом не создаём.

## Закреплённые входы

- [Upstream Drasl v4.0.0](https://github.com/unmojang/drasl/tree/0fe488c087bbe792485e9c5dae751c6e5fbdc380),
  commit `0fe488c087bbe792485e9c5dae751c6e5fbdc380`.
- Source tar SHA256 `cc6196dbd538e6e17d3d22d180697673b607f585603f4ee72cebeb4dff615493`;
  Docker проверяет hash до распаковки, затем `git apply --check` перед исправлением.
- Go 1.26.4: `sha256:f96cc555eb8db430159a3aa6797cd5bae561945b7b0fe7d0e284c63a3b291609`.
- Upstream runtime/assets: `unmojang/drasl:4.0.0@sha256:d02f57bda0f0840ab6a2d6c9e167b923c71d4c7d7c9ef322c8ffce44854df6ad`.

Статический Go/SQLite binary собирается с readonly go.mod/go.sum; assets и сертификаты
берутся из закреплённого официального образа. Nix-путь DataDirectory относится именно
к этому image digest. При обновлении Drasl его необходимо проверить заново, вместе
с API/скинами и конкурентной одноразовостью. Отсутствие применимости patch останавливает
сборку. Удалять patch ради успешной сборки нельзя.

Drasl распространяется под GPLv3: лицензия/уведомления upstream сохранены в базовом
образе, соответствующие исходники закреплены ссылкой выше, полное локальное изменение
содержится в patch. Производный образ не загружается в публичный registry этим процессом.

## Локальный стенд и CI

```powershell
docker compose -f deploy/auth-lab/compose.yaml build --pull
uv run omk lab auth smoke
uv run omk lab auth expiry
uv run omk lab admin smoke
```

Compose использует собранный образ без fallback на неизменённый upstream.
Это отдельный development Drasl на loopback с одноразовыми аккаунтами, не production.
Базы/миры владельца команды не принимают. CI также собирает exact-source образ;
runtime остаётся Linux Docker. Пароли/управляющие ключи не включаются в build context.

[Правило приглашений и результаты](../../docs/INVITATIONS.md).
