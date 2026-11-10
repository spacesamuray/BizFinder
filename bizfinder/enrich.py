"""Visit business websites and collect email addresses and social media links."""

import json
import logging
import re
import warnings
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from urllib.parse import unquote, urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup
from urllib3.exceptions import NameResolutionError

log = logging.getLogger(__name__)

# Many small-business sites have expired or broken certificates. We still read
# them (and flag it in the sheet), so silence the per-request warning.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", module="bs4")
logging.getLogger("bs4").setLevel(logging.ERROR)  # "some characters could not be decoded" noise

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = (8, 15)  # seconds to connect, seconds to wait for data
MAX_PAGE_BYTES = 3_000_000
MAX_EXTRA_PAGES = 3  # contact/about pages to try when the homepage has no email
MAX_EMAILS = 5

# Spreadsheet column -> domains that belong to that platform.
SOCIAL_SITES = {
    "Facebook": ("facebook.com", "fb.com", "fb.me"),
    "Instagram": ("instagram.com",),
    "LinkedIn": ("linkedin.com",),
    "X (Twitter)": ("twitter.com", "x.com"),
    "TikTok": ("tiktok.com",),
    "YouTube": ("youtube.com", "youtu.be"),
    "WhatsApp": ("wa.me", "whatsapp.com"),
    "Telegram": ("t.me", "telegram.me"),
}
# Delivery apps and directories. A business whose "website" is its page there has no site of
# its own, and crawling that page would only find the platform's own social media links.
LISTING_SITES = {
    "Wolt": ("wolt.com",),
    "Glovo": ("glovoapp.com",),
    "Bolt Food": ("food.bolt.eu",),
    "Uber Eats": ("ubereats.com",),
    "Tripadvisor": ("tripadvisor.com",),
    "Booking.com": ("booking.com",),
}
# Share buttons, tracking pixels and embeds: on a social domain, but not the business's profile.
SOCIAL_JUNK_PATH = re.compile(
    r"^/(share\w*|sharing|intent|plugins|dialog|tr|embed|hashtag|login|watch|home\.php)\b", re.I
)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,24}")
NOT_EMAIL_ENDINGS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".avif", ".ico", ".css", ".js")
PLACEHOLDER_EMAIL_DOMAINS = (
    "example.com", "example.org", "domain.com", "yourdomain.com", "yoursite.com", "website.com",
    "mysite.com", "email.com", "company.com", "test.com", "sentry.io", "wixpress.com",
)

# Words in a link's URL or text that suggest a page worth checking for an email.
CONTACT_WORDS = ("contact", "kontakt", "contacto", "contatti", "contato", "контакт", "კონტაქტ")
ABOUT_WORDS = ("about", "impressum", "о нас", "о-нас", "შესახებ")

# website_status values that mean the site is down, not just unfriendly to bots.
BROKEN_STATUSES = ("Domain doesn't exist", "Unreachable", "Timed out", "Not found", "Server error")


def enrich_all(businesses, workers=10, crawl=True, stop=None, progress=None):
    """Work out whether each business has a real website and, if `crawl`, visit
    those websites in parallel to collect emails and social links.

    Ctrl+C or setting `stop` (a threading.Event) ends the crawl early; everything
    collected so far is kept. `progress(checked, total)` is called as sites are checked.
    """
    to_crawl = [b for b in businesses if _classify(b) == "Yes" and b.relevant is not False]
    if not crawl or not to_crawl or (stop is not None and stop.is_set()):
        return

    total = len(to_crawl)
    log.info("Checking %d websites for emails and social media...", total)
    if progress:
        progress(0, total)
    pool = ThreadPoolExecutor(max_workers=workers)
    pending = {pool.submit(_crawl, b) for b in to_crawl}
    checked = 0
    try:
        while pending:
            done, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
            for _ in done:
                checked += 1
                if checked % 10 == 0 or checked == total:
                    log.info("  %d/%d websites checked", checked, total)
            if done and progress:
                progress(checked, total)
            if stop is not None and stop.is_set():
                log.warning("Stopped early - keeping what was collected so far.")
                break
    except KeyboardInterrupt:
        log.warning("Stopped early - keeping what was collected so far.")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _classify(business):
    if not business.website:
        business.has_website = "No"
    elif platform := _platform(business.website, SOCIAL_SITES):
        # Plenty of small businesses list their Facebook or Instagram page as their "website".
        business.has_website = "Only social page"
        business.socials = {platform: business.website}
    elif listing := _platform(business.website, LISTING_SITES):
        business.has_website = "Only listing page"
        business.website_status = f"{listing} page"
    else:
        business.has_website = "Yes"
    return business.has_website


def _crawl(business):
    try:
        status, emails, socials = _read_site(business.website)
    except Exception:  # one odd website must never kill a long run
        log.debug("Could not read %s", business.website, exc_info=True)
        status, emails, socials = "Could not read page", [], {}
    # Assign whole values at the end so an interrupted run never saves half-updated rows.
    business.emails = _rank_emails(emails, business.website)[:MAX_EMAILS]
    business.socials = socials
    business.website_status = status


def _read_site(url):
    """Return (status, emails, socials) for a website. Contact pages are only
    visited when the homepage has no email address."""
    emails, socials = [], {}
    with requests.Session() as session:
        session.headers.update(HEADERS)
        try:
            home_url, soup = _fetch(session, url)
        except requests.RequestException as e:
            return _describe_error(e), emails, socials
        status = "OK" if session.verify else "SSL certificate problem"

        _scan(soup, home_url, emails, socials)
        for link in _contact_links(soup, home_url)[:MAX_EXTRA_PAGES]:
            if emails:
                break
            try:
                page_url, page = _fetch(session, link)
            except requests.RequestException:
                continue
            _scan(page, page_url, emails, socials)
    return status, emails, socials


