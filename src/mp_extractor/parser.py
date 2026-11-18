"""Parser für die Bewertungslisten von moviepilot.de.

Die Seiten ``/users/<name>/rated/movies`` bzw. ``/rated/series`` enthalten eine
Tabelle (Titel · Land · Jahr | Bewertung | Datum). Neuere Versionen der Seite
werden mit Next.js gerendert; für diesen Fall gibt es zusätzlich einen
Fallback, der die eingebetteten JSON-Daten (``__NEXT_DATA__``) durchsucht.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Iterable, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from .models import MOVIE, SERIES, Rating

BASE_URL = "https://www.moviepilot.de"

_PRODUCTION_INFO_RE = re.compile(r"^(?P<country>.*?)\s*·\s*(?P<year>\d{4})\s*$")
_YEAR_RE = re.compile(r"\b(18|19|20)\d{2}\b")
_DATE_FORMATS = ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d")


def parse_rating_value(text: Any, *, percent: bool = False) -> Optional[float]:
    """Wandelt "9,5", "9.5", 95 (bei ``percent=True``) usw. in 0.0–10.0 um."""
    if text is None or isinstance(text, bool):
        return None
    if isinstance(text, (int, float)):
        value = float(text)
    else:
        match = re.search(r"\d+(?:[.,]\d+)?", str(text))
        if not match:
            return None
        value = float(match.group(0).replace(",", "."))
    if percent or value > 10:
        value = value / 10
    if not 0 <= value <= 10:
        return None
    return round(value * 2) / 2


def parse_date(text: Any) -> Optional[str]:
    """Liefert ein ISO-Datum ("YYYY-MM-DD") oder ``None``."""
    if not text:
        return None
    raw = str(text).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    try:  # ISO-Zeitstempel wie "2019-04-02T18:21:00+02:00"
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def kind_from_path(path: str, default: str) -> str:
    if path.startswith("/movies/"):
        return MOVIE
    if path.startswith("/serie/") or path.startswith("/series/"):
        return SERIES
    return default


def _slug(path: str) -> Optional[str]:
    parts = [p for p in urlparse(path).path.split("/") if p]
    return parts[1] if len(parts) >= 2 else None


def parse_ratings_page(html: str, default_kind: str = MOVIE) -> list[Rating]:
    """Extrahiert alle Bewertungen einer einzelnen Listenseite."""
    soup = BeautifulSoup(html, "html.parser")
    ratings = _parse_table(soup, default_kind)
    if not ratings:
        ratings = _parse_next_data(soup, default_kind)
    return ratings


def _parse_table(soup: BeautifulSoup, default_kind: str) -> list[Rating]:
    ratings: list[Rating] = []
    for table in soup.find_all("table"):
        header = [th.get_text(" ", strip=True).lower() for th in table.find_all("th")]
        if header and not any("bewertung" in h for h in header):
            continue
        body = table.find("tbody") or table
        for row in body.find_all("tr"):
            rating = _parse_row(row, default_kind)
            if rating:
                ratings.append(rating)
    return ratings


def _parse_row(row: Tag, default_kind: str) -> Optional[Rating]:
    cells = row.find_all("td")
    if len(cells) < 2:
        return None
    title_cell = row.find("td", class_="plain-list-movie") or cells[0]
    link = title_cell.find("a", href=True)
    if not link:
        return None
    href = link["href"]
    path = urlparse(href).path

    country = year = None
    info = title_cell.find(class_="production_info")
    if info:
        info_text = info.get_text(" ", strip=True)
        match = _PRODUCTION_INFO_RE.match(info_text)
        if match:
            country = match.group("country") or None
            year = int(match.group("year"))
        else:
            year_match = _YEAR_RE.search(info_text)
            year = int(year_match.group(0)) if year_match else None

    date_cell = row.find("td", class_="plain-list-date")
    rating_cell = row.find("td", class_="plain-list-rating")
    if rating_cell is None:
        rest = [c for c in cells if c is not title_cell and c is not date_cell]
        rating_cell = rest[0] if rest else None
    if date_cell is None and len(cells) >= 3:
        date_cell = cells[-1]

    return Rating(
        kind=kind_from_path(path, default_kind),
        title=link.get_text(" ", strip=True),
        rating=parse_rating_value(rating_cell.get_text(strip=True)) if rating_cell else None,
        url=urljoin(BASE_URL, href),
        slug=_slug(path),
        year=year,
        country=country,
        rated_at=parse_date(date_cell.get_text(strip=True)) if date_cell else None,
    )


# --- Next.js-Fallback -------------------------------------------------------

_RATING_KEYS = ("userRating", "user_rating", "myRating", "rating", "value")
_DATE_KEYS = ("ratedAt", "rated_at", "createdAt", "created_at", "updatedAt", "date")
_ITEM_KEYS = ("item", "movie", "series", "serie", "entity", "rateable")


def _parse_next_data(soup: BeautifulSoup, default_kind: str) -> list[Rating]:
    script = soup.find("script", id="__NEXT_DATA__")
    if not script:
        return []
    try:
        data = json.loads(script.get_text())
    except ValueError:
        return []
    seen: set[tuple] = set()
    ratings: list[Rating] = []
    for node in _walk(data):
        rating = _rating_from_json(node, default_kind)
        if rating:
            key = (rating.kind, rating.slug or rating.title)
            if key not in seen:
                seen.add(key)
                ratings.append(rating)
    return ratings


def _walk(node: Any) -> Iterable[dict]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _rating_from_json(node: dict, default_kind: str) -> Optional[Rating]:
    """Erkennt Objekte der Form ``{rating: .., item: {title, url}}`` o. ä."""
    item = next((node[k] for k in _ITEM_KEYS if isinstance(node.get(k), dict)), None)
    target = item if item is not None else node
    title = target.get("title") or target.get("name")
    if not isinstance(title, str):
        return None

    raw_rating = None
    for key in _RATING_KEYS:
        value = node.get(key)
        if isinstance(value, dict):
            value = value.get("value")
        if isinstance(value, (int, float, str)) and not isinstance(value, bool):
            raw_rating = value
            break
    if raw_rating is None:
        return None
    # Die moviepilot-API liefert Bewertungen als Ganzzahl 0–100.
    rating = parse_rating_value(raw_rating, percent=isinstance(raw_rating, int))
    if rating is None:
        return None

    href = target.get("url") or target.get("path") or target.get("href")
    path = urlparse(href).path if isinstance(href, str) else ""
    year = target.get("year") or target.get("productionYear") or target.get("copyrightYear")
    country = target.get("country") or target.get("productionCountry")
    if isinstance(country, list):
        country = ", ".join(str(c) for c in country) or None

    return Rating(
        kind=kind_from_path(path, default_kind),
        title=title.strip(),
        rating=rating,
        url=urljoin(BASE_URL, href) if path else None,
        slug=target.get("slug") or (_slug(path) if path else None),
        year=int(year) if isinstance(year, (int, str)) and str(year).isdigit() else None,
        country=country if isinstance(country, str) else None,
        rated_at=next((parse_date(node[k]) for k in _DATE_KEYS if node.get(k)), None),
    )


# --- Seiteninformationen ----------------------------------------------------


def find_last_page(html: str) -> Optional[int]:
    """Höchste in der Paginierung verlinkte Seitennummer (falls vorhanden)."""
    pages = [int(m) for m in re.findall(r"[?&](?:amp;)?page=(\d+)", html)]
    return max(pages) if pages else None


def is_private_list(html: str) -> bool:
    """True, wenn moviepilot die Liste als privat und für uns unsichtbar markiert."""
    script = BeautifulSoup(html, "html.parser").find("script", id="__NEXT_DATA__")
    if not script:
        return False
    try:
        props = json.loads(script.get_text())["props"]
    except (ValueError, KeyError, TypeError):
        return False
    page_props = props.get("initialProps", {}).get("pageProps") or props.get("pageProps") or {}
    return bool(page_props.get("isPrivate")) and page_props.get("isVisibleToCurrentUser") is False


def looks_like_login_page(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True).lower() if soup.title else ""
    return "login" in title or "anmelden" in title or bool(
        soup.find("input", attrs={"type": "password"}) and not soup.find("table")
    )
