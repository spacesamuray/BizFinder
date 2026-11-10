<picture>
  <source media="(prefers-color-scheme: dark)" srcset="brand/bizfinder-logo-dark.svg">
  <img src="brand/bizfinder-logo.svg" alt="bizfinder" width="180">
</picture>

# Business finder

Searches a map service for any kind of business (dentists, flower shops, ...) in a
city, then visits each business's website to find email addresses and social media
pages. Everything goes into an Excel spreadsheet with a summary sheet for analysis.

Use it in your browser (type `bizfinder`) or in the terminal (`bizfinder find ...`).

Two map services are supported:

| | **TomTom** | **Google Maps** |
|---|---|---|
| Cost | Free: 2,500 requests a day, no payment card | 1,000 requests a month free, then paid; needs a payment card |
| Phone numbers | Most businesses | Most businesses |
| Websites | Few (about 1 in 10 dentists in Tbilisi) | Many more |
| Ratings and reviews | No | Yes |
| Example: Tbilisi | 488 dentists, 15 flower shops | not tested yet |

The tool uses whichever key you put in `.env`. If both are there, Google is used unless
you add `--source tomtom`.

## Setup (once)

**1. Get a key (TomTom, Google, or both)**

*TomTom (free):*
1. Sign up at <https://developer.tomtom.com> and open <https://my.tomtom.com/keys>.
2. Click **Create key** and tick **Search API** and **Geocoding API**.
3. Copy the key.

*Google Maps:*
1. Open <https://console.cloud.google.com/>, create a project, and turn on billing.
2. Enable **Places API (New)**, not the old "Places API":
   <https://console.cloud.google.com/apis/library/places.googleapis.com>
3. **APIs & Services → Credentials → Create credentials → API key**.

**2. Install**

```bash
git clone git@github.com:spacesamuray/BizFinder.git
cd BizFinder
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then open .env and paste your key(s)
```

**3. Make the `bizfinder` command** (so it works from any folder, no `source` needed).
In the project folder:

```bash
mkdir -p ~/.local/bin
ln -s "$PWD/bin/bizfinder" ~/.local/bin/bizfinder
```

`~/.local/bin` must be on your PATH. If `bizfinder` isn't found, add
`export PATH="$HOME/.local/bin:$PATH"` to `~/.zshrc` and open a new terminal.

## Usage

### In the browser (easiest)

```bash
bizfinder
```

This opens the app at <http://127.0.0.1:8650>. Keep the terminal window open while you use
it; Ctrl+C stops it. Typing `bizfinder` again while it runs just opens the page again.
When the app's code is updated, it restarts itself (after any running search finishes) and
the page offers a **Reload** button. Call notes are kept in the browser until they're saved,
so a note typed while the app restarts isn't lost.

- **New search:** type what you're looking for (press Enter after each; add the Georgian
  words too), where, and choose Google Maps or TomTom. You see the progress live, and
  **Stop and save** keeps what was found so far.
- **Saved searches** on the left: every spreadsheet in `output/`, including older ones.
- **Table:** the spreadsheet, with all rows. Click a column name to sort, drag its edge to
  resize, **Filters** for a filter box per column, **Columns** to show or hide columns.
  The buttons above it show only businesses that **need a website** (no website, only a
  social or listing page, or a broken site), have no website, have an email, and so on.
- **Click a row** for everything about that business, with call, email, website and
  Google Maps buttons and copy buttons. The arrow keys go to the next or previous one.
- **Your call** (in a business's details): mark how the call went (No answer, Call back,
  Interested, Somewhat interested, Client, Not interested, Wrong number), what they said,
  and how you could do better next time. **Somewhat interested** means: send them a demo
  on WhatsApp. It saves by itself as you type. Changing the result within 10 minutes
  corrects it; a later one is logged as another call, so you see every call with its date.
  The table shows these in **Call status**, **Their response** and **How to improve**, and
  the **All calls** menu shows, for example, only businesses you haven't called yet.
  A quick way to work through a list: choose **Needs a website** and **Not called yet**,
  open the first business, and after each call press ↓ (or the arrow at the top) for the next.
- **Map:** every business as a dot, coloured by its web presence. Click a dot for details.
- **Summary:** the same numbers as the spreadsheet's Summary sheet.
- **Export:** copy the emails or phone numbers of the businesses shown, or download them
  as CSV. **Download .xlsx** gives you the whole spreadsheet, e.g. to open in Google Sheets.
- The bottom left shows how many map requests you made today.

