"""Write businesses to an Excel workbook (or CSV), ready for filtering and analysis."""

import csv
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from itertools import zip_longest
from statistics import mean, median
from typing import NamedTuple
from urllib.parse import unquote

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.marker import DataPoint
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.drawing.line import LineProperties
from openpyxl.formatting.rule import DataBarRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .enrich import BROKEN_STATUSES, SOCIAL_SITES
from .models import Business

# One blue ramp for headers, bars and highlights; gray for everything de-emphasized.
DARK_BLUE = "184F95"
ACCENT_BLUE = "2A78D6"
LIGHT_BLUE = "86B6EF"
MUTED_GRAY = "C9C7C0"
SECONDARY_INK = "52514E"

FONT = Font(name="Arial", size=10)
LINK_FONT = Font(name="Arial", size=10, color="0563C1", underline="single")
HEADER_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor=DARK_BLUE)
BAND_FILL = PatternFill("solid", fgColor="F5F7FA")
TILE_FILL = PatternFill("solid", fgColor="EEF3FA")
TILE_SIDE = Side(style="thin", color="D9DEE7")
CENTER = Alignment(horizontal="center")

# Excel's familiar good / neutral / bad cell styles, for status columns (always next to a text label).
GOOD = (PatternFill("solid", fgColor="C6EFCE"), Font(color="006100"))
NEUTRAL = (PatternFill("solid", fgColor="FFEB9C"), Font(color="9C5700"))
BAD = (PatternFill("solid", fgColor="FFC7CE"), Font(color="9C0006"))


class Column(NamedTuple):
    header: str
    value: Callable[[Business], object]
    width: int
    link: str | None = None  # prefix that turns the value into a clickable link
    number_format: str | None = None
    centered: bool = False


COLUMNS = [
    Column("Name", lambda b: b.name, 34),
    Column("Category", lambda b: b.category, 20),
    Column("Search", lambda b: ", ".join(b.queries), 18),
    Column("Phone", lambda b: b.phone, 16),
    Column("Intl. phone", lambda b: b.intl_phone, 18),
    Column("Has website", lambda b: b.has_website, 16),
    Column("Website", lambda b: b.website, 32, link=""),
    Column("Website status", lambda b: b.website_status, 22),
    Column("Email", lambda b: b.emails[0] if b.emails else "", 28, link="mailto:"),
    Column("Other emails", lambda b: ", ".join(b.emails[1:]), 28),
    *[Column(name, lambda b, name=name: b.socials.get(name, ""), 30, link="") for name in SOCIAL_SITES],
    Column("Rating", lambda b: b.rating, 8, number_format="0.0", centered=True),
    Column("Reviews", lambda b: b.reviews, 10, number_format="#,##0", centered=True),
    Column("Business status", lambda b: b.status, 18),
    Column("Address", lambda b: b.address, 45),
    Column("Google Maps", lambda b: b.maps_url, 30, link=""),
    Column("Latitude", lambda b: b.lat, 11),
    Column("Longitude", lambda b: b.lng, 11),
    Column("Place ID", lambda b: b.place_id, 30),
    Column("Google types", lambda b: ", ".join(b.types), 30),
]
LETTER = {c.header: get_column_letter(i) for i, c in enumerate(COLUMNS, 1)}


def save(businesses, path, title, source=None):
    """Save matching businesses plus a summary with percentages. Results that don't look
    like what was searched for (relevant=False) are kept apart. For Excel those are extra
    sheets; for CSV, extra files next to `path`. `source` (e.g. "Google Maps") is noted in
    the summary. Returns notes on the extra parts, for the log."""
    matches = [b for b in businesses if b.relevant is not False]
    others = [b for b in businesses if b.relevant is False]
    if path.suffix.lower() == ".csv":
        _save_csv(matches, path)
        summary_path = path.with_name(f"{path.stem}_summary.csv")
        _save_summary_csv(matches, summary_path, title, len(others), source)
        notes = [f"summary with percentages in {summary_path.name}"]
        others_location = path.with_name(f"{path.stem}_other-results.csv")
        if others:
            _save_csv(others, others_location)
        others_location = others_location.name
    else:
        _save_xlsx(matches, others, path, title, source)
        notes = ['summary with percentages and charts on the "Summary" sheet']
        others_location = 'the "Other results" sheet'
    if others:
        examples = ", ".join(b.name for b in others[:3])
        notes.append(f"{len(others)} results that don't look like a match (e.g. {examples}) in {others_location}")
    return notes


def _save_csv(businesses, path):
    # utf-8-sig so Excel shows non-Latin names (e.g. Georgian) correctly.
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([c.header for c in COLUMNS])
        for b in businesses:
            writer.writerow([c.value(b) for c in COLUMNS])


