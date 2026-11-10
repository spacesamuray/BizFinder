"""Search a big area box by box, for map APIs that cap how many results one search returns."""

import logging
from collections import deque
from typing import NamedTuple

log = logging.getLogger(__name__)


class Box(NamedTuple):
    south: float
    west: float
    north: float
    east: float

    def quadrants(self):
        mid_lat = (self.south + self.north) / 2
        mid_lng = (self.west + self.east) / 2
        return [
            Box(s, w, n, e)
            for s, n in ((self.south, mid_lat), (mid_lat, self.north))
            for w, e in ((self.west, mid_lng), (mid_lng, self.east))
        ]


def search_tiles(area, depth, cap, search_box):
    """Yield the unique results of searching `area`, box by box.

    `search_box(box)` yields the raw results (dicts with an "id") for one box.
    A box that comes back full (`cap` results, the API's maximum) probably
    holds more, so it is split into four smaller boxes, up to `depth` times.
    """
    seen = set()
    boxes = deque([(area, 0)])
    searched = 0
    while boxes:
        box, level = boxes.popleft()
        returned = 0
        for result in search_box(box):
            returned += 1
            if result["id"] not in seen:
                seen.add(result["id"])
                yield result
        searched += 1
        log.info("  area %d searched, %d found so far", searched, len(seen))
        if returned >= cap and level < depth:
            boxes.extend((quad, level + 1) for quad in box.quadrants())
