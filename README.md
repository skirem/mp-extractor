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

**Profil privat?** Dann bricht das Tool mit einem Hinweis ab. Am einfachsten in den
moviepilot-Profileinstellungen **„Mein Profil öffentlich zeigen“** und **„Meine Bewertungen
in meinem Profil öffentlich zeigen“** anhaken. „Bewertungen öffentlich“ allein reicht nicht.
Danach kannst du die Haken wieder entfernen.

Alternativ mit Login-Cookies:

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

### Umzug zu Trakt

```bash
mp-extractor DEIN_NUTZERNAME -f trakt --limit 10   # erst mit 10 Filmen + 10 Serien testen
mp-extractor DEIN_NUTZERNAME -f trakt              # dann alles
```

Erzeugt `moviepilot_<name>.trakt.csv` für den Datei-Import auf trakt.tv
(Einstellungen → Import). Trakt ordnet Titel über IDs zu, deshalb lädt das Tool für
jeden Titel die IMDb-ID (Serien zusätzlich die TVDB-ID) von der moviepilot-Detailseite:
eine Anfrage pro Titel, bei ~1300 Titeln also rund eine halbe Stunde. Die IDs werden in
`export/.mp-extractor-ids.json` gecacht, ein zweiter Lauf ist schnell.

- Trakt kennt nur ganze Zahlen von 1 bis 10: halbe Punkte werden **aufgerundet**
  (7,5 → 8), 0 und 0,5 werden zu 1.
- `--no-ids` überspringt den ID-Abruf (dauert dann nur ~1 Minute). Trakt muss die
  Titel dann über Titel und Jahr finden, was bei deutschen Titeln unsicherer ist.
- `--trakt-watched` markiert alle bewerteten Titel zusätzlich als gesehen
  (Datum = Bewertungsdatum).

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
| `genres` | `["Kriminalfilm", "Komödie"]` | Genres (in der CSV kommagetrennt) |
| `community_rating` | `7.3` | Durchschnitt der moviepilot-Community, 0.0–10.0 |
| `moviepilot_id` | `18755` | Interne ID bei moviepilot |
| `imdb_id`, `tvdb_id` | `tt1032755` | Nur mit `--with-ids` oder `-f trakt` |

Die JSON-Datei enthält zusätzlich `stats` je Typ (Anzahl, Durchschnitt, Median, Verteilung).

## Entwicklung

```bash
pip install -e '.[dev]'
pytest
```

Die Tests laufen ohne Netzwerk gegen Beispielseiten in `tests/fixtures/`.
Der Parser liest die in Next.js eingebetteten Seitendaten (`__NEXT_DATA__` →
`pageProps.items`, Stand November 2026) und hat Fallbacks für die ältere
Tabellenansicht. Ändert
moviepilot das Layout, ist `src/mp_extractor/parser.py` die Stelle zum Anpassen.

## Hinweis

Inoffizielles Tool, nicht mit moviepilot verbunden. Gedacht für den Export der
eigenen Bewertungen; bitte die Nutzungsbedingungen von moviepilot beachten.
