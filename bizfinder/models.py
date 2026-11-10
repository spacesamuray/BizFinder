from dataclasses import dataclass, field


STOPPED = "Search stopped early."


class SearchError(Exception):
    """A map provider (Google or TomTom) refused or failed a request, or the search was stopped."""


@dataclass
class Business:
    """A place found on Google Maps, plus what we learned from its website."""

    place_id: str
    name: str
    queries: list[str]
    category: str = ""
    address: str = ""
    phone: str = ""
    intl_phone: str = ""
    website: str = ""
    rating: float | None = None
    reviews: int | None = None
    status: str = ""
    maps_url: str = ""
    lat: float | None = None
    lng: float | None = None
    types: list[str] = field(default_factory=list)  # Google place types, e.g. ["florist", "store"]
    relevant: bool | None = None  # set by relevance.py; False goes to the "Other results" sheet

    # Filled in by enrich.py
    has_website: str = ""  # "Yes", "Only social page", "Only listing page" (e.g. Wolt) or "No"
    website_status: str = ""
    emails: list[str] = field(default_factory=list)
    socials: dict[str, str] = field(default_factory=dict)
