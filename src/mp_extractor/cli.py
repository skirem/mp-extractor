"""Kommandozeile: ``mp-extractor <nutzername>`` oder ``mp-extractor --from-html ...``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import requests

from .client import ExtractionError, MoviepilotClient, load_cookies, parse_files
from .exporters import FORMATS
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
                   help="Ausgabeformat, mehrfach angebbar (Standard: json, csv und md)")
    p.add_argument("--stdout", action="store_true",
                   help="Nur ein Format direkt auf die Standardausgabe schreiben")
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
    formats = args.formats or list(FORMATS)

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
        else:
            client = MoviepilotClient(delay=args.delay, max_pages=args.max_pages)
            load_cookies(client.session, args.cookie, args.cookie_file)
            ratings = []
            for kind in kinds:
                ratings += client.fetch_ratings(args.username, kind)
    except (ExtractionError, requests.RequestException, OSError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1

    if not ratings:
        print("Warnung: keine Bewertungen gefunden.", file=sys.stderr)

    if args.stdout:
        sys.stdout.write(FORMATS[formats[0]](ratings, args.username))
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"moviepilot_{args.username}" if args.username else "moviepilot"
    for fmt in formats:
        path = args.output_dir / f"{stem}.{fmt}"
        path.write_text(FORMATS[fmt](ratings, args.username), encoding="utf-8")
        print(f"Geschrieben: {path}", file=sys.stderr)
    counts = ", ".join(f"{sum(r.kind == k for r in ratings)} {k}" for k in kinds)
    print(f"Fertig: {counts}.", file=sys.stderr)
    return 0
