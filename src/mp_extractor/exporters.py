"""Ausgabeformate: JSON und CSV für Maschinen, Markdown für Menschen."""

from __future__ import annotations

import csv
import io
import json
import statistics
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from . import __version__
from .models import KINDS, MOVIE, SERIES, Rating

KIND_LABELS = {MOVIE: "Filme", SERIES: "Serien"}


def compute_stats(ratings: list[Rating]) -> dict:
    values = [r.rating for r in ratings if r.rating is not None]
    distribution = Counter(values)
    return {
        "count": len(ratings),
        "average": round(statistics.fmean(values), 2) if values else None,
        "median": statistics.median(values) if values else None,
        "distribution": {f"{v:.1f}": distribution[v] for v in sorted(distribution, reverse=True)},
    }


def _sorted(ratings: list[Rating]) -> list[Rating]:
    return sorted(ratings, key=lambda r: (KINDS.index(r.kind) if r.kind in KINDS else 99,
                                          -(r.rating if r.rating is not None else -1),
                                          r.title.lower()))


def to_json(ratings: list[Rating], username: Optional[str] = None) -> str:
    document = {
        "source": "moviepilot.de",
        "username": username,
        "exported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "tool": f"mp-extractor {__version__}",
        "rating_scale": {"min": 0.0, "max": 10.0, "step": 0.5},
        "stats": {kind: compute_stats([r for r in ratings if r.kind == kind]) for kind in KINDS},
        "ratings": [r.to_dict() for r in _sorted(ratings)],
    }
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def to_csv(ratings: list[Rating]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=Rating.field_names(), lineterminator="\n")
    writer.writeheader()
    for r in _sorted(ratings):
        row = r.to_dict()
        row["genres"] = ", ".join(r.genres)
        writer.writerow(row)
    return buffer.getvalue()


def _fmt_rating(value: Optional[float], digits: int = 1) -> str:
    return "–" if value is None else f"{value:.{digits}f}".replace(".", ",")


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|")


def to_markdown(ratings: list[Rating], username: Optional[str] = None) -> str:
    who = f" von {username}" if username else ""
    lines = [f"# moviepilot-Bewertungen{who}", ""]
    lines.append(f"Exportiert am {datetime.now().strftime('%d.%m.%Y')} · Skala 0–10")
    lines.append("")

    lines += ["## Überblick", "", "| | Anzahl | Ø Bewertung | Median |", "|---|---:|---:|---:|"]
    for kind in KINDS:
        s = compute_stats([r for r in ratings if r.kind == kind])
        lines.append(f"| {KIND_LABELS[kind]} | {s['count']} | {_fmt_rating(s['average'], 2)} "
                     f"| {_fmt_rating(s['median'])} |")
    lines.append("")

    for kind in KINDS:
        items = [r for r in _sorted(ratings) if r.kind == kind]
        if not items:
            continue
        stats = compute_stats(items)
        lines += [f"## {KIND_LABELS[kind]} ({len(items)})", "", "### Verteilung", ""]
        top = max(stats["distribution"].values(), default=1)
        for value, count in stats["distribution"].items():
            bar = "█" * max(1, round(20 * count / top))
            lines.append(f"    {value.replace('.', ','):>4}  {bar} {count}")
        lines += ["", "### Alle Bewertungen", "",
                  "| Bewertung | Titel | Jahr | Land | Genres | Bewertet am |",
                  "|---:|---|---:|---|---|---|"]
        for r in items:
            title = f"[{_md_escape(r.title)}]({r.url})" if r.url else _md_escape(r.title)
            rated_at = datetime.fromisoformat(r.rated_at).strftime("%d.%m.%Y") if r.rated_at else ""
            lines.append(f"| {_fmt_rating(r.rating)} | {title} | {r.year or ''} "
                         f"| {_md_escape(r.country or '')} | {_md_escape(', '.join(r.genres))} | {rated_at} |")
        lines.append("")
    return "\n".join(lines)


FORMATS = {
    "json": lambda ratings, username: to_json(ratings, username),
    "csv": lambda ratings, username: to_csv(ratings),
    "md": lambda ratings, username: to_markdown(ratings, username),
}
