"""Read saved spreadsheets back, for the app and `bizfinder list`.

The spreadsheets in output/ are the only record of past searches: the app shows
whatever is there, including files made before the app existed.
"""

import logging
import re
import shutil
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

from .run import OUTPUT

log = logging.getLogger(__name__)

GENERATED = re.compile(r"Generated (\d{4}-\d\d-\d\d \d\d:\d\d)(?: from ([^.]+))?")

_cache = {}  # path -> (modified time, data), so the list doesn't re-read every file


def saved():
    """A summary of every saved search in output/, newest first."""
    items = []
    for path in OUTPUT.glob("*.xlsx"):
        if path.name.startswith(("~$", ".")):  # Excel's lock files, hidden files
            continue
        try:
            data = read(path.name)
        except Exception:  # a broken or unrelated spreadsheet must not hide the others
            log.debug("Skipping %s", path, exc_info=True)
            continue
        items.append({key: data[key] for key in ("file", "title", "generated", "source", "found", "others")})
    return sorted(items, key=lambda item: item["generated"], reverse=True)


def read(name):
    """Everything in one saved spreadsheet: its title, date, source and both sheets of businesses."""
    path = find(name)
    modified = path.stat().st_mtime
    if path in _cache and _cache[path][0] == modified:
        return _cache[path][1]

    wb = load_workbook(path)  # not read-only: hyperlinks are only loaded in normal mode
    if "Businesses" not in wb.sheetnames:
        raise ValueError(f"{name} has no Businesses sheet")
    summary = wb["Summary"] if "Summary" in wb.sheetnames else None
    title = str(summary["A1"].value or "") if summary else ""
    match = GENERATED.search(str(summary["A2"].value or "")) if summary else None

    businesses = _sheet(wb["Businesses"])
    others = _sheet(wb["Other results"]) if "Other results" in wb.sheetnames else {"columns": [], "rows": []}
    generated = match.group(1) if match else f"{datetime.fromtimestamp(modified):%Y-%m-%d %H:%M}"
    data = {
        "file": path.name,
        "title": title or path.stem,
        "generated": generated,
        "source": (match and match.group(2)) or _guess_source(businesses),
        "found": len(businesses["rows"]),
        "others": len(others["rows"]),
        "businesses": businesses,
        "otherResults": others,
    }
    _cache[path] = (modified, data)
    return data


def find(name):
    """The saved spreadsheet called `name`, only ever inside output/."""
    path = OUTPUT / Path(name).name
    if Path(name).name != name or path.suffix.lower() != ".xlsx" or not path.is_file():
        raise FileNotFoundError(name)
    return path


def trash(name):
    """Move a saved spreadsheet to the Trash (macOS), so it can still be recovered."""
    path = find(name)
    bin_ = Path.home() / ".Trash"
    if not bin_.is_dir():
        raise OSError("There is no Trash folder on this computer.")
    target = bin_ / path.name
    n = 2
    while target.exists():
        target = bin_ / f"{path.stem} {n}{path.suffix}"
        n += 1
    shutil.move(path, target)
    _cache.pop(path, None)


def _sheet(ws):
    """A sheet's headers and rows. Link cells give their link (the cell shows a shortened version)."""
    rows = ws.iter_rows()
    header = next(rows, ())
    columns = [str(cell.value or "") for cell in header]
    data = []
    for row in rows:
        values = []
        for cell in row[: len(columns)]:
            value = cell.value
            if cell.hyperlink is not None and cell.hyperlink.target:
                value = cell.hyperlink.target.removeprefix("mailto:")
            elif isinstance(value, datetime):
                value = value.isoformat(sep=" ")
            values.append(value)
        if any(v not in (None, "") for v in values):
            data.append(values)
    return {"columns": columns, "rows": data}


def _guess_source(sheet):
    """For spreadsheets made before the source was noted: only Google has ratings."""
    if "Rating" in sheet["columns"]:
        i = sheet["columns"].index("Rating")
        if any(row[i] not in (None, "") for row in sheet["rows"] if i < len(row)):
            return "Google Maps"
    return "TomTom"