def _fetch(session, url):
    """GET an HTML page and return (final url after redirects, parsed page).

    If the site's certificate is broken, retry without checking it and leave
    session.verify False so the caller can tell.
    """
    try:
        resp = session.get(url, timeout=TIMEOUT, stream=True)
    except requests.exceptions.SSLError:
        session.verify = False
        resp = session.get(url, timeout=TIMEOUT, stream=True)
    with resp:
        resp.raise_for_status()
        body = b""
        if "html" in resp.headers.get("Content-Type", "text/html").lower():
            for chunk in resp.iter_content(64 * 1024):
                body += chunk
                if len(body) >= MAX_PAGE_BYTES:
                    break
    return resp.url, BeautifulSoup(body, "html.parser")


def _describe_error(error):
    if isinstance(error, requests.HTTPError):
        code = error.response.status_code
        if code in (401, 403, 429):
            return f"Blocked automated check (HTTP {code})"
        if code in (404, 410):
            return f"Not found (HTTP {code})"
        if code >= 500:
            return f"Server error (HTTP {code})"
        return f"HTTP {code}"
    if isinstance(error, requests.Timeout):
        return "Timed out"
    if isinstance(error, requests.ConnectionError):
        # Usually an expired domain: the business stopped paying for it.
        if error.args and isinstance(getattr(error.args[0], "reason", None), NameResolutionError):
            return "Domain doesn't exist"
        return "Unreachable"
    return "Could not read page"


def _scan(soup, page_url, emails, socials):
    """Add the emails and social profile links found on one page."""
    # Cloudflare hides addresses from bots; the encoding is a simple XOR.
    for tag in soup.find_all(attrs={"data-cfemail": True}):
        _add_emails(emails, _decode_cfemail(tag["data-cfemail"]))

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("mailto:"):
            _add_emails(emails, unquote(href[7:]))
        elif "/cdn-cgi/l/email-protection#" in href:
            _add_emails(emails, _decode_cfemail(href.split("#", 1)[1]))
        elif url := _absolute(page_url, href):
            _add_social(socials, url)

    # Structured data (added by most SEO plugins) often lists the email and social profiles.
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.get_text())
        except ValueError:
            continue
        for node in _walk_json(data):
            if isinstance(node.get("email"), str):
                _add_emails(emails, node["email"])
            same_as = node.get("sameAs") or []
            for url in [same_as] if isinstance(same_as, str) else same_as:
                if isinstance(url, str):
                    _add_social(socials, url)

    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    _add_emails(emails, soup.get_text(" "))


def _add_emails(found, text):
    for email in EMAIL_RE.findall(text):
        email = email.lower().lstrip("._%+-")
        domain = email.rsplit("@", 1)[1]
        if (
            email not in found
            and not email.endswith(NOT_EMAIL_ENDINGS)
            and not any(domain == d or domain.endswith("." + d) for d in PLACEHOLDER_EMAIL_DOMAINS)
        ):
            found.append(email)


def _add_social(found, url):
    link = _social_link(url)
    if link and link[0] not in found:
        found[link[0]] = link[1]


def _platform(url, sites):
    """Name of the site in `sites` (SOCIAL_SITES or LISTING_SITES) that `url` is on, if any."""
    host = _site(url)
    for name, domains in sites.items():
        if any(host == d or host.endswith("." + d) for d in domains):
            return name
    return None


def _social_link(url):
    """Return (platform, cleaned url) if `url` points to a social media profile, else None."""
    platform = _platform(url, SOCIAL_SITES)
    if not platform:
        return None
    parts = urlparse(url.strip())
    path = parts.path.rstrip("/")
    if not path or SOCIAL_JUNK_PATH.match(path):
        return None
    # Numeric Facebook profiles and WhatsApp chat links need their query string; others don't.
    query = f"?{parts.query}" if parts.query and path in ("/profile.php", "/send") else ""
    return platform, f"https://{_site(url)}{path}{query}"


def _contact_links(soup, page_url):
    """Same-site links that look like contact or about pages, contact pages first."""
    site = _site(page_url)
    found = {}
    for a in soup.find_all("a", href=True):
        url = _absolute(page_url, a["href"])
        if not url or url in found or url.rstrip("/") == page_url.rstrip("/") or _site(url) != site:
            continue
        parts = urlparse(url)
        label = f"{unquote(parts.path)}?{unquote(parts.query)} {a.get_text(' ', strip=True)}".lower()
        if any(w in label for w in CONTACT_WORDS):
            found[url] = 0
        elif any(w in label for w in ABOUT_WORDS):
            found[url] = 1
    return sorted(found, key=found.get)


def _rank_emails(emails, website):
    """Addresses on the business's own domain first (info@clinic.ge before clinic@gmail.com)."""
    site = _site(website)
    return sorted(emails, key=lambda e: not (e.endswith("@" + site) or e.endswith("." + site)))


def _absolute(page_url, href):
    """Resolve a link against the page it is on, without its #fragment. None if malformed."""
    try:
        return urljoin(page_url, href.strip()).split("#")[0]
    except ValueError:
        return None


def _site(url):
    try:
        return urlparse(url.strip()).netloc.lower().split(":")[0].removeprefix("www.")
    except ValueError:
        return ""


def _decode_cfemail(encoded):
    try:
        key = int(encoded[:2], 16)
        return "".join(chr(int(encoded[i : i + 2], 16) ^ key) for i in range(2, len(encoded), 2))
    except ValueError:
        return ""


def _walk_json(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_json(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_json(value)