Your call notes are kept in `output/calls.json`, one per business, so they show up again in
any later search that finds the same business (Google and TomTom number businesses
differently, so a note made on a TomTom result doesn't show on a Google one). Keep a copy of
that file: it's the only place they're stored. They are in the CSV export but not in the
.xlsx download, because re-saving the spreadsheet would lose its charts.

The app only works on this computer: other computers and websites can't reach it.

Its look follows the logo: ink, cream and green, with headings and numbers in Sora. The
logo files (app icon, favicon, versions for light and dark backgrounds, a social preview)
are in `brand/`, with the exact colours in `brand/README.txt`. The app uses the favicon
from `bizfinder/static/brand/` and the Sora font from `bizfinder/static/vendor/sora/`
(free to use, see its `OFL.txt`), so it needs no internet for them.

### In the terminal

```bash
bizfinder find "dentist" --in "Tbilisi, Georgia"
bizfinder find "flower shop" "florist" --in "Batumi"       # several searches, one sheet
bizfinder find "dentist" --in "Tbilisi" --source tomtom    # choose the map service
bizfinder find "cafe" --in "Kutaisi" --out cafes.csv       # CSV instead of Excel
bizfinder find                                             # asks what and where
bizfinder list                                             # your saved searches
```

The spreadsheet is saved to `output/` unless you pass `--out`. Run `bizfinder find --help`
for all options. The old `python find_businesses.py ...` still works the same way.

| Option | What it does |
|---|---|
| `--source tomtom` / `google` | Choose the map service. |
| `--deep` | Google only. Google returns **at most 60 businesses per search**. `--deep` splits the city into smaller areas and searches each one, so a big city can give hundreds of results. (TomTom always does this, because its requests are free.) |
| `--limit N` | Stop after N businesses per search. |
| `--language en` | Language for names and addresses. For TomTom use a code like `en-GB`. |
| `--no-crawl` | Skip visiting websites: much faster, but no emails or social links. |

**Tips**
- **TomTom:** use simple category words like `"dentist"`, `"florist"`, `"pharmacy"` or
  `"restaurant"`. If TomTom has no category with your words, the tool warns you and
  only finds businesses whose name contains them.
- **Google:** search in the local language as well, e.g. `"სტომატოლოგია"` next to
  `"dental clinic"`. Businesses found by both searches are listed once.

## What's in the spreadsheet

**Businesses** sheet: one row per business, with filters on every column.

| Column | Source |
|---|---|
| Name, Category, Phone, Address, Website | The map service |
| Rating, Reviews, Business status | Google only |
| Google Maps | A link to the business on Google Maps. With TomTom it opens a Google Maps search for the business, handy for checking its website and reviews. |
| Has website | `Yes`, `Only social page` (their "website" is a Facebook/Instagram page), `Only listing page` (their "website" is a Wolt, Glovo, Bolt Food, ... page) or `No` |
| Website status | `OK`, `Domain doesn't exist` (expired), `Unreachable`, `Not found`, `SSL certificate problem`, `Blocked automated check`, ... |
| Email, Other emails | Found on their website (homepage, then contact page). Emails on their own domain come first. |
| Facebook, Instagram, LinkedIn, X, TikTok, YouTube, WhatsApp, Telegram | Links found on their website |

**Summary** sheet (the first tab): headline numbers, tables with counts and percentages
(website presence, website health, contact details, social media, ratings, by search, by
category) and bar charts. The numbers are a snapshot taken when the file was made. Charts
show in Excel, Numbers and Google Sheets, but not in the Mac's spacebar preview.

The **Businesses** sheet colours the website columns: green = has a working website,
yellow = only a social/listing page (or the site couldn't be checked), red = no website or broken.

With `--out something.csv` you get the same as separate files: `something.csv` (the
businesses), `something_summary.csv` (the summary with percentages) and, if any,
`something_other-results.csv`.

**Other results** sheet (Google only): Google pads quiet areas with loosely related
places ("flower shop" also returns malls and furniture stores). A result counts as a
match if it has the place type most results share (e.g. `florist`) or a search word
in its name; everything else goes here instead of being deleted, in case a real
match was misjudged.

To find businesses without a website of their own, filter **Has website** to anything but `Yes`.
To find broken or expired websites, filter **Website status**.

## Cost

- **TomTom:** free up to 2,500 requests a day. Above that, requests are refused; you are
  never charged. A city-wide search uses roughly 5–60 requests.
- **Google:** each request returns up to 20 businesses. Requests are billed as "Text Search
  Enterprise": 1,000 free a month, then about $35 per 1,000 (check
  <https://mapsplatform.google.com/pricing/>). `--deep` uses up to about 64 requests per search.
- Visiting websites is free.

The tool prints how many requests each run used and how many today. The app shows the
day's total too (kept in `output/.usage.json`; Google's day ends at midnight Pacific time).

## Limitations

- Emails and social links come from the business's own website, so businesses without a
  website (or whose website the map service doesn't know) have neither.
- With TomTom, `Has website: No` often only means *TomTom* doesn't know the website. Use the
  Google Maps link to check.
- Websites built entirely with JavaScript, and sites that block automated visitors, can
  hide their emails and links from the tool.
- Map providers' terms limit how long their data may be stored. Treat the sheets as
  working snapshots, not a permanent database. If you contact businesses by email,
  follow your local marketing and privacy laws.