def _save_xlsx(matches, others, path, title, source):
    wb = Workbook()
    wb.active.title = "Summary"
    _write_summary(wb.active, matches, title, len(others), source)
    _write_businesses(wb.create_sheet("Businesses"), matches)
    if others:
        _write_businesses(wb.create_sheet("Other results"), others)
    wb.save(path)


def _write_businesses(ws, businesses):
    for col, column in enumerate(COLUMNS, 1):
        cell = ws.cell(1, col, column.header)
        cell.font, cell.fill = HEADER_FONT, HEADER_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(col)].width = column.width
    ws.row_dimensions[1].height = 30

    for row, business in enumerate(businesses, 2):
        for col, column in enumerate(COLUMNS, 1):
            value = column.value(business)
            if isinstance(value, str):
                value = ILLEGAL_CHARACTERS_RE.sub("", value)
            cell = ws.cell(row, col, value)
            cell.font = FONT
            if isinstance(value, str) and value.startswith("="):
                cell.data_type = "s"  # a name like "=Flowers" must not become a formula
            if value and column.link is not None:
                cell.hyperlink = column.link + value
                cell.font = LINK_FONT
                # Show "facebook.com/დენტალი" rather than "facebook.com/%E1%83%93..."; the link is unchanged.
                cell.value = ILLEGAL_CHARACTERS_RE.sub("", unquote(value))
            if column.number_format:
                cell.number_format = column.number_format
            if column.centered:
                cell.alignment = CENTER
            # Also set directly (not only as conditional formatting below), so the colours
            # show in previews and apps without conditional formatting. They move with the
            # cell when sorting, so they stay right.
            if style := _status_style(column.header, value):
                cell.fill, cell.font = style[0], Font(name="Arial", size=10, color=style[1].color)

    ws.freeze_panes = "B2"  # keep the header row and names visible while scrolling
    ws.auto_filter.ref = ws.dimensions
    if businesses:
        _highlight(ws, len(businesses) + 1)


def _status_style(header, value):
    """GOOD / NEUTRAL / BAD for a value in one of the website columns, else None."""
    if not value:
        return None
    if header == "Has website":
        return GOOD if value == "Yes" else BAD if value == "No" else NEUTRAL
    if header == "Website status":
        return GOOD if value == "OK" else BAD if value.startswith(BROKEN_STATUSES) else NEUTRAL
    return None


def _highlight(ws, last_row):
    """Colour the website columns by status, add bars to Reviews, and band the rows.
    Done with conditional formatting so it stays right after editing, sorting or filtering."""

    def add(header, formula, style):
        letter = LETTER[header]
        fill, font = style
        rule = FormulaRule(formula=[formula.replace("{c}", f"{letter}2")], fill=fill, font=font)
        ws.conditional_formatting.add(f"{letter}2:{letter}{last_row}", rule)

    add("Has website", '{c}="Yes"', GOOD)
    add("Has website", 'LEFT({c},4)="Only"', NEUTRAL)
    add("Has website", '{c}="No"', BAD)
    add("Website status", '{c}="OK"', GOOD)
    broken = ",".join(f'LEFT({{c}},{len(status)})="{status}"' for status in BROKEN_STATUSES)
    add("Website status", f"OR({broken})", BAD)
    add("Website status", 'LEN({c})>0', NEUTRAL)  # anything else: SSL problem, blocked, ...

    reviews = LETTER["Reviews"]
    ws.conditional_formatting.add(
        f"{reviews}2:{reviews}{last_row}",
        # Up to the 90th percentile, so a few hugely reviewed places don't flatten every other bar.
        DataBarRule(start_type="num", start_value=0, end_type="percentile", end_value=90, color=LIGHT_BLUE),
    )
    # Added last, so the status colours above take priority over the banding.
    ws.conditional_formatting.add(
        f"A2:{get_column_letter(len(COLUMNS))}{last_row}",
        FormulaRule(formula=["MOD(ROW(),2)=0"], fill=BAND_FILL),
    )


