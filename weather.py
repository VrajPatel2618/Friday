"""
weather.py - Weather reports for FRIDAY
Uses OpenWeatherMap free API (no pyowm, just requests).

Setup:
  1. Get free API key: https://openweathermap.org/api (Sign up -> API Keys)
  2. Set OPENWEATHER_API_KEY in config.py
  3. Set WEATHER_CITY in config.py (e.g. "Mumbai" or "London")

Voice commands (handled in commands.py):
  "What's the weather?"
  "Weather today"
  "Will it rain today?"
  "What's the temperature outside?"
  "Weather forecast"
"""

import requests
from config import OPENWEATHER_API_KEY, WEATHER_CITY

BASE_URL = "https://api.openweathermap.org/data/2.5"


def _available() -> bool:
    return bool(OPENWEATHER_API_KEY and not OPENWEATHER_API_KEY.startswith("YOUR_"))


def get_current_weather(city: str = None) -> str:
    """Return a spoken weather summary for the given city."""
    if not _available():
        return ("Weather is not configured. "
                "Get a free API key at openweathermap.org and set "
                "OPENWEATHER_API_KEY in config.py.")

    city = city or WEATHER_CITY
    try:
        resp = requests.get(
            f"{BASE_URL}/weather",
            params={
                "q":     city,
                "appid": OPENWEATHER_API_KEY,
                "units": "metric"
            },
            timeout=6
        )
        if resp.status_code == 401:
            return "Invalid OpenWeather API key. Check config.py."
        if resp.status_code == 404:
            return f"City '{city}' not found. Check WEATHER_CITY in config.py."
        resp.raise_for_status()

        d          = resp.json()
        temp       = round(d["main"]["temp"])
        feels_like = round(d["main"]["feels_like"])
        humidity   = d["main"]["humidity"]
        desc       = d["weather"][0]["description"].capitalize()
        wind_kph   = round(d["wind"]["speed"] * 3.6)
        city_name  = d["name"]

        return (f"Currently in {city_name}: {desc}. "
                f"Temperature is {temp}°C, feels like {feels_like}°C. "
                f"Humidity {humidity}%, wind {wind_kph} km/h.")

    except requests.exceptions.ConnectionError:
        return "No internet connection for weather data."
    except Exception as e:
        return f"Weather error: {e}"


def get_forecast(city: str = None, days: int = 3) -> str:
    """Return a 3-day spoken forecast."""
    if not _available():
        return "Weather API not configured."

    city = city or WEATHER_CITY
    try:
        resp = requests.get(
            f"{BASE_URL}/forecast",
            params={
                "q":     city,
                "appid": OPENWEATHER_API_KEY,
                "units": "metric",
                "cnt":   days * 8   # 3-hour steps
            },
            timeout=6
        )
        resp.raise_for_status()
        data = resp.json()

        # Summarize: group by day, pick midday reading
        from collections import defaultdict
        daily: dict = defaultdict(list)
        for item in data["list"]:
            date = item["dt_txt"].split(" ")[0]
            daily[date].append(item)

        lines = []
        for i, (date, readings) in enumerate(list(daily.items())[:days]):
            mid    = readings[len(readings) // 2]
            temp   = round(mid["main"]["temp"])
            desc   = mid["weather"][0]["description"]
            label  = ["Today", "Tomorrow", f"In {i+1} days"][min(i, 2)]
            lines.append(f"{label}: {desc}, {temp}°C")

        return f"Forecast for {city}: " + ". ".join(lines) + "."

    except Exception as e:
        return f"Forecast error: {e}"


def will_it_rain(city: str = None) -> str:
    """Check if rain is expected today."""
    if not _available():
        return "Weather API not configured."

    city = city or WEATHER_CITY
    try:
        resp = requests.get(
            f"{BASE_URL}/forecast",
            params={
                "q":     city,
                "appid": OPENWEATHER_API_KEY,
                "units": "metric",
                "cnt":   8   # next 24h
            },
            timeout=6
        )
        resp.raise_for_status()
        data = resp.json()

        rain_periods = []
        for item in data["list"]:
            weather_main = item["weather"][0]["main"].lower()
            if "rain" in weather_main or "drizzle" in weather_main:
                time_str = item["dt_txt"].split(" ")[1][:5]
                rain_periods.append(time_str)

        if rain_periods:
            return (f"Yes, rain is expected in {city} around "
                    f"{', '.join(rain_periods[:3])}. You may want an umbrella.")
        return f"No rain expected in {city} for the next 24 hours."

    except Exception as e:
        return f"Rain check error: {e}"


if __name__ == "__main__":
    print(get_current_weather())
    print(get_forecast())
    print(will_it_rain())
