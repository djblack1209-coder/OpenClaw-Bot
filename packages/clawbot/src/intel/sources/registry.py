"""Default Intel Brief source adapter registry."""

from __future__ import annotations

from src.intel.sources.ai_model_updates import AIModelUpdatesAdapter
from src.intel.sources.astock_flow import AkshareLhbAdapter
from src.intel.sources.base import IntelSourceAdapter
from src.intel.sources.congress_trading import SenateTransactionsAdapter
from src.intel.sources.github_trending import GitHubTrendingAdapter
from src.intel.sources.institutional_13f import Institutional13FAdapter
from src.intel.sources.weather_monitor import WeatherMonitorAdapter


def build_default_source_adapters() -> dict[str, IntelSourceAdapter]:
    """Build adapters that are safe to invoke from a worker once deployed.

    Only sources with prior target-worker evidence should be registered here.
    Additional adapters must be added after their Phase B evidence exists.
    """
    senate = SenateTransactionsAdapter(
        evidence_path="data/intel_evidence/phaseb/20260706T224857Z-oracle-arm1-overseas-fallback-retry.jsonl"
    )
    akshare_lhb = AkshareLhbAdapter(
        evidence_path="data/intel_evidence/phaseb/20260706T225123Z-yanhuoyun-akshare-call-retry.jsonl"
    )
    github_trending = GitHubTrendingAdapter(
        evidence_path=(
            "data/intel_evidence/phaseaq/"
            "20260707T190500Z-github-trending-oracle-sg-worker-parser-fixed.json"
        )
    )
    ai_model_updates = AIModelUpdatesAdapter(
        evidence_path="data/intel_evidence/phaseau/20260707T193548Z-ai-model-updates-oracle-sg-worker-final.json"
    )
    institutional_13f = Institutional13FAdapter(
        evidence_path=(
            "data/intel_evidence/phaseaw/"
            "20260707T201214Z-institutional-13f-oracle-sg-worker-aggregated.json"
        )
    )
    weather = WeatherMonitorAdapter(
        evidence_path="data/intel_evidence/phaseaz/20260707T204803Z-weather-oracle-sg-worker.json"
    )
    return {
        senate.source_name: senate,
        akshare_lhb.source_name: akshare_lhb,
        github_trending.source_name: github_trending,
        ai_model_updates.source_name: ai_model_updates,
        institutional_13f.source_name: institutional_13f,
        weather.source_name: weather,
    }
