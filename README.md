# mp-extractor

Exportiert deine **Film- und Serienbewertungen von [moviepilot.de](https://www.moviepilot.de)**
in drei Formate:

| Datei | Für | Inhalt |
|---|---|---|
| `moviepilot_<name>.json` | Maschinen | Metadaten, Statistiken und alle Bewertungen (UTF-8, ISO-Datumsangaben) |
| `moviepilot_<name>.csv` | Excel, LibreOffice, pandas | Eine Zeile pro Bewertung |
| `moviepilot_<name>.md` | Menschen | Überblick, Verteilung und sortierte Tabellen mit Links |

## Installation

```bash
git clone https://github.com/skirem/mp-extractor.git
cd mp-extractor
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

Benötigt Python ≥ 3.10.

## Benutzung

### 1. Direkt von moviepilot laden

```bash
mp-extractor DEIN_NUTZERNAME            # Filme und Serien -> ./export/
mp-extractor DEIN_NUTZERNAME -t movies  # nur Filme
mp-extractor DEIN_NUTZERNAME -f json -f csv -o ~/backup
```

Den Nutzernamen findest du in deiner Profil-URL: `https://www.moviepilot.de/users/<nutzername>`.
Geladen werden die Seiten `/users/<nutzername>/rated/movies` und `/rated/series`,
inklusive aller Unterseiten (`?page=2`, …). Zwischen den Abrufen wird 1,5 s gewartet
(`--delay`), um moviepilot nicht zu belasten.

**Login nötig?** Wenn deine Listen nicht öffentlich sind, meldet das Tool das. Dann:

1. Im Browser bei moviepilot einloggen.
2. Entwicklertools (F12) → *Netzwerk* → Seite neu laden → bei einer Anfrage an
   moviepilot.de den Wert des `Cookie`-Headers kopieren.
3. `mp-extractor DEIN_NUTZERNAME --cookie "…kopierter Wert…"`

Alternativ eine `cookies.txt` (Netscape-Format, z. B. per Browser-Erweiterung exportiert)
mit `--cookie-file cookies.txt` übergeben. Cookies sind wie ein Passwort – nicht weitergeben.

### 2. Offline aus gespeicherten Seiten

Falls der direkte Abruf blockiert wird: Bewertungsseiten im Browser öffnen,
mit *Strg+S* als „Webseite, nur HTML“ speichern und einlesen:

```bash
mp-extractor --from-html filme_seite1.html filme_seite2.html serien.html
```

Dateien mit „serie“ im Namen werden als Serien behandelt, sofern der Link-Pfad
(`/movies/…` bzw. `/serie/…`) es nicht ohnehin verrät.

### Alle Optionen

```
mp-extractor [nutzername] [-t {movies,series,all}] [-o ORDNER] [-f {json,csv,md}]...
             [--stdout] [--from-html DATEI ...] [--cookie COOKIE] [--cookie-file DATEI]
             [--delay SEKUNDEN] [--max-pages N] [-v]
```

`--stdout` schreibt genau ein Format auf die Standardausgabe, z. B. zum Weiterverarbeiten:

```bash
mp-extractor DEIN_NUTZERNAME -f json --stdout | jq '.ratings[] | select(.rating >= 9) | .title'
```

## Datenformat

Jede Bewertung hat diese Felder (in JSON und CSV identisch):

| Feld | Beispiel | Bedeutung |
|---|---|---|
| `kind` | `movie` / `series` | Film oder Serie |
| `title` | `Star Trek - Der Film` | Titel, wie auf moviepilot angezeigt |
| `rating` | `9.5` | Bewertung auf der moviepilot-Skala 0.0–10.0 (Schritte 0.5) |
| `url` | `https://www.moviepilot.de/movies/star-trek-der-film` | Seite auf moviepilot |
| `slug` | `star-trek-der-film` | Eindeutiger Kurzname aus der URL |
| `year` | `1979` | Produktionsjahr |
| `country` | `USA` | Produktionsland |
| `rated_at` | `2019-04-02` | Datum der Bewertung (ISO 8601) |

Die JSON-Datei enthält zusätzlich `stats` je Typ (Anzahl, Durchschnitt, Median, Verteilung).

## Entwicklung

```bash
pip install -e '.[dev]'
pytest
```

Die Tests laufen ohne Netzwerk gegen Beispielseiten in `tests/fixtures/`.
Der Parser liest die klassische Tabellenansicht von moviepilot und hat einen
Fallback für die in Next.js eingebetteten JSON-Daten (`__NEXT_DATA__`). Ändert
moviepilot das Layout, ist `src/mp_extractor/parser.py` die Stelle zum Anpassen.

## Hinweis

Inoffizielles Tool, nicht mit moviepilot verbunden. Gedacht für den Export der
eigenen Bewertungen; bitte die Nutzungsbedingungen von moviepilot beachten.
