"""The `bizfinder` command: open the app, run a search in the terminal, or list saved searches."""

import argparse
import logging
import sys
from pathlib import Path

from . import results, tomtom
from .run import SOURCES, RunError, Search, has_key, run

EXAMPLES = """\
examples:
  bizfinder                                         open the app in your browser
  bizfinder find "dentist" --in "Tbilisi, Georgia"  search in the terminal
  bizfinder find                                    asks what and where to search
  bizfinder list                                    your saved searches
"""

FIND_EXAMPLES = """\
examples:
  bizfinder find "dental clinic" --in "Tbilisi, Georgia"
  bizfinder find "flower shop" "florist" --in "Batumi"
  bizfinder find "dentist" --in "Tbilisi" --source tomtom
  bizfinder find "dentist" --in "Tbilisi" --deep --out dentists.xlsx
"""


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="bizfinder",
        description="Find businesses on a map, check their websites for emails and social media, "
        "and save it all to a spreadsheet.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")

    app = commands.add_parser("app", help="open the app in your browser (the default)")
    app.add_argument("--port", type=int, default=8650, help="port for the app (default: 8650)")
    app.add_argument("--no-open", action="store_true", help="don't open the browser")

    find = commands.add_parser(
        "find",
        help="search in the terminal",
        description="Find businesses and export their phone, website, emails and social media to a spreadsheet.",
        epilog=FIND_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _find_arguments(find)

    commands.add_parser("list", help="list your saved searches")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logging.getLogger("bizfinder").setLevel(logging.INFO)

    if args.command == "find":
        _find(args)
    elif args.command == "list":
        _list()
    else:
        from .server import serve

        serve(port=getattr(args, "port", 8650), open_browser=not getattr(args, "no_open", False))


def _find_arguments(parser):
    parser.add_argument(
        "queries", nargs="*", metavar="QUERY", help='what to search for, e.g. "dental clinic" (several allowed)'
    )
    parser.add_argument("--in", dest="location", metavar="PLACE", help='city or area, e.g. "Tbilisi, Georgia"')
    parser.add_argument(
        "--source",
        choices=SOURCES,
        help="google (best data, paid above a free monthly allowance) or tomtom (free, fewer websites). "
        "Default: whichever has a key in .env, Google first",
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Google only: get past its 60-results-per-search cap by searching the area in smaller tiles "
        "(finds many more businesses in big cities, uses more API requests). TomTom always does this",
    )
    parser.add_argument(
        "--depth",
        type=int,
        choices=range(1, 6),
        help="how many times a crowded area may be split into 4 smaller ones "
        f"(default: 2 for Google --deep, {tomtom.DEFAULT_DEPTH} for TomTom)",
    )
    parser.add_argument("--limit", type=int, help="max businesses per query (default: all the map service returns)")
    parser.add_argument(
        "--out", type=Path, help="output file, .xlsx or .csv (default: output/<query>_<place>_<time>.xlsx)"
    )
    parser.add_argument("--language", help='language for names and addresses, e.g. "en" or "ka"')
    parser.add_argument(
        "--no-crawl", action="store_true", help="don't visit websites (no emails or social links, but much faster)"
    )
    parser.add_argument("--workers", type=int, default=10, help="websites to check in parallel (default: 10)")
    parser.add_argument("--api-key", help="API key for the chosen source (default: the key in .env)")


def _find(args):
    queries = args.queries
    location = args.location
    source = args.source
    if not queries or not location:
        queries, location, source = _ask(queries, location, source)
    search = Search(
        queries=queries,
        location=location,
        source=source,
        deep=args.deep,
        depth=args.depth,
        limit=args.limit,
        language=args.language,
        crawl=not args.no_crawl,
        workers=args.workers,
        out=args.out,
        api_key=args.api_key,
    )
    try:
        run(search)
    except RunError as e:
        sys.exit(str(e))


def _ask(queries, location, source):
    """Ask for whatever the command line left out."""
    if not sys.stdin.isatty():
        sys.exit('Say what and where, e.g.: bizfinder find "dentist" --in "Tbilisi, Georgia"')
    try:
        while not queries:
            answer = input("What are you looking for? (separate several with commas) ")
            queries = [q.strip() for q in answer.split(",") if q.strip()]
        while not location:
            location = input("Where? (e.g. Tbilisi, Georgia) ").strip()
        keys = [s for s in SOURCES if has_key(s)]
        if not source and len(keys) > 1:
            names = " or ".join(f"{s} ({SOURCES[s][0]})" for s in keys)
            answer = input(f"Search with {names}? [{keys[0]}] ").strip().lower()
            source = answer if answer in keys else keys[0]
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(1)
    return queries, location, source


def _list():
    saved = results.saved()
    if not saved:
        print(f"No saved searches yet. They are saved to {results.OUTPUT}")
        return
    print(f"{'Date':<17}  {'Found':>5}  {'Source':<11}  Search")
    for item in saved:
        print(f"{item['generated']:<17}  {item['found']:>5}  {item['source']:<11}  {item['title']}")
    print(f"\nFiles are in {results.OUTPUT}. Open them all with: bizfinder")
