"""Count map API requests per day, so you can see how much of a free allowance is left.

Kept in output/.usage.json. A day ends when the provider resets its daily quota.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

FILE = Path(__file__).resolve().parent.parent / "output" / ".usage.json"

# Where each provider's day starts and ends: Google resets quotas at midnight Pacific time.
DAY_ZONES = {"google": ZoneInfo("America/Los_Angeles"), "tomtom": ZoneInfo("UTC")}
DAILY_FREE = {"tomtom": 2500}  # Google's free allowance is monthly, or a daily cap that depends on the key
KEEP_DAYS = 60


def add(source, requests):
    """Record `requests` made to `source` today."""
    if not requests:
        return
    data = _load()
    day = _today(source)
    counts = data.setdefault(source, {})
    counts[day] = counts.get(day, 0) + requests
    # Drop old days so the file stays small.
    for old in sorted(counts)[:-KEEP_DAYS]:
        del counts[old]
    try:
        FILE.parent.mkdir(parents=True, exist_ok=True)
        FILE.write_text(json.dumps(data, indent=1))
    except OSError as e:
        log.debug("Could not save request counts: %s", e)


def today(source):
    """{"used": requests today, "free": daily free allowance or None, "resets": ISO time}."""
    zone = DAY_ZONES[source]
    now = datetime.now(zone)
    resets = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        "used": _load().get(source, {}).get(_today(source), 0),
        "free": DAILY_FREE.get(source),
        "resets": resets.isoformat(),
    }


def _today(source):
    return datetime.now(DAY_ZONES[source]).strftime("%Y-%m-%d")


def _load():
    try:
        return json.loads(FILE.read_text())
    except (OSError, ValueError):
        return {}
