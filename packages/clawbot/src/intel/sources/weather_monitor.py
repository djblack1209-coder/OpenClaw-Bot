"""No-key weather, air quality, and alert monitor for Intel Brief."""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from typing import Any

from src.intel.runtime_policy import resolve_runtime_policy
from src.intel.sources.base import IntelSourceResult

DEFAULT_LATITUDE = "39.7392"
DEFAULT_LONGITUDE = "-104.9903"
DEFAULT_LOCATION_NAME = "Denver, CO"
NWS_USER_AGENT = "OpenClaw-IntelBrief/0.1 contact=openclaw-intel@example.invalid"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def _fetch_json(url: str, *, timeout: int, opener=None) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": NWS_USER_AGENT,
            "Accept": "application/geo+json,application/json,*/*",
        },
    )
    open_fn = opener or urllib.request.urlopen
    with open_fn(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8", errors="replace")
    data = json.loads(payload) if payload else {}
    return data if isinstance(data, dict) else {}


def _point_text(latitude: str, longitude: str) -> str:
    return f"{_clean(latitude)},{_clean(longitude)}"


def _open_meteo_air_quality_url(latitude: str, longitude: str) -> str:
    return (
        "https://air-quality-api.open-meteo.com/v1/air-quality"
        f"?latitude={_clean(latitude)}&longitude={_clean(longitude)}"
        "&current=us_aqi,pm2_5,pm10&timezone=auto"
    )


def _category_item(*, category: str, location_name: str, title: str, summary: str, provider: str) -> dict[str, Any]:
    return {
        "source": "weather",
        "category": category,
        "category_aliases": ["weather", category] if category != "weather" else ["weather"],
        "provider": provider,
        "location": location_name,
        "title": title,
        "summary": summary,
    }


def _first_hourly_period(hourly_payload: dict[str, Any]) -> dict[str, Any]:
    periods = ((hourly_payload.get("properties") or {}).get("periods") or []) if isinstance(hourly_payload, dict) else []
    if periods and isinstance(periods[0], dict):
        return periods[0]
    return {}


def _percent_from_period(period: dict[str, Any], key: str) -> str:
    value = period.get(key)
    if isinstance(value, dict):
        value = value.get("value")
    if value in (None, ""):
        return ""
    return str(value)


def _alert_title(alerts_payload: dict[str, Any], *, location_name: str) -> tuple[str, str]:
    features = alerts_payload.get("features") if isinstance(alerts_payload, dict) else []
    if isinstance(features, list) and features:
        props = features[0].get("properties") if isinstance(features[0], dict) else {}
        event = _clean(props.get("event") if isinstance(props, dict) else "")
        severity = _clean(props.get("severity") if isinstance(props, dict) else "")
        headline = _clean(props.get("headline") if isinstance(props, dict) else "")
        suffix = f"{event}（{severity}）" if severity else event
        return f"{location_name} 灾害预警：{suffix}", headline or suffix
    return f"{location_name} 暂无活跃天气灾害预警", "NWS active alerts returned zero active alerts for this point."


def _air_quality_item(air_payload: dict[str, Any], *, location_name: str) -> dict[str, Any]:
    current = air_payload.get("current") if isinstance(air_payload, dict) else {}
    us_aqi = _clean(current.get("us_aqi") if isinstance(current, dict) else "")
    pm25 = _clean(current.get("pm2_5") if isinstance(current, dict) else "")
    pm10 = _clean(current.get("pm10") if isinstance(current, dict) else "")
    title = f"{location_name} 空气质量：US AQI {us_aqi}" if us_aqi else f"{location_name} 空气质量：暂无 AQI 数据"
    summary = "；".join(part for part in [f"US AQI {us_aqi}" if us_aqi else "", f"PM2.5 {pm25}" if pm25 else "", f"PM10 {pm10}" if pm10 else ""] if part)
    return _category_item(
        category="air_quality",
        location_name=location_name,
        title=title,
        summary=summary or "Open-Meteo air quality current endpoint returned no current values.",
        provider="open_meteo_air_quality",
    )


def fetch_weather_monitor(
    *,
    latitude: str = DEFAULT_LATITUDE,
    longitude: str = DEFAULT_LONGITUDE,
    location_name: str = DEFAULT_LOCATION_NAME,
    limit: int = 6,
    timeout: int = 20,
    opener=None,
) -> list[dict[str, Any]]:
    """Fetch NWS weather/alerts plus Open-Meteo air quality rows without credentials."""
    point = _point_text(latitude, longitude)
    points_payload = _fetch_json(f"https://api.weather.gov/points/{point}", timeout=timeout, opener=opener)
    forecast_hourly_url = _clean((points_payload.get("properties") or {}).get("forecastHourly"))
    if not forecast_hourly_url:
        raise RuntimeError("nws_forecast_hourly_url_missing")
    hourly_payload = _fetch_json(forecast_hourly_url, timeout=timeout, opener=opener)
    period = _first_hourly_period(hourly_payload)
    short_forecast = _clean(period.get("shortForecast")) or "Weather forecast unavailable"
    temperature = _clean(period.get("temperature"))
    temp_unit = _clean(period.get("temperatureUnit")) or "F"
    precip = _percent_from_period(period, "probabilityOfPrecipitation")
    humidity = _percent_from_period(period, "relativeHumidity")
    wind_speed = _clean(period.get("windSpeed"))
    alerts_payload = _fetch_json(f"https://api.weather.gov/alerts/active?point={point}", timeout=timeout, opener=opener)
    alert_title, alert_summary = _alert_title(alerts_payload, location_name=location_name)
    air_payload = _fetch_json(_open_meteo_air_quality_url(latitude, longitude), timeout=timeout, opener=opener)

    items = [
        _category_item(
            category="weather",
            location_name=location_name,
            title=f"{location_name} 天气：{short_forecast}，{temperature}°{temp_unit}" if temperature else f"{location_name} 天气：{short_forecast}",
            summary="；".join(part for part in [short_forecast, f"风速 {wind_speed}" if wind_speed else ""] if part),
            provider="nws_api",
        ),
        _category_item(
            category="temperature",
            location_name=location_name,
            title=f"{location_name} 温度：{temperature}°{temp_unit}" if temperature else f"{location_name} 温度：暂无数据",
            summary=f"NWS hourly forecast temperature for {location_name}.",
            provider="nws_api",
        ),
        _category_item(
            category="rainfall",
            location_name=location_name,
            title=f"{location_name} 降雨概率：{precip}%" if precip else f"{location_name} 降雨概率：暂无数据",
            summary=f"NWS hourly probability of precipitation for {location_name}.",
            provider="nws_api",
        ),
        _category_item(
            category="humidity",
            location_name=location_name,
            title=f"{location_name} 湿度：{humidity}%" if humidity else f"{location_name} 湿度：暂无数据",
            summary=f"NWS hourly relative humidity for {location_name}.",
            provider="nws_api",
        ),
        _category_item(
            category="disaster_alerts",
            location_name=location_name,
            title=alert_title,
            summary=alert_summary,
            provider="nws_api",
        ),
        _air_quality_item(air_payload, location_name=location_name),
    ]
    return items[: max(0, int(limit))]


class WeatherMonitorAdapter:
    """Weather/air quality/alert adapter using no-key public APIs."""

    source_name = "weather"

    def __init__(
        self,
        *,
        latitude: str = DEFAULT_LATITUDE,
        longitude: str = DEFAULT_LONGITUDE,
        location_name: str = DEFAULT_LOCATION_NAME,
        timeout: int = 20,
        opener=None,
        evidence_path: str = "",
    ) -> None:
        self.latitude = latitude
        self.longitude = longitude
        self.location_name = location_name
        self.timeout = timeout
        self.opener = opener
        self.evidence_path = evidence_path

    def fetch(self, *, limit: int = 20) -> IntelSourceResult:
        items = fetch_weather_monitor(
            latitude=self.latitude,
            longitude=self.longitude,
            location_name=self.location_name,
            limit=limit,
            timeout=self.timeout,
            opener=self.opener,
        )
        policy = resolve_runtime_policy(self.source_name)
        return IntelSourceResult(
            source=self.source_name,
            worker=policy.preferred_worker,
            fetched_at=_now_iso(),
            items=items,
            raw_count=len(items),
            health_status="success",
            evidence_path=self.evidence_path,
        )
