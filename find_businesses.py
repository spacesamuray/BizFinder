#!/usr/bin/env python3
"""Find businesses and export their contact details to a spreadsheet.

Kept so old commands still work. The same as `bizfinder find ...`; see README.md.
"""

import sys

from bizfinder.cli import main

if __name__ == "__main__":
    main(["find", *sys.argv[1:]])
