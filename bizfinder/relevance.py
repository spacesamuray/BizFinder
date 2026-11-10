"""Tell which search results really are the kind of business that was searched for.

Map searches pad thin areas with loosely related places: "flower shop" also
returns malls, furniture stores and supermarkets. So results are checked by
their place types and their names.
"""

import re
from collections import Counter

# Words too common to identify a business by name ("flower shop" -> look for "flower").
GENERIC_WORDS = {
    "shop", "store", "clinic", "center", "centre", "salon", "studio", "service", "company",
    "office", "place", "and", "the", "for",
    "მაღაზია", "კლინიკა", "სალონი", "ცენტრი", "სტუდია",  # Georgian
    "магазин", "клиника", "салон", "центр", "студия",  # Russian
}

# Google place types too broad to say what a business is.
VAGUE_TYPES = {
    "point_of_interest", "establishment", "store", "market", "service", "food", "food_store", "health",
}

# A place type shared by at least this share of a search's results is what the search is about.
# Kept low because a search often has several (dentist and dental_clinic); the unrelated places
# Google pads results with are spread over many types, each well under this.
MAIN_TYPE_SHARE = 0.10


def normalize(text):
    """Lowercase words without plural s, so "Flower Shops" equals "flower shop"."""
    words = re.findall(r"\w+", text.lower())
    return " ".join(w[:-1] if w.endswith("s") and len(w) > 3 else w for w in words)


def keywords(query):
    """The distinctive words of a query, to look for in business names."""
    return [w for w in normalize(query).split() if len(w) >= 3 and w not in GENERIC_WORDS]


def name_matches(name, words):
    """True if a word in `name` starts like any of `words`: "dentist" matches "Dental" and
    "Shako Dent" (but not "Residential"), "ყვავილების" matches "ყვავილები"."""
    name = name.lower()
    return any(re.search(r"(?<!\w)" + re.escape(w[: max(4, len(w) // 2)]), name) for w in words)


def mark_relevance(businesses, query):
    """Mark which of one query's results match it: those with one of the place
    types most results share (e.g. "florist"), or with a query word in their name."""
    counts = Counter(t for b in businesses for t in set(b.types) if t not in VAGUE_TYPES)
    main_types = {t for t, n in counts.items() if n >= MAIN_TYPE_SHARE * len(businesses)}
    if not main_types:  # no clear picture of what a match looks like; names alone are too strict
        return
    words = keywords(query)
    for b in businesses:
        # A place that matched an earlier query stays a match.
        b.relevant = bool(b.relevant) or bool(main_types & set(b.types)) or name_matches(b.name, words)
