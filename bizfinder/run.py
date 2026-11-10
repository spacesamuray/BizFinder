"""The search itself, shared by the command line and the app: find businesses on a map
service, visit their websites and save a spreadsheet."""

import logging
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dotenv import dotenv_values

from . import tomtom, usage
from .enrich import enrich_all
from .export import save
from .models import STOPPED, SearchError
from .places import PlacesClient
from .relevance import mark_relevance
from .tomtom import TomTomClient

log = logging.getLogger("bizfinder")

PROJECT = Path(__file__).resolve().parent.parent
OUTPUT = PROJECT / "output"

# source -> (display name, .env variable holding its key)
SOURCES = {
    "google": ("Google Maps", "GOOGLE_MAPS_API_KEY"),
    "tomtom": ("TomTom", "TOMTOM_API_KEY"),
}


class RunError(Exception):
    """A search that could not start or found nothing. The message says why."""


@dataclass
class Search:
    queries: list[str]
    location: str
    source: str | None = None  # default: the first source with a key, Google first
    deep: bool = False
    depth: int | None = None
    limit: int | None = None
    language: str | None = None
    crawl: bool = True
    workers: int = 10
    out: Path | None = None  # default: output/<queries>_<place>_<time>.xlsx
    api_key: str | None = None  # default: the key in .env


@dataclass
class Result:
    path: Path
    found: int  # businesses that match the search
    others: int  # results that don't look like a match
    requests: int
    stopped: bool


def has_key(source):
    return bool(_key(SOURCES[source][1]))


def run(search, stop=None, progress=None):
    """Run `search` and save the spreadsheet. Returns a Result, or raises RunError.

    `stop` (a threading.Event) ends the search early and saves what was found so far.
    `progress(**state)` is called with the stage ("search", "websites", "save") and counts.
    """
    progress = progress or (lambda **state: None)
    source = search.source or next((s for s in SOURCES if has_key(s)), "google")
    source_name, key_var = SOURCES[source]
    api_key = (search.api_key or _key(key_var)).strip()
    if not api_key:
        raise RunError(f"No {source_name} API key found. Put {key_var}=your-key in the .env file (see README.md).")

    if source == "google":
        client = PlacesClient(api_key, language=search.language)
        depth = (search.depth or 2) if search.deep else 0
    else:
        client = TomTomClient(api_key, language=search.language)
        depth = search.depth or tomtom.DEFAULT_DEPTH
    client.stop = stop

    try:
        businesses, error = _find(client, source, source_name, search, depth, stop, progress)
    finally:
        usage.add(source, client.requests_made)
    if not businesses:
        raise RunError(error or "No businesses found.")

    enrich_all(
        businesses,
        workers=search.workers,
        crawl=search.crawl,
        stop=stop,
        progress=lambda checked, total: progress(stage="websites", checked=checked, total=total),
    )

    progress(stage="save")
    out = search.out or _default_output(search.queries, search.location)
    out.parent.mkdir(parents=True, exist_ok=True)
    notes = save(businesses, out, f"{', '.join(search.queries)} in {search.location}", source=source_name)

    matches = [b for b in businesses if b.relevant is not False]
    websites = Counter(b.has_website for b in matches)
    log.info("")
    log.info("Saved %d businesses to %s", len(matches), out)
    for note in notes:
        log.info("  + %s", note)
    log.info(
        "  website: %d | only social page: %d | only Wolt/Glovo/... page: %d | no website: %d | with email: %d",
        websites["Yes"],
        websites["Only social page"],
        websites["Only listing page"],
        websites["No"],
        sum(1 for b in matches if b.emails),
    )
    allowance = "free up to 2,500 a day" if source == "tomtom" else "1,000 free a month"
    log.info(
        "%s API requests used: %d (%s; %d today)",
        source_name,
        client.requests_made,
        allowance,
        usage.today(source)["used"],
    )
    return Result(
        path=out,
        found=len(matches),
        others=len(businesses) - len(matches),
        requests=client.requests_made,
        stopped=bool(stop and stop.is_set()),
    )


def _find(client, source, source_name, search, depth, stop, progress):
    """Run every query on the map service. Businesses found by several are listed once.
    Returns (businesses, the error that ended the search early or None)."""
    found = {}
    error = None
    for step, query in enumerate(search.queries, 1):
        log.info('Searching %s for "%s" in %s...', source_name, query, search.location)
        progress(stage="search", query=query, step=step, steps=len(search.queries), found=len(found))
        before = len(found)
        results = []
        try:
            for business in client.search(query, search.location, limit=search.limit, depth=depth):
                business = found.setdefault(business.place_id, business)
                if query not in business.queries:
                    business.queries.append(query)
                results.append(business)
                progress(found=len(found), requests=client.requests_made)
                if stop is not None and stop.is_set():
                    raise SearchError(STOPPED)
        except SearchError as e:
            error = str(e)
        except KeyboardInterrupt:
            error = STOPPED
        progress(found=len(found), requests=client.requests_made)
        log.info("  %d new businesses", len(found) - before)
        # Also for a search cut short, so partial results are sorted too.
        if source == "google":  # TomTom results are already filtered by tomtom.py
            mark_relevance(results, query)
        if error == STOPPED:
            log.warning("%s Keeping the %d businesses found so far.", error, len(found))
            break
        if error:
            log.error("%s", error)
            if found:
                log.warning("Continuing with the %d businesses found before that.", len(found))
            break
    return list(found.values()), error


def _key(var):
    """A key from the environment or, read fresh each time, from .env."""
    return os.environ.get(var) or dotenv_values(PROJECT / ".env").get(var) or ""


def _default_output(queries, location):
    stem = f"{_slug(' '.join(queries))}_{_slug(location)}_{datetime.now():%Y%m%d-%H%M}"
    path = OUTPUT / f"{stem}.xlsx"
    n = 2
    while path.exists():  # two searches in the same minute
        path = OUTPUT / f"{stem}-{n}.xlsx"
        n += 1
    return path


def _slug(text):
    return re.sub(r"\W+", "-", text.lower()).strip("-")[:50]
