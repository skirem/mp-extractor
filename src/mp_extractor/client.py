"""Lädt die Bewertungslisten eines Nutzers von moviepilot.de."""

from __future__ import annotations

import http.cookiejar
import json
import logging
import time
from pathlib import Path
from typing import Callable, Optional

import requests

from .models import MOVIE, SERIES, Rating
from .parser import (
    BASE_URL,
    find_last_page,
    is_private_list,
    looks_like_login_page,
    parse_external_ids,
    parse_ratings_page,
)

log = logging.getLogger(__name__)

LIST_PATHS = {MOVIE: "movies", SERIES: "series"}
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36 mp-extractor/0.1"
)


class ExtractionError(RuntimeError):
    pass


def ratings_url(username: str, kind: str, page: int = 1) -> str:
    url = f"{BASE_URL}/users/{username}/rated/{LIST_PATHS[kind]}"
    return f"{url}?page={page}" if page > 1 else url


def load_cookies(session: requests.Session, cookie: Optional[str], cookie_file: Optional[Path]) -> None:
    """Übernimmt Browser-Cookies für eingeloggte Abrufe.

    ``cookie`` ist ein Header-String ("name=wert; name2=wert2"),
    ``cookie_file`` eine Datei im Netscape-Format (cookies.txt).
    """
    if cookie_file:
        jar = http.cookiejar.MozillaCookieJar(str(cookie_file))
        jar.load(ignore_discard=True, ignore_expires=True)
        session.cookies.update(jar)
    if cookie:
        for part in cookie.split(";"):
            name, sep, value = part.strip().partition("=")
            if sep:
                session.cookies.set(name, value, domain=".moviepilot.de")


class MoviepilotClient:
    def __init__(
        self,
        session: Optional[requests.Session] = None,
        delay: float = 1.5,
        max_pages: int = 500,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.session.headers.setdefault("Accept-Language", "de-DE,de;q=0.9")
        self.delay = delay
        self.max_pages = max_pages
        self._sleep = sleep

    def fetch(self, url: str) -> str:
        log.info("Lade %s", url)
        response = self.session.get(url, timeout=30)
        if response.status_code == 404:
            raise ExtractionError(f"Seite nicht gefunden (404): {url} – stimmt der Nutzername?")
        response.raise_for_status()
        response.encoding = response.encoding or "utf-8"
        return response.text

    def fetch_ratings(self, username: str, kind: str) -> list[Rating]:
        """Lädt alle Seiten einer Liste, bis keine neuen Einträge mehr kommen."""
        ratings: list[Rating] = []
        seen: set[str] = set()
        last_page: Optional[int] = None

        for page in range(1, self.max_pages + 1):
            if page > 1:
                self._sleep(self.delay)
            html = self.fetch(ratings_url(username, kind, page))
            page_ratings = parse_ratings_page(html, default_kind=kind)

            if page == 1:
                last_page = find_last_page(html)
                if not page_ratings and is_private_list(html):
                    raise ExtractionError(
                        f"Die Bewertungen von {username} sind auf moviepilot privat. "
                        "Entweder im Profil öffentlich schalten oder die Cookies deiner "
                        "eingeloggten Browser-Sitzung übergeben (--cookie oder --cookie-file)."
                    )
                if not page_ratings and looks_like_login_page(html):
                    raise ExtractionError(
                        "moviepilot verlangt einen Login für diese Liste. "
                        "Bitte Cookies aus dem Browser übergeben (--cookie oder --cookie-file)."
                    )

            new = [r for r in page_ratings if (r.url or r.title) not in seen]
            for r in new:
                seen.add(r.url or r.title)
            ratings.extend(new)
            log.info("Seite %d: %d Einträge (%d neu)", page, len(page_ratings), len(new))

            if not new or (last_page is not None and page >= last_page):
                break
        return ratings


def add_external_ids(client: "MoviepilotClient", ratings: list[Rating], cache_file: Path) -> None:
    """Ergänzt IMDb-/TVDB-IDs über die Detailseiten (eine Anfrage pro Titel).

    Gefundene IDs werden in ``cache_file`` gemerkt, damit ein erneuter Lauf schnell ist.
    """
    cache: dict = {}
    if cache_file.exists():
        cache = json.loads(cache_file.read_text(encoding="utf-8"))

    def save() -> None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")

    todo = [r for r in ratings if r.url and r.url not in cache]
    log.info("IDs: %d im Cache, %d werden geladen", len(ratings) - len(todo), len(todo))
    try:
        for i, r in enumerate(todo, 1):
            if i > 1:
                client._sleep(client.delay)
            try:
                imdb_id, tvdb_id = parse_external_ids(client.fetch(r.url))
            except (ExtractionError, requests.RequestException) as exc:
                log.warning("Keine IDs für %s: %s", r.title, exc)
                continue
            cache[r.url] = {"imdb_id": imdb_id, "tvdb_id": tvdb_id}
            if i % 25 == 0:
                log.warning("IDs: %d/%d geladen", i, len(todo))
                save()
    finally:
        save()

    for r in ratings:
        ids = cache.get(r.url or "", {})
        r.imdb_id = ids.get("imdb_id")
        r.tvdb_id = ids.get("tvdb_id")


def parse_files(paths: list[Path], kind: Optional[str] = None) -> list[Rating]:
    """Offline-Modus: liest im Browser gespeicherte HTML-Seiten ein."""
    ratings: list[Rating] = []
    seen: set[tuple] = set()
    for path in paths:
        default_kind = kind or (SERIES if "serie" in path.name.lower() else MOVIE)
        for r in parse_ratings_page(path.read_text(encoding="utf-8", errors="replace"), default_kind):
            key = (r.kind, r.url or r.title)
            if key not in seen:
                seen.add(key)
                ratings.append(r)
    return ratings