def _write_summary(ws, businesses, title, other_count, source):
    ws.sheet_view.showGridLines = False
    for letter, width in zip("ABCDEF", (34, 15, 15, 15, 15, 15)):
        ws.column_dimensions[letter].width = width

    ws["A1"] = title
    ws["A1"].font = Font(name="Arial", size=16, bold=True)
    notes = _summary_notes(other_count, 'the "Other results" sheet', source)
    notes[0] += ' A snapshot of the "Businesses" sheet: editing it won\'t change these numbers.'
    for row, note in enumerate(notes, 2):
        ws.cell(row, 1, note).font = Font(name="Arial", size=9, italic=True, color=SECONDARY_INK)

    _write_tiles(ws, 5, _headline_figures(businesses))

    row = 9
    tables = {}
    for headers, rows, formats in _summary_tables(businesses):
        tables[headers[0]] = (row + 1, [values[0] for values in rows])
        row = _table(ws, row, headers, rows, formats)

    anchor_row = 5
    for table, chart_title in [
        ("Website", "Website presence"),
        ("Contact details", "Contact details available"),
        ("Social media", "Social media used"),
    ]:
        if table not in tables or not tables[table][1]:
            continue
        first_row, labels = tables[table]
        # The story for website presence is how many have none, so only that bar is coloured.
        highlight = labels.index("No website") if "No website" in labels else None
        chart = _bar_chart(ws, chart_title, first_row, first_row + len(labels) - 1, highlight)
        ws.add_chart(chart, f"H{anchor_row}")
        anchor_row += 16


def _headline_figures(businesses):
    total = len(businesses)

    def share(test):
        return sum(1 for b in businesses if test(b)) / total if total else 0

    figures = [
        ("Businesses found", total, "#,##0"),
        ("Have their own website", share(lambda b: b.has_website == "Yes"), "0%"),
        ("No website at all", share(lambda b: b.has_website == "No"), "0%"),
    ]
    if any(b.website_status for b in businesses if b.has_website == "Yes"):
        figures.append(("Have an email", share(lambda b: b.emails), "0%"))
    if ratings := [b.rating for b in businesses if b.rating is not None]:
        figures.append(("Average Google rating", mean(ratings), "0.0"))
    return figures


def _write_tiles(ws, row, figures):
    """Headline numbers as tiles: a small label above a big value."""
    for col, (label, value, number_format) in enumerate(figures, 1):
        top = ws.cell(row, col, label)
        top.font = Font(name="Arial", size=9, color=SECONDARY_INK)
        top.alignment = Alignment(wrap_text=True, vertical="top")
        top.border = Border(top=TILE_SIDE, left=TILE_SIDE, right=TILE_SIDE)
        bottom = ws.cell(row + 1, col, value)
        bottom.font = Font(name="Arial", size=20, bold=True, color=DARK_BLUE)
        bottom.number_format = number_format
        bottom.alignment = Alignment(horizontal="left", vertical="center")
        bottom.border = Border(bottom=TILE_SIDE, left=TILE_SIDE, right=TILE_SIDE)
        top.fill = bottom.fill = TILE_FILL
    ws.row_dimensions[row].height = 26
    ws.row_dimensions[row + 1].height = 34


def _table(ws, row, headers, rows, formats=()):
    """Write a small table at `row` and return the row where the next one can start."""
    for col, text in enumerate(headers, 1):
        cell = ws.cell(row, col, text)
        cell.font, cell.fill = HEADER_FONT, HEADER_FILL
        cell.alignment = Alignment(horizontal="left" if col == 1 else "right")
    first = row + 1
    for i, values in enumerate(rows):
        row += 1
        for col in range(1, len(headers) + 1):
            cell = ws.cell(row, col, values[col - 1] if col <= len(values) else None)
            cell.font = FONT
            if i % 2:
                cell.fill = BAND_FILL
            if col <= len(formats) and formats[col - 1]:
                cell.number_format = formats[col - 1]
    # Bars in percentage columns, so shares can be compared at a glance.
    for col, number_format in enumerate(formats, 1):
        if number_format and number_format.endswith("%") and rows:
            letter = get_column_letter(col)
            ws.conditional_formatting.add(
                f"{letter}{first}:{letter}{row}",
                DataBarRule(start_type="num", start_value=0, end_type="num", end_value=1, color=LIGHT_BLUE),
            )
    return row + 2


def _bar_chart(ws, title, first_row, last_row, highlight=None):
    """Horizontal bars for a summary table's Share column (C), labelled with percentages.
    With `highlight`, that bar is blue and the rest gray; otherwise all are blue."""
    chart = BarChart()
    chart.type = "bar"
    chart.title = title
    chart.legend = None
    chart.gapWidth = 50
    chart.add_data(Reference(ws, min_col=3, min_row=first_row, max_row=last_row))
    chart.set_categories(Reference(ws, min_col=1, min_row=first_row, max_row=last_row))

    series = chart.series[0]
    base = ACCENT_BLUE if highlight is None else MUTED_GRAY
    series.graphicalProperties = GraphicalProperties(solidFill=base, ln=LineProperties(noFill=True))
    if highlight is not None:
        series.dPt.append(
            DataPoint(idx=highlight, spPr=GraphicalProperties(solidFill=ACCENT_BLUE, ln=LineProperties(noFill=True)))
        )
    series.dLbls = DataLabelList(showVal=True, dLblPos="outEnd", numFmt="0%")

    chart.x_axis.scaling.orientation = "maxMin"  # keep the table's order, first row on top
    chart.x_axis.delete = False
    chart.y_axis.delete = True  # the bar labels already show the values
    chart.y_axis.scaling.min = 0
    chart.y_axis.scaling.max = 1
    chart.y_axis.majorGridlines = None
    chart.width, chart.height = 14, 7
    return chart


