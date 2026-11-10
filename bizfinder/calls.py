"""Your notes on calling businesses: whether you called, what they said, and what to do
better next time.

Kept in output/calls.json, keyed by the business's place ID, so a note shows up in every
search that finds the same business. Not written into the spreadsheets: re-saving them
would lose their charts.
"""

import json
import os
import tempfile
import threading
from datetime import datetime

from .run import OUTPUT

FILE = OUTPUT / "calls.json"
STATUSES = ("No answer", "Call back", "Interested", "Somewhat interested", "Client", "Not interested", "Wrong number")
TEXT_FIELDS = ("response", "improve")
MAX_TEXT = 5000
SAME_CALL_MINUTES = 10  # a new result within this time corrects the last one instead of logging another call

_lock = threading.Lock()


def load():
    """All notes, {key: note}. Raises ValueError if the file is damaged, so it's never overwritten."""
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except ValueError as e:
        raise ValueError(f"{FILE} is damaged ({e}). Fix it or move it away to start a new one.") from None
    if not isinstance(data, dict):
        raise ValueError(f"{FILE} is damaged. Fix it or move it away to start a new one.")
    return data


def update(key, changes):
    """Change one business's notes and return them, or None once they're empty.

    Only the fields present in `changes` change: "status" (one of STATUSES, or "" for not
    called), "response" and "improve". "name", "phone" and "search" are kept alongside, so
    calls.json makes sense on its own.
    """
    key = str(key or "")[:300]
    if not key:
        raise ValueError("Which business? The note has no key.")
    with _lock:
        calls = load()
        call = calls.get(key, {})
        now = datetime.now().isoformat(timespec="minutes")

        if "status" in changes:
            status = changes["status"] or ""
            if status and status not in STATUSES:
                raise ValueError(f"Unknown call result: {status}")
            if not status:
                for field in ("status", "calledAt", "history"):
                    call.pop(field, None)
            elif status != call.get("status"):
                history = call.setdefault("history", [])
                if history and _minutes_since(history[-1]["at"]) < SAME_CALL_MINUTES:
                    history[-1] = {"at": now, "status": status}
                else:
                    history.append({"at": now, "status": status})
                call["status"] = status
                call["calledAt"] = now

        for field in TEXT_FIELDS:
            if field in changes:
                text = str(changes[field] or "").strip()[:MAX_TEXT]
                if text:
                    call[field] = text
                else:
                    call.pop(field, None)

        if not any(call.get(field) for field in ("status", *TEXT_FIELDS)):
            calls.pop(key, None)
            call = None
        else:
            for field in ("name", "phone", "search"):
                if changes.get(field):
                    call[field] = str(changes[field])[:300]
            call["updatedAt"] = now
            calls[key] = call
        _write(calls)
        return call


def _minutes_since(stamp):
    try:
        return (datetime.now() - datetime.fromisoformat(stamp)).total_seconds() / 60
    except (TypeError, ValueError):
        return float("inf")


def _write(calls):
    """Write the whole file at once, so a crash mid-write can't leave it half written."""
    FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=FILE.parent, prefix=".calls-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(calls, f, ensure_ascii=False, indent=1)
        os.replace(tmp, FILE)
    except BaseException:
        os.unlink(tmp)
        raise
