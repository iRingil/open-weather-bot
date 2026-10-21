<p align="center">
    <img src="https://repository-images.githubusercontent.com/559574279/ac1f8317-c07c-4c0f-a4e4-c49ae01237cd" alt="Open Weather Bot" width="640">
</p>
<p align="center">
    <a href="https://www.python.org/downloads/release/python-3130/">
        <img src="https://img.shields.io/badge/python-v3.13-informational" alt="python version">
    </a>
    <a href="https://pypi.org/project/APScheduler/3.11.3/">
        <img src="https://img.shields.io/badge/APScheduler-v3.11.3-informational" alt="APScheduler version">
    </a>
    <a href="https://pypi.org/project/Jinja2/3.1.6/">
        <img src="https://img.shields.io/badge/Jinja2-v3.1.6-informational" alt="Jinja2 version">
    </a>
    <a href="https://pypi.org/project/Pillow/13.0.0/">
        <img src="https://img.shields.io/badge/Pillow-v13.0.0-informational" alt="Pillow version">
    </a>
    <a href="https://pypi.org/project/aiogram/3.31.0/">
        <img src="https://img.shields.io/badge/aiogram-v3.31.0-informational" alt="aiogram version">
    </a>
    <a href="https://pypi.org/project/aiohttp/3.14.5/">
        <img src="https://img.shields.io/badge/aiohttp-v3.14.5-informational" alt="aiohttp version">
    </a>
    <a href="https://pypi.org/project/asyncpg/0.32.0/">
        <img src="https://img.shields.io/badge/asyncpg-v0.32.0-informational" alt="asyncpg version">
    </a>
    <a href="https://pypi.org/project/babel/2.18.0/">
        <img src="https://img.shields.io/badge/babel-v2.18.0-informational" alt="babel version">
    </a>
    <a href="https://pypi.org/project/environs/15.2.0/">
        <img src="https://img.shields.io/badge/environs-v15.2.0-informational" alt="environs version">
    </a>
    <a href="https://pypi.org/project/loguru/0.7.3/">
        <img src="https://img.shields.io/badge/loguru-v0.7.3-informational" alt="loguru version">
    </a>
    <a href="https://pypi.org/project/orjson/3.13.0/">
        <img src="https://img.shields.io/badge/orjson-v3.13.0-informational" alt="orjson version">
    </a>
    <a href="https://pypi.org/project/pydantic/2.13.5/">
        <img src="https://img.shields.io/badge/pydantic-v2.13.5-informational" alt="pydantic version">
    </a>
    <a href="https://pypi.org/project/redis/8.1.0/">
        <img src="https://img.shields.io/badge/redis-v8.1.0-informational" alt="redis version">
    </a>
</p>
<p align="center">
    <a href="https://github.com/psf/black">
        <img alt="Code style: black" src="https://img.shields.io/badge/code%20style-black-black.svg">
    </a>
    <a href="https://github.com/iRingil/open-weather-bot/actions/workflows/mypy.yml">
        <img src="https://github.com/iRingil/open-weather-bot/actions/workflows/mypy.yml/badge.svg" alt="Mypy">
    </a>
    <a href="https://github.com/iRingil/open-weather-bot/actions/workflows/pylint.yml">
        <img src="https://github.com/iRingil/open-weather-bot/actions/workflows/pylint.yml/badge.svg" alt="Pylint">
    </a>
    <a href="https://github.com/iRingil/open-weather-bot/actions/workflows/pytest.yml">
        <img src="https://github.com/iRingil/open-weather-bot/actions/workflows/pytest.yml/badge.svg" alt="Pytest">
    </a>
    <a href="https://github.com/iRingil/open-weather-bot/actions/workflows/codeql.yml">
        <img src="https://github.com/iRingil/open-weather-bot/actions/workflows/codeql.yml/badge.svg" alt="CodeQL">
    </a>
    <a href="https://github.com/iRingil/open-weather-bot/blob/master/LICENCE.md">
        <img src="https://img.shields.io/badge/licence-MIT-success" alt="MIT licence">
    </a>
</p>

# Open Weather Bot

A Telegram bot that shows the weather forecast for a city of your choice and keeps it up to date.

