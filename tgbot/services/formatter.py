"""Formats weather data into the required view."""

from math import log

from tgbot.middlewares.localization import i18n
from tgbot.services.classes import CurrentWeatherData

__all__: tuple[str] = ("FormatWeather",)

_ = i18n.gettext  # Alias for gettext method


class FormatWeather:
    """A class for formatting weather data."""

    @staticmethod
    async def correct_user_input(raw_city_name: str) -> str:
        """
        Removes everything from the city_name except letters, spaces and hyphens.

        :param raw_city_name: Raw city name, inputted by user.
        :return: Formated city name.
        """
        processed_string: str = ""
        for char in raw_city_name[:72]:  # Cut raw_city_name to 72, because this is max length of the city name
            if char.isalpha() or char == "-":
                processed_string += char
            elif char.isspace() and (not processed_string or not processed_string[-1].isspace()):
                processed_string += char
        return processed_string

    @staticmethod
    async def _get_weather_emoji(weather_code: int) -> str:
        """
        Returns emoji by weather code from OpenWeatherMap.

        :param weather_code: Weather code.
        :return: Corresponding emoji.
        """
        if weather_code in (800,):  # clear
            weather_emoji: str = "☀"
        elif weather_code in (801,):  # light clouds
            weather_emoji = "🌤"
        elif weather_code in (803, 804):  # clouds
            weather_emoji = "🌥"
        elif weather_code in (802,):  # scattered clouds
            weather_emoji = "☁"
        elif weather_code in (500, 501, 502, 503, 504):  # rain
            weather_emoji = "🌦"
        elif weather_code in (300, 301, 302, 310, 311, 312, 313, 314, 321, 520, 521, 522, 531):  # drizzle
            weather_emoji = "🌧"
        elif weather_code in (200, 201, 202, 210, 211, 212, 221, 230, 231, 232):  # thunderstorm
            weather_emoji = "⛈"
        elif weather_code in (511, 600, 601, 602, 611, 612, 613, 615, 616, 620, 621, 622):  # snow
            weather_emoji = "🌨"
        elif weather_code in (701, 711, 721, 731, 741, 751, 761, 762, 771, 781):  # atmosphere
            weather_emoji = "🌫"
        else:  # default
            weather_emoji = "🌀"
        return weather_emoji

    @staticmethod
    async def _calculate_dew_point(temp: int, humidity: int) -> int:
        """
        Calculates the surface temperature at which condensation occurs (dew point).

        :param temp: Temperature.
        :param humidity: Humidity.
        :return:
        """
        const_a: float = 17.27
        const_b: float = 237.7
        gamma: float = (const_a * temp) / (const_b + temp) + log(humidity / 100)
        return round((const_b * gamma) / (const_a - gamma))

    async def format_current_weather(
        self, weather_data: CurrentWeatherData, units: str, city: str, lang_code: str
    ) -> str:
        """
        Returns the current weather data in the desired form.

        :param weather_data: CurrentWeatherData object.
        :param units: Weather measure units.
        :param city: Current city.
        :param lang_code: User language code.
        :return: Formatted weather data.
        """
        # Defining measurement unit signatures
        if units == "metric":
            temp_units: str = "°C"
            wind_units: str = "m/s"
            precip_units: str = "mm"
            vis_units: str = "km"
        else:
            temp_units = "°F"
            wind_units = "mph"
            precip_units = "in"
            vis_units = "mi"
        # Obtaining required values
        emoji: str = await self._get_weather_emoji(weather_code=weather_data.weather_code)
        dew_point: int = await self._calculate_dew_point(temp=weather_data.temp, humidity=weather_data.humidity)
        # Obtaining optional values
        precipitation: str = (
            (
                f", <b>{weather_data.precipitation} {precip_units} </b>"
                + _("of precipitation in one hour", locale=lang_code)
                + ""
            )
            if weather_data.precipitation
            else ""
        )
        wind_gust: str = (
            ", " + _("gusts to", locale=lang_code) + f": <b>{weather_data.gust} {wind_units}</b>"
            if weather_data.gust
            else ""
        )
        visibility: str = (
            ("🌫️ " + _("Visibility", locale=lang_code) + f": <b>{weather_data.visibility} {vis_units}</b>\n\n")
            if weather_data.visibility
            else ""
        )
        # Forming the final string with weather information
        current_weather: str = (
            f"<b>{city}, {weather_data.time}</b>\n"
            + f"{emoji} {weather_data.weather_description}{precipitation}\n\n"
            + f"🌡 <b>{weather_data.temp}{temp_units}</b>, "
            + _("feels like", locale=lang_code)
            + f" <b>{weather_data.feels_like}{temp_units}</b>\n\n"
            + "💦 "
            + _("Humidity", locale=lang_code)
            + f": <b>{weather_data.humidity}%</b>, "
            + _("Dew point", locale=lang_code)
            + f": <b>{dew_point}{temp_units}</b>\n"
            + "💨 "
            + _("Wind speed", locale=lang_code)
            + f": <b>{weather_data.wind_speed} {wind_units}</b>{wind_gust}\n"
            + "🌡 "
            + _("Pressure", locale=lang_code)
            + f": <b>{weather_data.pressure} hPa</b>\n"
            + f"{visibility}"
            + "🌅 "
            + _("Sunrise", locale=lang_code)
            + f": <b>{weather_data.sunrise}</b>  🌇 "
            + _("Sunset", locale=lang_code)
            + f": <b>{weather_data.sunset}</b>"
        )
        return current_weather
