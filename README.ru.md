<p align="center">
    <img src="https://repository-images.githubusercontent.com/559574279/ac1f8317-c07c-4c0f-a4e4-c49ae01237cd" alt="Open Weather Bot" width="640">
</p>

<p align="center">
    <a href="https://www.python.org/downloads/release/python-3119/">
        <img src="https://img.shields.io/badge/python-v3.11-informational" alt="python version">
    </a>
    <a href="https://pypi.org/project/aiogram/2.25.2/">
        <img src="https://img.shields.io/badge/aiogram-v2.25.2-informational" alt="aiogram version">
    </a>
    <a href="https://pypi.org/project/aiohttp/3.8.6/">
        <img src="https://img.shields.io/badge/aiohttp-v3.8.6-informational" alt="aiohttp version">
    </a>
    <a href="https://pypi.org/project/aioredis/1.3.1/">
        <img src="https://img.shields.io/badge/aioredis-v1.3.1-informational" alt="aioredis version">
    </a>
    <a href="https://pypi.org/project/asyncpg/0.31.0/">
        <img src="https://img.shields.io/badge/asyncpg-v0.31.0-informational" alt="asyncpg version">
    </a>
    <a href="https://pypi.org/project/APScheduler/3.11.2/">
        <img src="https://img.shields.io/badge/APScheduler-v3.11.2-informational" alt="APScheduler version">
    </a>
    <a href="https://pypi.org/project/environs/14.5.0/">
        <img src="https://img.shields.io/badge/environs-v14.5.0-informational" alt="environs version">
    </a>
    <a href="https://pypi.org/project/Pillow/12.0.0/">
        <img src="https://img.shields.io/badge/Pillow-v12.0.0-informational" alt="Pillow version">
    </a>
    <a href="https://pypi.org/project/tzlocal/5.3.1/">
        <img src="https://img.shields.io/badge/tzlocal-5.3.1-informational" alt="tzlocal version">
    </a>
</p>

<p align="center">
    <a href="https://github.com/psf/black">
        <img alt="Code style: black" src="https://img.shields.io/badge/code%20style-black-black.svg">
    </a>
    <a href="https://github.com/rin-gil/open-weather-bot/actions/workflows/tests.yml">
        <img src="https://github.com/rin-gil/open-weather-bot/actions/workflows/tests.yml/badge.svg" alt="Linter">
    </a>
    <a href="https://github.com/rin-gil/open-weather-bot/actions/workflows/codeql.yml">
        <img src="https://github.com/rin-gil/open-weather-bot/actions/workflows/codeql.yml/badge.svg" alt="CodeQL">
    </a>
    <a href="https://github.com/rin-gil/open-weather-bot/blob/master/LICENCE.md">
        <img src="https://img.shields.io/badge/licence-MIT-success" alt="MIT licence">
    </a>
</p>

<p align="right">
    <a href="https://github.com/iRingil/open-weather-bot/blob/master/README.md">
        <img src="https://raw.githubusercontent.com/iRingil/iRingil/main/assets/img/icons/flags/united-kingdom_24x24.png" alt="En"></a>
    <a href="https://github.com/iRingil/open-weather-bot/blob/master/README.ua.md">
        <img src="https://raw.githubusercontent.com/iRingil/iRingil/main/assets/img/icons/flags/ukraine_24x24.png" alt="Ua">
    </a>
</p>

## Open Weather Bot

Телеграм бот, показывающий прогноз погоды.
Рабочая версия доступна по ссылке [@OpenWeatherSmartBot](https://t.me/OpenWeatherSmartBot)

### Возможности

* Поиск города по названию или координатам
* Показ текущей погоды и прогноза на 24 часа
* Обновление прогноза погоды каждые 3 часа

### Установка

```
git clone https://github.com/iRingil/open-weather-bot.git
cd open-weather-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
mv .env.dist .env
```

<img align="right" width="300" src="https://raw.githubusercontent.com/iRingil/iRingil/refs/heads/main/assets/img/projects/OpenWeatherBot/screenshot_ru.png" alt="Главный экран open-weather-bot">

### Настройка и запуск

* Зарегистрируйте нового бота у [@BotFather](https://t.me/BotFather) и скопируйте полученный токен
* Вставьте токен бота в файл .env
* Зарегистрируйте учетную запись на сайте [OpenWeatherMap](https://home.openweathermap.org/users/sign_in)
* Создайте [API ключ](https://home.openweathermap.org/api_keys) и скопируйте его в файл .env
* Вставьте свой id Телеграм в файл .env
* Узнать свой id можно, например, написав боту [@getmyid_bot](https://t.me/getmyid_bot)
* Запуск бота через файл bot.py `python bot.py`

### Локализация

* С версии 1.1.0 в бот добавлена локализация для английского, украинского и русского языка
* Для добавления перевода на свой язык, сделайте следующее:
  1. перейдите в папку с ботом
  2. активируйте виртуальное окружение:

     `source venv/bin/activate`
  3. создайте файл перевода на ваш язык, где **{language}** - код языка по стандарту [ISO 639-1](https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes)

     `pybabel init --input-file=tgbot/locales/tgbot.pot --output-dir=tgbot/locales --domain=tgbot --locale={language}`
  4. переведите строки в файле **locales/{language}/LC_MESSAGES/tgbot.po**
  5. скомпилируйте перевод командой:

     `pybabel compile --directory=tgbot/locales --domain=tgbot`
  6. перезапустите бота
* При изменениях строк для перевода в коде, вам нужно будет полностью пересоздать и скомпилировать файлы 
  перевода для всех локализаций:
  1. извлечь строки для перевода из кода:

     `pybabel extract --input-dirs=./tgbot --output-file=tgbot/locales/tgbot.pot --sort-by-file --project=open-weather-bot`
  2. создать файлы перевода для всех локализаций:

     `pybabel init --input-file=tgbot/locales/tgbot.pot --output-dir=tgbot/locales --domain=tgbot --locale={language}`
  3. скомпилировать переводы:

     `pybabel compile --directory=tgbot/locales --domain=tgbot`
* Более подробно об этом можно прочитать в примере из документации [aiogram](https://docs.aiogram.dev/en/latest/examples/i18n_example.html)

### Разработчики

* [Ringil](https://github.com/iRingil)

### Лицензии

* Исходный код **Open Weather Bot** доступен по лицензии [MIT](https://github.com/iRingil/open-weather-bot/blob/master/LICENCE.md)
* Данные о прогнозе погоды предоставлены сервисом [OpenWeather](https://openweathermap.org/)
* Иконки погоды от [www.wishforge.games](https://freeicons.io/profile/2257) c [freeicons.io](https://freeicons.io/)
