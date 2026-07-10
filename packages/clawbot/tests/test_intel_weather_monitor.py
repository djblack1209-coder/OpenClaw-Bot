from __future__ import annotations

import json

from src.intel.sources.weather_monitor import WeatherMonitorAdapter, fetch_weather_monitor


class _FakeResponse:
    def __init__(self, body: dict[str, object]) -> None:
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def test_weather_monitor_fetches_nws_weather_alerts_and_open_meteo_air_quality_without_credentials():
    bodies = {
        "https://api.weather.gov/points/39.7392,-104.9903": {
            "properties": {"forecastHourly": "https://api.weather.gov/gridpoints/BOU/63,61/forecast/hourly"}
        },
        "https://api.weather.gov/gridpoints/BOU/63,61/forecast/hourly": {
            "properties": {
                "periods": [
                    {
                        "name": "This Hour",
                        "temperature": 72,
                        "temperatureUnit": "F",
                        "shortForecast": "Partly Cloudy",
                        "windSpeed": "8 mph",
                        "probabilityOfPrecipitation": {"value": 40},
                        "relativeHumidity": {"value": 35},
                    }
                ]
            }
        },
        "https://api.weather.gov/alerts/active?point=39.7392,-104.9903": {
            "features": [{"properties": {"event": "Severe Thunderstorm Warning", "severity": "Severe"}}]
        },
        (
            "https://air-quality-api.open-meteo.com/v1/air-quality"
            "?latitude=39.7392&longitude=-104.9903&current=us_aqi,pm2_5,pm10&timezone=auto"
        ): {"current": {"us_aqi": 42, "pm2_5": 7.5, "pm10": 18.1}},
    }
    calls: list[str] = []

    def opener(request, timeout: int):
        calls.append(request.full_url)
        return _FakeResponse(bodies[request.full_url])

    items = fetch_weather_monitor(opener=opener, timeout=5, limit=10)

    assert [item["category"] for item in items] == [
        "weather",
        "temperature",
        "rainfall",
        "humidity",
        "disaster_alerts",
        "air_quality",
    ]
    assert items[0]["source"] == "weather"
    assert items[0]["category_aliases"] == ["weather"]
    assert "Partly Cloudy" in items[0]["title"]
    assert items[1]["title"] == "Denver, CO 温度：72°F"
    assert items[2]["title"] == "Denver, CO 降雨概率：40%"
    assert items[3]["title"] == "Denver, CO 湿度：35%"
    assert items[4]["title"] == "Denver, CO 灾害预警：Severe Thunderstorm Warning（Severe）"
    assert items[5]["title"] == "Denver, CO 空气质量：US AQI 42"
    assert calls == list(bodies)


def test_weather_monitor_adapter_returns_source_result_with_overseas_worker():
    def opener(request, timeout: int):
        if request.full_url == "https://api.weather.gov/points/39.7392,-104.9903":
            return _FakeResponse(
                {"properties": {"forecastHourly": "https://api.weather.gov/gridpoints/BOU/63,61/forecast/hourly"}}
            )
        if request.full_url == "https://api.weather.gov/gridpoints/BOU/63,61/forecast/hourly":
            return _FakeResponse(
                {
                    "properties": {
                        "periods": [
                            {
                                "temperature": 70,
                                "temperatureUnit": "F",
                                "shortForecast": "Sunny",
                                "probabilityOfPrecipitation": {"value": 0},
                                "relativeHumidity": {"value": 20},
                            }
                        ]
                    }
                }
            )
        if request.full_url == "https://api.weather.gov/alerts/active?point=39.7392,-104.9903":
            return _FakeResponse({"features": []})
        return _FakeResponse({"current": {"us_aqi": 35, "pm2_5": 5.5, "pm10": 12.0}})

    adapter = WeatherMonitorAdapter(opener=opener, evidence_path="evidence/weather.json")

    result = adapter.fetch(limit=6)

    assert result.source == "weather"
    assert result.worker == "overseas"
    assert result.health_status == "success"
    assert result.raw_count == 6
    assert result.items[-2]["title"] == "Denver, CO 暂无活跃天气灾害预警"
    assert result.evidence_path.endswith("weather.json")
