import csv
import io
import json
from pathlib import Path

import pytest

from mp_extractor import cli
from mp_extractor.client import ExtractionError, MoviepilotClient, parse_files, ratings_url
from mp_extractor.exporters import compute_stats, to_csv, to_json, to_markdown
from mp_extractor.models import MOVIE, SERIES
from mp_extractor.parser import parse_date, parse_rating_value, parse_ratings_page

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code
        self.encoding = "utf-8"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, pages):
        self.pages = pages
        self.headers = {}
        self.cookies = None
        self.requested = []

    def get(self, url, timeout=None):
        self.requested.append(url)
        if url not in self.pages:
            return FakeResponse("", 404)
        return FakeResponse(self.pages[url])


@pytest.mark.parametrize("raw,percent,expected", [
    ("9.5", False, 9.5), ("8,0", False, 8.0), ("10", False, 10.0), (85, True, 8.5),
    (7, True, 0.5), ("abc", False, None), (None, False, None), ("95", False, 9.5),
])
def test_parse_rating_value(raw, percent, expected):
    assert parse_rating_value(raw, percent=percent) == expected


def test_parse_date():
    assert parse_date("02.04.2019") == "2019-04-02"
    assert parse_date("2023-05-06T20:15:00+02:00") == "2023-05-06"
    assert parse_date("gestern") is None


def test_parse_table_page():
    ratings = parse_ratings_page(fixture("movies_page1.html"))
    assert [r.title for r in ratings] == ["Star Trek - Der Film", "Das Boot | Director's Cut"]
    first = ratings[0]
    assert first.kind == MOVIE
    assert first.rating == 9.5
    assert first.year == 1979
    assert first.country == "USA"
    assert first.rated_at == "2019-04-02"
    assert first.url == "https://www.moviepilot.de/movies/star-trek-der-film"
    assert first.slug == "star-trek-der-film"
    assert ratings[1].rating == 8.0


def test_parse_series_page_detects_kind():
    (series,) = parse_ratings_page(fixture("series_page1.html"), default_kind=MOVIE)
    assert series.kind == SERIES
    assert series.rating == 10.0


def test_parse_next_data_fallback():
    dune, lost = parse_ratings_page(fixture("next_data_page.html"))
    assert (dune.title, dune.rating, dune.year, dune.rated_at) == ("Dune", 8.5, 2021, "2023-05-06")
    assert lost.kind == SERIES and lost.rating == 4.0


def test_client_follows_pagination():
    session = FakeSession({
        ratings_url("testuser", MOVIE): fixture("movies_page1.html"),
        ratings_url("testuser", MOVIE, 2): fixture("movies_page2.html"),
    })
    client = MoviepilotClient(session=session, sleep=lambda s: None)
    ratings = client.fetch_ratings("testuser", MOVIE)
    assert len(ratings) == 3
    assert session.requested == [
        "https://www.moviepilot.de/users/testuser/rated/movies",
        "https://www.moviepilot.de/users/testuser/rated/movies?page=2",
    ]


def test_client_stops_when_page_repeats():
    page = fixture("movies_page1.html")
    session = FakeSession({ratings_url("u", MOVIE, n): page for n in range(1, 4)})
    client = MoviepilotClient(session=session, sleep=lambda s: None)
    # Seite 2 liefert dieselben Einträge wie Seite 1 -> Abbruch statt Endlosschleife
    assert len(client.fetch_ratings("u", MOVIE)) == 2


def test_client_detects_login():
    session = FakeSession({ratings_url("u", SERIES): fixture("login_page.html")})
    with pytest.raises(ExtractionError, match="Login"):
        MoviepilotClient(session=session).fetch_ratings("u", SERIES)


def test_client_unknown_user():
    with pytest.raises(ExtractionError, match="404"):
        MoviepilotClient(session=FakeSession({})).fetch_ratings("nobody", MOVIE)


def _all_ratings():
    return parse_files([FIXTURES / "movies_page1.html", FIXTURES / "movies_page2.html",
                        FIXTURES / "series_page1.html"])


def test_stats():
    stats = compute_stats([r for r in _all_ratings() if r.kind == MOVIE])
    assert stats["count"] == 3
    assert stats["average"] == 6.67
    assert stats["median"] == 8.0
    assert stats["distribution"] == {"9.5": 1, "8.0": 1, "2.5": 1}


def test_json_export():
    doc = json.loads(to_json(_all_ratings(), "testuser"))
    assert doc["username"] == "testuser"
    assert doc["stats"]["movie"]["count"] == 3
    assert doc["stats"]["series"]["count"] == 1
    assert doc["ratings"][0]["title"] == "Star Trek - Der Film"  # bestbewerteter Film zuerst
    assert doc["ratings"][-1]["kind"] == "series"


def test_csv_export():
    rows = list(csv.DictReader(io.StringIO(to_csv(_all_ratings()))))
    assert len(rows) == 4
    assert rows[1]["title"] == "Das Boot | Director's Cut"
    assert rows[1]["rating"] == "8.0"


def test_markdown_export():
    md = to_markdown(_all_ratings(), "testuser")
    assert "# moviepilot-Bewertungen von testuser" in md
    assert "| Filme | 3 | 6,67 | 8,0 |" in md
    assert "[Das Boot \\| Director's Cut](https://www.moviepilot.de/movies/das-boot)" in md
    assert "| 9,5 | [Star Trek - Der Film]" in md


def test_cli_offline(tmp_path, capsys):
    files = [str(FIXTURES / n) for n in ("movies_page1.html", "series_page1.html")]
    assert cli.main(["--from-html", *files, "-o", str(tmp_path)]) == 0
    assert {p.name for p in tmp_path.iterdir()} == {"moviepilot.json", "moviepilot.csv", "moviepilot.md"}
    assert cli.main(["--from-html", *files, "--stdout", "-f", "csv", "-t", "series"]) == 0
    out = capsys.readouterr().out
    assert "Breaking Bad" in out and "Star Trek" not in out


def test_cli_requires_input(capsys):
    assert cli.main([]) == 2
