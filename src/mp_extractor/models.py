"""Datenmodell für eine einzelne Bewertung."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Optional

MOVIE = "movie"
SERIES = "series"
KINDS = (MOVIE, SERIES)


@dataclass
class Rating:
    """Eine Film- oder Serienbewertung eines moviepilot-Nutzers.

    ``rating`` liegt immer auf der moviepilot-Skala 0.0–10.0 (Schritte von 0.5).
    """

    kind: str
    title: str
    rating: Optional[float]
    url: Optional[str] = None
    slug: Optional[str] = None
    year: Optional[int] = None
    country: Optional[str] = None
    rated_at: Optional[str] = None  # ISO-8601-Datum, z. B. "2019-04-02"
    genres: list[str] = field(default_factory=list)
    community_rating: Optional[float] = None  # Schnitt der moviepilot-Community, 0.0–10.0
    moviepilot_id: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def field_names(cls) -> list[str]:
        return [f.name for f in fields(cls)]
