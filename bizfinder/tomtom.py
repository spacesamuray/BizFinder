"""Client for the TomTom Search API: the free alternative to Google.

The free plan allows 2,500 requests a day with no payment card. TomTom has
phone numbers for most businesses but websites for far fewer than Google.

Docs: https://developer.tomtom.com/search-api/documentation/search-service/search-service
"""

import logging
import math
import time
from functools import partial
from urllib.parse import quote, quote_plus

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import STOPPED, Business, SearchError
from .relevance import keywords, name_matches, normalize
from .tiles import Box, search_tiles

log = logging.getLogger(__name__)

BASE_URL = "https://api.tomtom.com/search/2"
MAX_PER_SEARCH = 100  # TomTom returns at most 100 places per search, with no further pages
MIN_INTERVAL = 0.22  # seconds between requests; the free plan allows about 5 per second
DEFAULT_DEPTH = 4  # requests are free, so split crowded areas finely by default


class TomTomClient:
    def __init__(self, api_key, language=None):
        self.api_key = api_key
        self.language = language
        self.requests_made = 0
        self.stop = None  # a threading.Event; once set, the next request ends the search
        self._areas = {}
        self._categories = None
        self._last_request = 0.0
        self.session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504), raise_on_status=False)
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def search(self, query, location, limit=None, depth=DEFAULT_DEPTH):
        """Yield up to `limit` businesses matching `query` in `location`.

        The area is always searched box by box (see tiles.py), and each box
        twice: by TomTom category ("dentist" finds every dentist) and by name
        ("flower shop" finds "IK Flowers"), because TomTom files many shops
        under a generic "shop" category. TomTom's own matching is very loose
        ("flower shop" also returns bakeries and beauty salons), so only places
        in the query's category or with a query word in their name are kept.
        """
        limit = limit or math.inf
        area = self._area(location)
        categories = self._category_ids(query)
        words = keywords(query)
        if not categories:
            log.warning(
                '  TomTom has no "%s" category, so only names containing %s are found. '
                'TomTom categories are simple English words, e.g. "dentist" or "florist".',
                query,
                " or ".join(f'"{w}"' for w in words) or "it",
            )

        # The name search looks for the distinctive words only: "flower", not "flower shop".
        passes = [("poiSearch", " ".join(words) or query)]
        if categories:
            passes.insert(0, ("categorySearch", query))

        seen = set()
        for endpoint, text in passes:
            search_box = partial(self._search_box, endpoint, text, categories)
            for result in search_tiles(area, depth, MAX_PER_SEARCH, search_box):
                if result["id"] in seen or not _relevant(result, categories, words):
                    continue
                seen.add(result["id"])
                yield _to_business(result, query)
                if len(seen) >= limit:
                    return

    def _search_box(self, endpoint, query, categories, box):
        params = {
            "limit": MAX_PER_SEARCH,
            "topLeft": f"{box.north},{box.west}",
            "btmRight": f"{box.south},{box.east}",
        }
        if endpoint == "categorySearch":
            params["categorySet"] = ",".join(map(str, categories))
        return self._get(f"{endpoint}/{quote(query)}.json", params).get("results", [])

    def _category_ids(self, query):
        """IDs of the TomTom categories named like `query` ("flower shop" -> Florists)."""
        if self._categories is None:
            self._categories = self._get("poiCategories.json", {}).get("poiCategories", [])
        wanted = normalize(query)
        return {
            category["id"]
            for category in self._categories
            if wanted in {normalize(name) for name in [category["name"], *category.get("synonyms", [])]}
        }

    def _area(self, location):
        """Bounding box of a city or area, e.g. "Tbilisi, Georgia"."""
        if location not in self._areas:
            results = self._get(f"geocode/{quote(location)}.json", {"limit": 1}).get("results") or [{}]
            bounds = results[0].get("boundingBox") or results[0].get("viewport")
            if not bounds:
                raise SearchError(f'Could not find the area "{location}" on TomTom.')
            top_left, bottom_right = bounds["topLeftPoint"], bounds["btmRightPoint"]
            self._areas[location] = Box(
                bottom_right["lat"], top_left["lon"], top_left["lat"], bottom_right["lon"]
            )
        return self._areas[location]

    def _get(self, path, params):
        if self.stop is not None and self.stop.is_set():
            raise SearchError(STOPPED)
        wait = self._last_request + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

        params = {**params, "key": self.api_key}
        if self.language:
            params["language"] = self.language
        try:
            resp = self.session.get(f"{BASE_URL}/{path}", params=params, timeout=30)
        except requests.RequestException as e:
            # The key is part of the URL, so keep it out of error messages.
            message = str(e).replace(self.api_key, "***")
            raise SearchError(f"Could not reach the TomTom API: {message}") from None
        self.requests_made += 1
        if not resp.ok:
            raise SearchError(f"TomTom API error (HTTP {resp.status_code}): {_error_message(resp)}")
        return resp.json()


def _error_message(resp):
    try:
        data = resp.json()
        return data.get("detailedError", {}).get("message") or data.get("errorText") or resp.text[:300]
    except ValueError:
        return resp.text[:300]


def _relevant(result, categories, words):
    poi = result.get("poi", {})
    # Subcategory IDs start with their parent's ID (Restaurant 7315 -> 7315025).
    ids = [str(c.get("id")) for c in poi.get("categorySet", [])]
    in_category = any(i.startswith(str(c)) for i in ids for c in categories)
    return in_category or name_matches(poi.get("name", ""), words)


def _to_business(result, query):
    poi = result.get("poi", {})
    position = result.get("position", {})
    name = poi.get("name", "")
    address = result.get("address", {}).get("freeformAddress", "")
    website = poi.get("url", "")
    if website and "://" not in website:
        website = "http://" + website  # TomTom leaves out the scheme ("flowerstudio.ge")
    return Business(
        place_id=result["id"],
        name=name,
        queries=[query],
        category=(poi.get("categories") or [""])[0].capitalize(),
        address=address,
        phone=poi.get("phone", ""),
        website=website,
        # TomTom has no ratings or reviews; this opens the business on Google Maps to check them.
        maps_url="https://www.google.com/maps/search/?api=1&query=" + quote_plus(f"{name}, {address}"),
        lat=position.get("lat"),
        lng=position.get("lon"),
    )
