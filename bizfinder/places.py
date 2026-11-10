"""Client for the Google Places API (New) Text Search endpoint.

Docs: https://developers.google.com/maps/documentation/places/web-service/text-search
"""

import math

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import STOPPED, Business, SearchError
from .tiles import Box, search_tiles

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

PAGE_SIZE = 20  # Google's maximum per page
MAX_PER_SEARCH = 60  # Google never returns more than this for one search

# Only these fields are requested (and billed). Phone, website and rating put
# each request in the "Text Search Enterprise" pricing tier.
PLACE_FIELDS = (
    "id",
    "displayName",
    "primaryTypeDisplayName",
    "formattedAddress",
    "nationalPhoneNumber",
    "internationalPhoneNumber",
    "websiteUri",
    "googleMapsUri",
    "rating",
    "userRatingCount",
    "businessStatus",
    "location",
    "types",
)
FIELD_MASK = ",".join([f"places.{f}" for f in PLACE_FIELDS] + ["nextPageToken"])

BUSINESS_STATUS = {
    "OPERATIONAL": "Open",
    "CLOSED_TEMPORARILY": "Temporarily closed",
    "CLOSED_PERMANENTLY": "Permanently closed",
}


class PlacesClient:
    def __init__(self, api_key, language=None):
        self.language = language
        self.requests_made = 0
        self.stop = None  # a threading.Event; once set, the next request ends the search
        self.session = requests.Session()
        self.session.headers["X-Goog-Api-Key"] = api_key
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=None,  # Places searches are POSTs
            raise_on_status=False,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def search(self, query, location, limit=None, depth=0):
        """Yield up to `limit` businesses matching `query` in `location`.

        One Google search returns at most 60 places. With depth > 0 the area is
        searched tile by tile instead: every tile that comes back full is split
        into four smaller tiles, up to `depth` times. That finds far more
        businesses in big cities, at the cost of extra API requests.
        """
        limit = limit or math.inf
        if depth == 0:
            places = self._results({"textQuery": f"{query} in {location}"}, min(limit, MAX_PER_SEARCH))
        else:
            places = search_tiles(
                self._area(location),
                depth,
                MAX_PER_SEARCH,
                lambda box: self._results(
                    {"textQuery": query, "locationRestriction": {"rectangle": _rectangle(box)}},
                    MAX_PER_SEARCH,
                ),
            )
        for count, place in enumerate(places, 1):
            yield _to_business(place, query)
            if count >= limit:
                return

    def _area(self, location):
        """Bounding box of a city or area, e.g. "Tbilisi, Georgia"."""
        data = self._post({"textQuery": location, "pageSize": 1}, "places.viewport")
        places = data.get("places") or [{}]
        if "viewport" not in places[0]:
            raise SearchError(f'Could not find the area "{location}" on Google Maps.')
        low, high = places[0]["viewport"]["low"], places[0]["viewport"]["high"]
        return Box(low["latitude"], low["longitude"], high["latitude"], high["longitude"])

    def _results(self, body, max_results):
        """Yield the raw places of one search, following page tokens."""
        body = {**body, "pageSize": min(PAGE_SIZE, max_results)}
        fetched = 0
        while fetched < max_results:
            data = self._post(body, FIELD_MASK)
            for place in data.get("places", [])[: max_results - fetched]:
                fetched += 1
                yield place
            if "nextPageToken" not in data:
                return
            body["pageToken"] = data["nextPageToken"]

    def _post(self, body, field_mask):
        if self.stop is not None and self.stop.is_set():
            raise SearchError(STOPPED)
        if self.language:
            body = {**body, "languageCode": self.language}
        try:
            resp = self.session.post(
                SEARCH_URL, json=body, headers={"X-Goog-FieldMask": field_mask}, timeout=30
            )
        except requests.RequestException as e:
            raise SearchError(f"Could not reach the Google Places API: {e}") from e
        self.requests_made += 1
        if not resp.ok:
            try:
                message = resp.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                message = resp.text[:300]
            raise SearchError(f"Google Places API error (HTTP {resp.status_code}): {message}")
        return resp.json()


def _rectangle(box):
    return {
        "low": {"latitude": box.south, "longitude": box.west},
        "high": {"latitude": box.north, "longitude": box.east},
    }


def _to_business(place, query):
    location = place.get("location", {})
    status = place.get("businessStatus", "")
    return Business(
        place_id=place["id"],
        name=place.get("displayName", {}).get("text", ""),
        queries=[query],
        category=place.get("primaryTypeDisplayName", {}).get("text", ""),
        address=place.get("formattedAddress", ""),
        phone=place.get("nationalPhoneNumber", ""),
        intl_phone=place.get("internationalPhoneNumber", ""),
        website=place.get("websiteUri", ""),
        rating=place.get("rating"),
        reviews=place.get("userRatingCount"),
        status=BUSINESS_STATUS.get(status, status),
        maps_url=place.get("googleMapsUri", ""),
        lat=location.get("latitude"),
        lng=location.get("longitude"),
        types=place.get("types", []),
    )