def _save_summary_csv(businesses, path, title, other_count, source):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([title])
        for note in _summary_notes(other_count, path.name.replace("_summary", "_other-results"), source):
            writer.writerow([note])
        writer.writerow([])
        writer.writerow(["Businesses found", len(businesses)])
        for headers, rows, formats in _summary_tables(businesses):
            writer.writerow([])
            writer.writerow(headers)
            for values in rows:
                writer.writerow([_csv_value(v, fmt) for v, fmt in zip_longest(values, formats)])


def _csv_value(value, number_format):
    if value is None:
        return ""
    if number_format and number_format.endswith("%"):
        return f"{value:.1%}"
    if number_format == "0.0":
        return f"{value:.1f}"
    return value


def _summary_notes(other_count, others_location, source):
    # results.py reads the date and source back from this line, for the app.
    notes = [f"Generated {datetime.now():%Y-%m-%d %H:%M}{f' from {source}' if source else ''}."]
    if other_count:
        notes.append(f"Not counted here: {other_count} results that don't look like a match (see {others_location}).")
    return notes


def _summary_tables(businesses):
    """The summary's tables, each as (headers, rows, number format per column)."""
    total = len(businesses)
    crawled = any(b.website_status for b in businesses if b.has_website == "Yes")
    ratings = [b.rating for b in businesses if b.rating is not None]
    reviews = [b.reviews for b in businesses if b.reviews is not None]

    def count(test, group=businesses):
        return sum(1 for b in group if test(b))

    def share(n, of=total):
        return n / of if of else 0

    def with_share(items, of=total):
        return [(label, n, share(n, of)) for label, n in items]

    percent = (None, None, "0.0%")
    own = count(lambda b: b.has_website == "Yes")
    tables = [(
        ("Website", "Businesses", "Share"),
        with_share([
            ("Own website", own),
            ("Only a social media page", count(lambda b: b.has_website == "Only social page")),
            ("Only a Wolt/Glovo/... page", count(lambda b: b.has_website == "Only listing page")),
            ("No website", count(lambda b: b.has_website == "No")),
        ]),
        percent,
    )]

    if crawled and own:
        works = count(lambda b: b.website_status in ("OK", "SSL certificate problem"))
        broken = count(lambda b: b.website_status.startswith(BROKEN_STATUSES))
        tables.append((
            ("Own website status", "Websites", "Share"),
            with_share(
                [("Works", works), ("Broken or expired", broken), ("Couldn't check (blocked, slow...)", own - works - broken)],
                own,
            ),
            percent,
        ))

    reach = [("Phone number", count(lambda b: b.phone or b.intl_phone)), ("Own website", own)]
    if ratings:
        reach.append(("Google rating", len(ratings)))
    if crawled:
        reach += [("Email", count(lambda b: b.emails)), ("Social media", count(lambda b: b.socials))]
    tables.append((("Contact details", "Businesses", "Share"), with_share(sorted(reach, key=lambda r: -r[1])), percent))

    if crawled:
        platforms = [(p, count(lambda b, p=p: p in b.socials)) for p in SOCIAL_SITES]
        tables.append((("Social media", "Businesses", "Share"), with_share(sorted(platforms, key=lambda r: -r[1])), percent))

    if ratings:
        tables.append((
            ("Ratings", "Value"),
            [
                ("Average rating", mean(ratings)),
                ("Average number of reviews", mean(reviews) if reviews else None),
                ("Median number of reviews", median(reviews) if reviews else None),
            ],
            (None, "0.0"),
        ))

    queries = list(dict.fromkeys(q for b in businesses for q in b.queries))
    if len(queries) > 1:
        rows = []
        for query in queries:
            group = [b for b in businesses if query in b.queries]
            rows.append((
                query,
                len(group),
                share(count(lambda b: b.has_website == "Yes", group), len(group)),
                share(count(lambda b: b.emails, group), len(group)),
                share(count(lambda b: b.socials, group), len(group)),
                mean(r) if (r := [b.rating for b in group if b.rating is not None]) else None,
            ))
        tables.append((
            ("By search", "Businesses", "Own website", "Email", "Social media", "Avg rating"),
            rows,
            (None, None, "0.0%", "0.0%", "0.0%", "0.0"),
        ))

    categories = Counter(b.category or "(no category)" for b in businesses).most_common(25)
    tables.append((("Google category", "Businesses", "Share"), with_share(categories), percent))
    return tables
