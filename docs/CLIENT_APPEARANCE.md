# Оформление лаунчера и DJ2

В лаунчере используются тёмный фон `#0b0d10`, панели `#12161b` и светлые элементы
`#dbe7f2`. Основной шрифт — Rubik Bold, ник отображается шрифтом Monocraft.
В небольшом окне форма входа и регистрации прокручивается.

## Меню и запуск Minecraft

В подписанной сборке DJ2 `2.23.4-omk.16` для Windows, Linux и Apple Silicon
включены главное меню с пейзажами, общий вид стандартных экранов и заставка
Forge с рудой OmkalityCraft. Отдельные интерфейсы модов используют свои текстуры.

- Custom Main Menu и ResourceLoader задают вид меню и стандартных кнопок.
- Ender Modpack Tweaks задаёт иконку и заголовок окна
  `OmkalityCraft · Divine Journey 2 · <версия сборки>`. В конфиге выключена
  рекомендуемая запись Pixel Gaming. Запись OmkalityCraft добавляется из
  подписанного профиля; остальные сохранённые серверы доступны игроку.
- `config/splash.properties` задаёт цвета загрузки Forge. Для своего логотипа
  подписанный профиль передаёт `-Domkality.appearance.forge112=true` в
  OmkalityClient. Для раннего экрана до загрузки Forge используется штатная
  заставка Minecraft.

На Windows в `2.23.4-omk.16` проверены заставка Forge, главное меню, настройки,
звук, список серверов, выбор мира и список модов при масштабе интерфейса 2.
В списке серверов по-прежнему видна кнопка `Oauth Login` из мода OAuth 1.06.4.
Для входа на OmkalityCraft используются аккаунт проекта и лаунчер.
Проверки значка на панели задач и в Dock ведутся в [#64][branding].

## Начальные настройки

[Профиль DJ2](../profiles/client-defaults/dj2.json) задаёт яркость 100%, угол
обзора 80°, масштаб интерфейса 2, выключенные покачивание камеры и автопрыжок.
При первом запуске лаунчер заполняет отсутствующие параметры. Пользовательские
значения в `options.txt` сохраняются при обновлении, а копия перед дополнением
попадает в `.omk-defaults-backups/` внутри папки игры. Пресет JourneyMap
применяется при отсутствии её файла настроек.

Подписанная сборка включает [FullscreenWindowed][borderless]. На Windows
в безрамочном полноэкранном режиме F11 курсор из меню или инвентаря можно
переместить на соседний монитор. Настройки монитора в `config/fw.cfg`
хранятся в папке игрока. [Протокол проверки на Windows][fullscreen-validation].

## Подготовка оформления

Для воспроизводимого набора файлов используется `scripts/build_client_appearance.py`.
Пример для DJ2 2.23.4 в PowerShell.

```powershell
python scripts/build_client_appearance.py `
  --output .local/appearance-review-new `
  --pack-version 2.23.4 `
  --legacy-backgrounds <архивный-клиент>/resources/mainmenu/background `
  --modpack-config <исходный-клиент>/config/endermodpacktweaks/modpack.cfg `
  --minecraft-jar <исходный-клиент>/versions/1.12.2/1.12.2.jar
```

Каталог вывода должен быть новым. Без `--legacy-backgrounds` используется тёмный
фон. С `--minecraft-jar` генератор сверяет SHA-256 и заменяет три полосы кнопок
в текстуре, сохраняя остальные пиксели, включая игровой HUD. `appearance-review.json`
содержит хеши входов и результата. Файлы игры и сгенерированные текстуры
с её пикселями хранятся вне Git. Установка в тестовый профиль и [публикация
подписанного профиля](RELEASES.md) выполняются отдельно.

[История внедрения и проверки][appearance-issue].

[appearance-issue]: https://github.com/omkality/omkalitycraft/issues/117
[branding]: https://github.com/omkality/omkalitycraft/issues/64
[borderless]: ../profiles/client-addons/forge-1.12.2/borderless.json
[fullscreen-validation]: validation/client-cursor-2026-11-14.json
