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
    <a href="https://pypi.org/project/redis/7.1.0/">
        <img src="https://img.shields.io/badge/redis-v7.1.0-informational" alt="redis version">
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
    <a href="https://github.com/rin-gil/open-weather-bot/blob/master/README.ruiRingil">
        <img src="https://raw.githubusercontent.com/rin-gil/rin-gil/main/assets/img/icons/flags/russia_24x24.png" alt="Ru"></a>
    <a href="https://github.com/rin-gil/open-weather-bot/blob/master/README.uaiRingil">
        <img src="https://raw.githubusercontent.com/rin-gil/rin-gil/main/assets/img/icons/flags/ukraine_24x24.png" alt="Ua">
    </a>
</p>

## Open Weather Bot

Telegram bot that shows the weather forecast.
The working version is available at [@OpenWeatherSmartBot](https://t.me/OpenWeatherSmartBot)

### Features

* City search by name or coordinates
* 24-hour weather and forecast display
* Updating weather forecast every 3 hours

### Installation

```
git clone https://github.com/rin-gil/open-weather-bot.git
cd open-weather-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
mv .env.dist .env
```

<img align="right" width="300" src="https://raw.githubusercontent.com/iRingil/iRingil/refs/heads/main/assets/img/projects/OpenWeatherBot/screenshot_en.png" alt="open-weather-bot home screen">

### Setup and run

* Register a new bot with [@BotFather](https://t.me/BotFather) and copy the received token
* Paste the bot's token into the .env file
* Register an account at [OpenWeatherMap](https://home.openweathermap.org/users/sign_in)
* Create [API key](https://home.openweathermap.org/api_keys) and copy it to .env file
* Paste your Telegram id into the .env file
* Find out your id, for example, by writing bot [@getmyid_bot](https://t.me/getmyid_bot)
* Launch the bot via the bot.py file `python bot.py`

### Localization

* Since version 1.1.0 the bot added localization for English, Ukrainian and Russian
* To add a translation in your language, do the following:
  1. go to the folder with the bot
  2. activate the virtual environment:

     `source venv/bin/activate`
  3. create a translation file for your language, where **{language}** is the [ISO 639-1](https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes) language code

     `pybabel init --input-file=tgbot/locales/tgbot.pot --output-dir=tgbot/locales --domain=tgbot --locale={language}`
  4. translate the lines in the file **locales/{language}/LC_MESSAGES/tgbot.po**
  5. compile the translation with the command:

     `pybabel compile --directory=tgbot/locales --domain=tgbot`
  6. restart the bot
* If you change the lines to be translated in the code, you will need to completely recreate and compile the 
  translation files for all localizations:
  1. extract strings to be translated from the code:

     `pybabel extract --input-dirs=./tgbot --output-file=tgbot/locales/tgbot.pot --sort-by-file --project=open-weather-bot`
  2. create translation files for all localizations:

     `pybabel init --input-file=tgbot/locales/tgbot.pot --output-dir=tgbot/locales --domain=tgbot --locale={language}`
  3. compile translations:

     `pybabel compile --directory=tgbot/locales --domain=tgbot`
* You can read more about this in the example from the documentation of [aiogram](https://docs.aiogram.dev/en/latest/examples/i18n_example.html)

### Developers

* [Ringil](https://github.com/iRingil)

### Licenses

* The source code of **Open Weather Bot** is available under the [MIT](https://github.com/rin-gil/open-weather-bot/blob/master/LICENCEiRingil) license
* Weather data provided by [OpenWeather](https://openweathermap.org/)
* Weather icons by [www.wishforge.games](https://freeicons.io/profile/2257) on [freeicons.io](https://freeicons.io/)
