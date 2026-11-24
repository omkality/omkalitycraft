# OmkalityCraft

[![Проверки dev](https://github.com/omkality/omkalitycraft/actions/workflows/checks.yml/badge.svg?branch=dev&event=push)](https://github.com/omkality/omkalitycraft/actions/workflows/checks.yml?query=branch%3Adev+event%3Apush)

Minecraft-сервер сообщества с русифицированной сборкой Divine Journey 2 2.23.4
на Minecraft 1.12.2 и Forge. Для регистрации нужно приглашение.

## Как начать играть

1. Скачайте лаунчер. [Windows x64](https://github.com/omkality/omkalitycraft/releases/latest/download/OmkalityCraft-windows-x64.zip) · [Linux x64](https://github.com/omkality/omkalitycraft/releases/latest/download/OmkalityCraft-linux-x64.zip) · [macOS Apple Silicon](https://github.com/omkality/omkalitycraft/releases/latest/download/OmkalityCraft-macos-arm64.zip)
2. Распакуйте архив целиком в папку, доступную для записи, и запустите
   `OmkalityCraft.exe` на Windows или `OmkalityCraft` на Linux и macOS.
   Для запуска Minecraft на Apple Silicon нужна [Rosetta 2](https://support.apple.com/ru-ru/102527).
3. Зарегистрируйтесь с приглашением или войдите в свой аккаунт. На карточке DJ2
   нажмите **«Скачать сборку»**, затем **«Играть»**. Лаунчер сам установит игру и Java.
4. В Minecraft выберите **«Сетевая игра» → «Divine Journey 2 RU»**. Запись сервера
   вернётся в список при следующем запуске Minecraft, если её удалить.

Лаунчер проверяет обновления при старте. Настройки, сессия и установленные
игровые файлы сохраняются при обновлении.

- [Системные требования](docs/CLIENT_REQUIREMENTS.md)
- [Команды и правила игры](docs/commands/dj2/README.md)
- [Журналы и файлы диагностики](docs/LOGGING.md)

## Для владельца и разработчиков

- [Терминал владельца, приглашения, модерация и вайп](docs/OWNER_TUI.md)
- [Развёртывание и обслуживание](deploy/README.md)
- [Сборка, публикация и автообновление](docs/RELEASES.md)
- [Структура проекта и локальные проверки](docs/DEVELOPMENT.md)
- [История изменений](CHANGELOG.md)
