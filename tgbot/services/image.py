"""Generates an image with weather forecast information"""

from dataclasses import dataclass
from os import makedirs, path
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from tgbot.config import BASE_DIR
from tgbot.services.classes import ForecastData

__all__: tuple[str] = ("DrawWeatherImage",)


@dataclass
class Cursor:
    """
    Cursor to draw objects on the canvas in a loop.

    :param pos_x: Cursor position on the X-axis.
    :param pos_y: Cursor position on the Y-axis.
    """

    pos_x: int = 0
    pos_y: int = 0


class DrawWeatherImage:
    """Draws an image with the weather forecast."""

    _ICONS_DIR: Path = Path(BASE_DIR, "tgbot/assets/ico")
    _FONT: Path = Path(BASE_DIR, "tgbot/assets/font/Rubik-Bold.ttf")
    _TEMP_DIR: Path = Path(BASE_DIR, "tgbot/temp")

    def __init__(self) -> None:
        """
        Initializes the DrawWeatherImage class.

        This function initializes the DrawWeatherImage class, which is used to draw an image with the weather
        forecast. It creates the directory for temporary files if it does not already exist.
        """
        makedirs(name=self._TEMP_DIR, exist_ok=True)

    # region Auxiliary methods
    @staticmethod
    def _get_temp_color(temperature: str) -> str:
        """
        Returns the color code, depending on the temperature value.

        :param temperature: Temperature value.
        :return: Temperature color code.
        """
        if temperature[-1:] == "C":
            temp: int = int(temperature.removesuffix("°C"))
        else:
            temp = round((int(temperature.removesuffix("°F")) - 32) * (5 / 9))

        if temp >= 50:
            temp_color: str = "#2b0001"
        elif 49 >= temp >= 40:
            temp_color = "#6b1527"
        elif 39 >= temp >= 30:
            temp_color = "#b73466"
        elif 29 >= temp >= 25:
            temp_color = "#db6c54"
        elif 24 >= temp >= 20:
            temp_color = "#e09f41"
        elif 19 >= temp >= 15:
            temp_color = "#e1ce39"
        elif 14 >= temp >= 10:
            temp_color = "#b8db41"
        elif 9 >= temp >= 5:
            temp_color = "#5ac84b"
        elif 4 >= temp >= 0:
            temp_color = "#4db094"
        elif -1 >= temp >= -5:
            temp_color = "#4178be"
        elif -6 >= temp >= -10:
            temp_color = "#5751ac"
        elif -11 >= temp >= -15:
            temp_color = "#291e6a"
        elif -16 >= temp >= -20:
            temp_color = "#8e108e"
        elif -21 >= temp >= -30:
            temp_color = "#f3a5f3"
        else:
            temp_color = "#e3e3e3"
        return temp_color

    @staticmethod
    def _get_wind_color(wind_speed: str) -> str:
        """
        Returns the color code, depending on the wind speed value.

        :param wind_speed: Wind speed value.
        :return: Wind speed color code.
        """
        if wind_speed[-1:] == "s":
            speed: int = int(wind_speed.removesuffix(" m/s"))
        else:
            speed = round(float(wind_speed.removesuffix(" mph")) / 2.237)

        if 0 <= speed <= 9:
            wind_speed_color: str = "#5a5673"
        elif 10 <= speed <= 19:
            wind_speed_color = "#5258ab"
        elif 20 <= speed <= 29:
            wind_speed_color = "#4083b8"
        elif 30 <= speed <= 39:
            wind_speed_color = "#4ea98f"
        elif 40 <= speed <= 49:
            wind_speed_color = "#4abe47"
        elif 50 <= speed <= 59:
            wind_speed_color = "#8ec94b"
        elif 60 <= speed <= 69:
            wind_speed_color = "#cad63e"
        elif 70 <= speed <= 79:
            wind_speed_color = "#d8bf3d"
        elif 80 <= speed <= 89:
            wind_speed_color = "#d69b44"
        elif 90 <= speed <= 99:
            wind_speed_color = "#d5784c"
        elif 100 <= speed <= 109:
            wind_speed_color = "#c7466f"
        elif 110 <= speed <= 119:
            wind_speed_color = "#a3355b"
        elif 120 <= speed <= 129:
            wind_speed_color = "#901c4f"
        elif 130 <= speed <= 139:
            wind_speed_color = "#631a1b"
        else:
            wind_speed_color = "#2b0001"
        return wind_speed_color

    @staticmethod
    def _get_color_of_text_temperature(temperature: str) -> str:
        """
        Returns the temperature text color code, depending on the temperature value.

        :param temperature: Temperature value.
        :return: Temperature text color code.
        """
        if temperature[-1:] == "C":
            temp: int = int(temperature.removesuffix("°C"))
        else:
            temp = round((int(temperature.removesuffix("°F")) - 32) * (5 / 9))

        if 24 >= temp >= 0 or temp <= -21:
            return "#000000"
        return "#ffffff"

    @staticmethod
    def _get_color_of_text_wind(wind_speed: str) -> str:
        """
        Returns the wind speed text color code, depending on the wind speed value.

        :param wind_speed: Wind speed value.
        :return: Wind speed text color code.
        """
        if wind_speed[-1:] == "s":
            speed: int = int(wind_speed.removesuffix(" m/s"))
        else:
            speed = round(float(wind_speed.removesuffix(" mph")) / 2.237)

        if 99 >= speed >= 40:
            return "#000000"
        return "#ffffff"

    @staticmethod
    def _invert_image_color(image: Image.Image) -> Image.Image:
        """
        Inverts the black color in the image.

        :param image: Image.Image object.
        :return: Image.Image object with inverted colors.
        """
        white_image: Image.Image = Image.new(mode="RGBA", size=image.size, color="#ffffff")
        white_image.putalpha(alpha=image.getchannel("A"))
        return white_image

    # endregion

    def draw_image(self, data: ForecastData, user_id: int) -> Path:
        """
        Draws an image with weather forecast information.

        :param data: Weather forecast data.
        :param user_id: User id (for generate filename).
        :return: Path to generated image file.
        """
        cursor: Cursor = Cursor()
        canvas: Image.Image = Image.new(mode="RGBA", size=(799, 199), color="#262626")
        draw: ImageDraw.ImageDraw = ImageDraw.Draw(im=canvas)

        temp: list[str] = data.temp
        time: list[str] = data.time
        ico_code: list[str] = data.ico_code
        wind_speed: list[str] = data.wind_speed

        def draw_text_align_center(pos_x: int, pos_y: int, font_size: int, text: str, color: str) -> None:
            """
            Draws specified text with center alignment.

            :param pos_x: X-axis position.
            :param pos_y: Y-axis position.
            :param font_size: Font size.
            :param text: Text to output.
            :param color: Text color
            :return: None
            """
            font: ImageFont.FreeTypeFont = ImageFont.truetype(font=self._FONT, size=font_size)
            offset: int = round((99 - draw.textlength(text=text, font=font)) / 2)
            draw.text(xy=(pos_x + offset, pos_y), text=text, font=font, fill=color)

        for idx in range(8):
            # Fill temperature columns
            cursor.pos_y = 0
            draw.rectangle(
                xy=(cursor.pos_x, cursor.pos_y, cursor.pos_x + 98, cursor.pos_y + 163),
                fill=self._get_temp_color(temperature=temp[idx]),
            )
            # Draw time
            color_of_text: str = self._get_color_of_text_temperature(temperature=temp[idx])
            cursor.pos_y = 15
            draw_text_align_center(
                pos_x=cursor.pos_x, pos_y=cursor.pos_y, font_size=24, text=time[idx], color=color_of_text
            )
            # Draw weather icons
            cursor.pos_y = 50
            file_path: str = path.join(self._ICONS_DIR, f"{ico_code[idx]}.png")
            weather_icon: Image.Image = Image.open(fp=file_path, mode="r", formats=("PNG",))
            if color_of_text == "#ffffff":
                weather_icon = self._invert_image_color(image=weather_icon)
            canvas.alpha_composite(im=weather_icon, dest=(cursor.pos_x + 17, cursor.pos_y))
            weather_icon.close()
            # Draw temperature
            cursor.pos_y = 126
            draw_text_align_center(
                pos_x=cursor.pos_x, pos_y=cursor.pos_y, font_size=24, text=temp[idx], color=color_of_text
            )
            # Fill wind speed columns
            cursor.pos_y = 165
            draw.rectangle(
                xy=(cursor.pos_x, cursor.pos_y, cursor.pos_x + 98, cursor.pos_y + 34),
                fill=self._get_wind_color(wind_speed=wind_speed[idx]),
            )
            # Draw wind speed
            color_of_text = self._get_color_of_text_wind(wind_speed=wind_speed[idx])
            cursor.pos_y = 173
            draw_text_align_center(
                pos_x=cursor.pos_x, pos_y=cursor.pos_y, font_size=18, text=wind_speed[idx], color=color_of_text
            )
            # Shift to the next column
            cursor.pos_x += 100

        path_to_image: Path = Path(self._TEMP_DIR, f"{user_id}.png")
        canvas.save(fp=path_to_image, format="PNG")
        canvas.close()

        return path_to_image