<img align="right" width="300" src="https://raw.githubusercontent.com/iRingil/iRingil/refs/heads/main/assets/img/projects/OpenWeatherBot/screenshot_en.png" alt="open-weather-bot home screen">

### Features

- **City search** by name or by sending your location.
- **24-hour forecast image** - temperature, weather icon and wind speed in 3-hour steps, in the
  city's local time.
- **Current weather** - temperature, feeling, humidity, dew point, wind and gusts, pressure,
  visibility, precipitation, sunrise and sunset.
- **Automatic updates every 3 hours**, in the same single message - the whole dialog with the bot
  lives in one window.
- **Metric or imperial units.**
- **English, Russian and Ukrainian** interface (any other language falls back to English).

### Try it out

The running bot: [@OpenWeatherSmartBot](https://t.me/OpenWeatherSmartBot)

### Requirements

- Python 3.13
- PostgreSQL (users and the monthly API request counter)
- Redis (FSM storage)
- An [OpenWeatherMap](https://home.openweathermap.org/users/sign_in) account with an
  [API key](https://home.openweathermap.org/api_keys) - the free plan is enough: the bot never
  sends more than 55 requests per minute (the limit is 60), and requests each forecast only once per location.

### Installation

```bash
git clone https://github.com/iRingil/open-weather-bot.git
cd open-weather-bot
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt
pybabel compile --directory=src/locales
cp src/.env.example src/.env
```

### Setup and run

1. Register a new bot with [@BotFather](https://t.me/BotFather) and put its token into `BOT_TOKEN`.
2. Put your OpenWeatherMap API key into `WEATHER_API_TOKEN`.
3. Put your Telegram ID into `ADMIN_IDS` (comma-separated for several admins) - you can find it
   out, for example, with [@getmyid_bot](https://t.me/getmyid_bot). Admins get the `/stats`
   command and start/stop notifications.
4. Fill in the PostgreSQL and Redis credentials. Set `USE_POSTGRES_SOCKET` / `USE_REDIS_SOCKET` to
   `True` to connect over a Unix socket instead of host and port.
5. The bot uses long polling by default. To use a webhook, set `USE_WEBHOOK=True` and fill in the
   `WEBHOOK_*` / `WEBAPP_*` variables; Telegram's requests are checked against `WEBHOOK_TOKEN`.
6. Run the bot: `python src/app.py`

Logs are written to `src/logs/open-weather-bot.log`; set `DEBUG=False` in production.
`infrastructure/` holds a reference systemd unit and a logrotate config for a Linux server.

### Localization

Every user-facing text lives in a Jinja2 template under `src/templates/`; translations are Babel
catalogs in `src/locales/{language}/LC_MESSAGES/messages.po`. The compiled `.mo` files are not kept
in the repository - compile them after every checkout or update.

From the repository root, after changing the texts of the templates:

```bash
pybabel extract -F infrastructure/localization/babel.cfg --input-dirs=src --output-file=src/locales/messages.pot --width=120 --sort-by-file
pybabel update --input-file=src/locales/messages.pot --output-dir=src/locales --width=120
# translate the new or changed strings in src/locales/*/LC_MESSAGES/messages.po
pybabel compile --directory=src/locales
```

To add a language, run `pybabel init --input-file=src/locales/messages.pot --output-dir=src/locales
--locale={language}` with an [ISO 639-1](https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes) code,
translate the new catalog and compile it. On Windows, the scripts in `infrastructure/localization/`
do the same.

### Development

```bash
pip install -r src/requirements-dev.txt
pylint --rcfile=pyproject.toml --recursive=y src tests
mypy --config-file=pyproject.toml src tests
pytest -c pyproject.toml tests --cov --cov-fail-under=100
black -l 120 src tests
```

### Developers

* [Ringil](https://github.com/iRingil)

### Licenses

* The source code of **Open Weather Bot** is available under the [MIT](https://github.com/iRingil/open-weather-bot/blob/master/LICENCE.md) license
* Weather data provided by [OpenWeather](https://openweathermap.org/)
* Weather icons by [www.wishforge.games](https://freeicons.io/profile/2257) on [freeicons.io](https://freeicons.io/)
