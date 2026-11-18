"""Kommandozeile: ``mp-extractor <nutzername>`` oder ``mp-extractor --from-html ...``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import requests

from .client import ExtractionError, MoviepilotClient, add_external_ids, load_cookies, parse_files
from .exporters import DEFAULT_FORMATS, EXTENSIONS, FORMATS, to_trakt_csv
from .models import KINDS, MOVIE, SERIES

TYPE_CHOICES = {"movies": [MOVIE], "series": [SERIES], "all": list(KINDS)}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mp-extractor",
        description="Exportiert Film- und Serienbewertungen von moviepilot.de "
                    "als JSON, CSV und Markdown.",
    )
    p.add_argument("username", nargs="?", help="moviepilot-Nutzername (aus der Profil-URL)")
    p.add_argument("-t", "--type", choices=TYPE_CHOICES, default="all",
                   help="Was exportiert werden soll (Standard: all)")
    p.add_argument("-o", "--output-dir", type=Path, default=Path("export"),
                   help="Zielordner (Standard: ./export)")
    p.add_argument("-f", "--format", dest="formats", action="append", choices=FORMATS,
                   help="Ausgabeformat, mehrfach angebbar (Standard: json, csv und md). "
                        "'trakt' erzeugt eine Importdatei für trakt.tv und lädt dafür die IMDb-IDs")
    p.add_argument("--stdout", action="store_true",
                   help="Nur ein Format direkt auf die Standardausgabe schreiben")
    p.add_argument("--with-ids", action="store_true",
                   help="IMDb-/TVDB-IDs von den Detailseiten laden (ca. 1–2 s pro Titel, wird gecacht)")
    p.add_argument("--no-ids", action="store_true",
                   help="Bei -f trakt keine IDs laden (schnell; Trakt muss dann über Titel und Jahr zuordnen)")
    p.add_argument("--trakt-watched", action="store_true",
                   help="In der Trakt-Datei alle bewerteten Titel auch als gesehen markieren")
    p.add_argument("--limit", type=int, metavar="N",
                   help="Nur die ersten N Einträge je Liste exportieren (zum Testen)")
    p.add_argument("--from-html", nargs="+", type=Path, metavar="DATEI",
                   help="Offline-Modus: gespeicherte HTML-Seiten statt Download einlesen")
    p.add_argument("--cookie", help='Cookie-Header aus dem Browser, z. B. "_session=..."')
    p.add_argument("--cookie-file", type=Path, help="Cookies im Netscape-Format (cookies.txt)")
    p.add_argument("--delay", type=float, default=1.5,
                   help="Pause zwischen Seitenabrufen in Sekunden (Standard: 1.5)")
    p.add_argument("--max-pages", type=int, default=500, help="Sicherheitslimit für Seiten pro Liste")
    p.add_argument("-v", "--verbose", action="store_true", help="Fortschritt ausgeben")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(message)s", stream=sys.stderr)
    kinds = TYPE_CHOICES[args.type]
    formats = args.formats or DEFAULT_FORMATS

    if not args.username and not args.from_html:
        print("Fehler: Nutzername oder --from-html angeben (siehe --help).", file=sys.stderr)
        return 2
    if args.stdout and len(formats) != 1:
        print("Fehler: --stdout braucht genau ein --format.", file=sys.stderr)
        return 2

    try:
        if args.from_html:
            kind = kinds[0] if len(kinds) == 1 else None
            ratings = [r for r in parse_files(args.from_html, kind) if r.kind in kinds]
            if args.limit:
                ratings = [r for k in kinds for r in [x for x in ratings if x.kind == k][: args.limit]]
        else:
            client = MoviepilotClient(delay=args.delay, max_pages=args.max_pages)
            load_cookies(client.session, args.cookie, args.cookie_file)
            ratings = []
            for kind in kinds:
                ratings += client.fetch_ratings(args.username, kind)[: args.limit]
            if args.with_ids or ("trakt" in formats and not args.no_ids):
                add_external_ids(client, ratings, args.output_dir / ".mp-extractor-ids.json")
    except (ExtractionError, requests.RequestException, OSError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1

    if not ratings:
        print("Warnung: keine Bewertungen gefunden.", file=sys.stderr)

    # Mit geladenen IDs kommen Titel ohne IMDb-ID in eine eigene Datei, damit Trakt
    # nichts über Titel/Jahr raten muss (das führte im Test zu falschen Treffern).
    with_ids = any(r.imdb_id for r in ratings)
    trakt_rows = [r for r in ratings if r.imdb_id] if with_ids else ratings
    without_id = [r for r in ratings if not r.imdb_id] if with_ids else []

    def render(fmt: str) -> str:
        if fmt == "trakt":
            return to_trakt_csv(trakt_rows, watched=args.trakt_watched)
        return FORMATS[fmt](ratings, args.username)

    if args.stdout:
        sys.stdout.write(render(formats[0]))
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"moviepilot_{args.username}" if args.username else "moviepilot"
    for fmt in formats:
        path = args.output_dir / f"{stem}.{EXTENSIONS.get(fmt, fmt)}"
        path.write_text(render(fmt), encoding="utf-8")
        print(f"Geschrieben: {path}", file=sys.stderr)
    counts = ", ".join(f"{sum(r.kind == k for r in ratings)} {k}" for k in kinds)
    print(f"Fertig: {counts}.", file=sys.stderr)
    if "trakt" in formats and without_id:
        path = args.output_dir / f"{stem}.trakt-ohne-id.csv"
        path.write_text(to_trakt_csv(without_id, watched=args.trakt_watched), encoding="utf-8")
        titles = ", ".join(r.title for r in without_id[:10]) + (" …" if len(without_id) > 10 else "")
        print(f"Hinweis: {len(without_id)} Titel ohne IMDb-ID stehen getrennt in {path} "
              f"(bitte von Hand bei Trakt eintragen): {titles}", file=sys.stderr)
    return 0
