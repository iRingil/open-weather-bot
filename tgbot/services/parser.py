"""Parses raw data on weather with OpenWeatherAPI."""

from datetime import datetime, timedelta

from tzlocal import get_localzone

from tgbot.misc.logger import logger
from tgbot.services.classes import CityData, CurrentWeatherData, ForecastData

__all__: tuple[str] = ("ParseWeather",)


class ParseWeather:
    """A class for parsing data with OpenWeatherAPI."""

    @staticmethod
    async def parse_city_data(raw_data: dict, lang_code: str) -> CityData | None:
        """
        Parses city data from OpenWeatherAPI response.

        :param raw_data: Raw city data from OpenWeatherAPI.
        :param lang_code: User language code.
        :return: Parsed city data as CityData object or None in case of error.
        """
        try:
            name: str = raw_data["name"]
            state: str | None = raw_data.get("state")
            country: str = raw_data["country"]
            local_names_dict: dict | None = raw_data.get("local_names")
            local_name: str | None = name if local_names_dict is None else local_names_dict.get(lang_code)
            city_name: str | None = name if local_name is None else local_name
            latitude: float = raw_data["lat"]
            longitude: float = raw_data["lon"]
            return CityData(
                name=f"{city_name}",
                full_name=f"{city_name}, {country}" if state is None else f"{city_name}, {state}, {country}",
                latitude=round(latitude, 6),
                longitude=round(longitude, 6),
            )
        except KeyError as ex:
            logger.error("Error when parsing city data: %s", ex)
        return None

    @staticmethod
    async def parse_current_weather(raw_data: dict) -> CurrentWeatherData | None:
        """
        Parses current weather data from OpenWeatherAPI response.

        :param raw_data: Raw weather data from OpenWeatherAPI.
        :return: Parsed weather data as CurrentWeatherData object or None in case of error.
        """
        try:
            temp: int = round(raw_data["main"]["temp"])
            feels_like: int = round(raw_data["main"]["feels_like"])
            weather_code: int = raw_data["weather"][0]["id"]
            weather_description: str = raw_data["weather"][0]["description"]
            wind_speed: int = round(raw_data["wind"]["speed"])
            gust: int | None = round(raw_data["wind"]["gust"]) if raw_data["wind"].get("gust") else None
            humidity: int = raw_data["main"]["humidity"]
            pressure: int = raw_data["main"]["pressure"]
            visibility: float | None = round(raw_data["visibility"] / 1000, 1) if raw_data.get("visibility") else None
            if raw_data.get("snow"):
                precipitation: float | None = raw_data["snow"]["1h"]
            elif raw_data.get("rain"):
                precipitation = raw_data["rain"]["1h"]
            else:
                precipitation = None
            server_time_offset_from_utc: timedelta | None = datetime.now(get_localzone()).utcoffset()
            if server_time_offset_from_utc:
                time_offset: int = raw_data["timezone"] - int(server_time_offset_from_utc.total_seconds())
            else:
                time_offset = raw_data["timezone"]
            time: str = datetime.fromtimestamp(raw_data["dt"] + time_offset).strftime("%d %b %H:%M")
            sunrise: str = datetime.fromtimestamp(raw_data["sys"]["sunrise"] + time_offset).strftime("%H:%M")
            sunset: str = datetime.fromtimestamp(raw_data["sys"]["sunset"] + time_offset).strftime("%H:%M")
            return CurrentWeatherData(
                temp=temp,
                feels_like=feels_like,
                weather_code=weather_code,
                weather_description=weather_description,
                wind_speed=wind_speed,
                gust=gust,
                humidity=humidity,
                pressure=pressure,
                visibility=visibility,
                precipitation=precipitation,
                time=time,
                sunrise=sunrise,
                sunset=sunset,
            )
        except KeyError as ex:
            logger.error("Error when parsing current weather data: %s", ex)
        return None

    @staticmethod
    async def parse_weather_forecast(raw_data: dict, units: str) -> ForecastData | None:
        """
        Parses weather forecast data from OpenWeatherAPI response.

        :param raw_data: Raw forecast data from OpenWeatherAPI.
        :param units: Measurement units ('metric' or 'imperial')
        :return: Parsed forecast data as ForecastData object or None in case of error.
        """
        time: list[str] = []
        ico_code: list[str] = []
        temp: list[str] = []
        wind_speed: list[str] = []
        try:
            for item in raw_data["list"]:
                time.append(datetime.fromtimestamp(item["dt"]).strftime("%H:%M"))
                ico_code.append(item["weather"][0]["icon"])
                temp.append(f"{round(item['main']['temp'])}{'°C' if units == 'metric' else '°F'}")
                wind_speed.append(f"{round(item['wind']['speed'])} {'m/s' if units == 'metric' else 'mph'}")
            return ForecastData(time=time, ico_code=ico_code, temp=temp, wind_speed=wind_speed)
        except KeyError as ex:
            logger.error("Error when parsing weather forecast data: %s", ex)
        return None
