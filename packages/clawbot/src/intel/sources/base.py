"""Intel Brief source adapter base contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class IntelSourceResult:
    """Normalized result returned by every Intel Brief source adapter."""

    source: str
    worker: str
    fetched_at: str
    items: list[dict[str, Any]]
    raw_count: int
    health_status: str
    evidence_path: str


class IntelSourceAdapter(Protocol):
    """Protocol implemented by Intel Brief source adapters."""

    source_name: str

    def fetch(self, *, limit: int = 20) -> IntelSourceResult:
        """Fetch real source data and return a normalized source result."""
