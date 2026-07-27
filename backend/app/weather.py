from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

import httpx


@dataclass(frozen=True)
class DailyWeather:
    date: date
    min_temp_c: float
    max_temp_c: float
    apparent_min_temp_c: float
    apparent_max_temp_c: float
    planning_temp_c: float
    precipitation_probability: float
    precipitation_mm: float
    max_wind_kph: float
    humidity_percent: float | None
    weather_code: str
    confidence: float | None


class WeatherProvider(Protocol):
    async def get_forecast(
        self,
        latitude: float,
        longitude: float,
        start_date: date,
        days: int,
        timezone: str,
        active_start_hour: int = 8,
        active_end_hour: int = 18,
    ) -> list[DailyWeather]: ...


class OpenMeteoProvider:
    name = "open-meteo"
    endpoint = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client

    async def get_forecast(
        self,
        latitude: float,
        longitude: float,
        start_date: date,
        days: int,
        timezone: str,
        active_start_hour: int = 8,
        active_end_hour: int = 18,
    ) -> list[DailyWeather]:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date.isoformat(),
            "end_date": date.fromordinal(start_date.toordinal() + days - 1).isoformat(),
            "timezone": timezone,
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
            "daily": (
                "temperature_2m_min,temperature_2m_max,apparent_temperature_min,"
                "apparent_temperature_max,precipitation_probability_max,"
                "precipitation_sum,weather_code,wind_speed_10m_max"
            ),
            "hourly": "apparent_temperature,relative_humidity_2m",
        }
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=12)
        try:
            response = await client.get(self.endpoint, params=params)
            response.raise_for_status()
            return normalize_open_meteo(
                response.json(),
                active_start_hour=active_start_hour,
                active_end_hour=active_end_hour,
            )
        finally:
            if owns_client:
                await client.aclose()


def normalize_open_meteo(
    payload: dict, active_start_hour: int = 8, active_end_hour: int = 18
) -> list[DailyWeather]:
    daily = payload["daily"]
    hourly = payload.get("hourly", {})
    apparent_by_day: dict[date, list[float]] = defaultdict(list)
    humidity_by_day: dict[date, list[float]] = defaultdict(list)
    for timestamp, apparent, humidity in zip(
        hourly.get("time", []),
        hourly.get("apparent_temperature", []),
        hourly.get("relative_humidity_2m", []),
        strict=False,
    ):
        moment = datetime.fromisoformat(timestamp)
        if active_start_hour <= moment.hour <= active_end_hour:
            apparent_by_day[moment.date()].append(float(apparent))
            humidity_by_day[moment.date()].append(float(humidity))
    result = []
    for index, day_value in enumerate(daily["time"]):
        forecast_date = date.fromisoformat(day_value)
        apparent_values = apparent_by_day.get(forecast_date, [])
        fallback = 0.4 * float(daily["apparent_temperature_min"][index]) + 0.6 * float(
            daily["apparent_temperature_max"][index]
        )
        humidity_values = humidity_by_day.get(forecast_date, [])
        result.append(
            DailyWeather(
                date=forecast_date,
                min_temp_c=float(daily["temperature_2m_min"][index]),
                max_temp_c=float(daily["temperature_2m_max"][index]),
                apparent_min_temp_c=float(daily["apparent_temperature_min"][index]),
                apparent_max_temp_c=float(daily["apparent_temperature_max"][index]),
                planning_temp_c=(
                    sum(apparent_values) / len(apparent_values) if apparent_values else fallback
                ),
                precipitation_probability=float(daily["precipitation_probability_max"][index] or 0),
                precipitation_mm=float(daily["precipitation_sum"][index] or 0),
                max_wind_kph=float(daily["wind_speed_10m_max"][index] or 0),
                humidity_percent=(
                    sum(humidity_values) / len(humidity_values) if humidity_values else None
                ),
                weather_code=str(daily["weather_code"][index]),
                confidence=None,
            )
        )
    return result


def required_warmth(temperature_c: float) -> int:
    if temperature_c <= -5:
        return 5
    if temperature_c <= 5:
        return 4
    if temperature_c <= 14:
        return 3
    if temperature_c <= 22:
        return 2
    if temperature_c <= 28:
        return 1
    return 0


def weather_suitability(garment: dict, weather: DailyWeather) -> tuple[int, list[str]]:
    target = required_warmth(weather.planning_temp_c)
    warmth = int(garment.get("warmth") or 0)
    breathability = int(garment.get("breathability") or 0)
    water_resistance = int(garment.get("water_resistance") or 0)
    score = 100 - abs(target - warmth) * 16
    explanations = []
    if weather.planning_temp_c >= 24:
        score += breathability * 5
        if breathability >= 4:
            explanations.append("Breathable for warm weather")
    if weather.precipitation_probability >= 55 or weather.precipitation_mm >= 3:
        score += water_resistance * 6 - 12
        if water_resistance >= 3:
            explanations.append("Offers useful rain protection")
    if abs(target - warmth) <= 1:
        explanations.append("Warmth matches the forecast")
    return max(0, min(150, score)), explanations
