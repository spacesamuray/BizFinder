"""The app: a small web server on this computer that runs searches and shows the saved
spreadsheets in your browser. Start it with `bizfinder` (see cli.py).

The page (static/) talks to it through a JSON API under /api/. One search runs at a
time, in a background thread; the page polls it for progress.

When its code changes (an update), the app restarts itself as soon as no search is
running, and the page offers to reload.
"""

import hashlib
import json
import logging
import mimetypes
import os
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import urlopen

from . import calls, results, usage
from .run import SOURCES, RunError, Search, has_key, run

log = logging.getLogger("bizfinder")

PACKAGE = Path(__file__).resolve().parent
STATIC = PACKAGE / "static"
DEFAULT_PORT = 8650
MAX_BODY = 64 * 1024
MAX_LOG_LINES = 2000


def _fingerprint(*patterns):
    """A short hash of the app's files, to notice when they change."""
    digest = hashlib.sha1()
    for pattern in patterns:
        for path in sorted(PACKAGE.glob(pattern)):
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


CODE = ("*.py",)  # what this process runs; a change needs a restart
PAGE = ("*.py", "static/*.*")  # what the browser runs too; a change needs a page reload
STARTED_CODE = _fingerprint(*CODE)


class Job:
    """One search running in the background, with its log and progress."""

    def __init__(self, search):
        self.id = uuid.uuid4().hex[:10]
        self.search = search
        self.stop = threading.Event()
        self.lines = []
        self.progress = {"stage": "start", "source": SOURCES[search.source][0]}
        self.state = "running"  # then "done" or "failed"
        self.result = None
        self.error = None
        self.started = time.time()
        self.finished = None

    def start(self):
        threading.Thread(target=self._run, name=f"search-{self.id}", daemon=True).start()

    def _run(self):
        handler = _ListHandler(self.lines)
        log.addHandler(handler)
        try:
            result = run(self.search, stop=self.stop, progress=self.progress.update)
            self.result = {
                "file": result.path.name,
                "found": result.found,
                "others": result.others,
                "requests": result.requests,
                "stopped": result.stopped,
            }
            self.state = "done"
        except RunError as e:
            self.error = str(e)
            self.state = "failed"
        except Exception as e:  # shown on the page instead of silently killing the thread
            log.exception("The search failed")
            self.error = f"Something went wrong: {e}"
            self.state = "failed"
        finally:
            self.finished = time.time()
            log.removeHandler(handler)

    def status(self, since=0):
        return {
            "id": self.id,
            "state": self.state,
            "queries": self.search.queries,
            "location": self.search.location,
            "progress": dict(self.progress),  # copied: the search thread keeps updating it
            "stopping": self.stop.is_set(),
            "lines": self.lines[since:],
            "lineCount": len(self.lines),
            "result": self.result,
            "error": self.error,
            "seconds": round((self.finished or time.time()) - self.started),
        }


class _ListHandler(logging.Handler):
    """Collects a search's log messages for the page."""

    def __init__(self, lines):
        super().__init__(logging.INFO)
        self.lines = lines

    def emit(self, record):
        if len(self.lines) < MAX_LOG_LINES:
            self.lines.append({"level": record.levelname.lower(), "text": record.getMessage()})


class App(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port):
        super().__init__(("127.0.0.1", port), Handler)
        self.port = port
        self.hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self.job = None
        self.lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server_version = "bizfinder"

    def log_message(self, format, *args):  # keep the terminal for search progress
        pass

    # ---------- routing ----------

    def do_GET(self):
        if not self._trusted():
            return
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        path = url.path
        try:
            if path == "/":
                self._file(STATIC / "index.html")
            elif path.startswith("/static/"):
                self._static(path.removeprefix("/static/"))
            elif path == "/api/ping":
                self._json({"app": "bizfinder"})
            elif path == "/api/setup":
                self._json(self._setup())
            elif path == "/api/saved":
                self._json({"saved": results.saved()})
            elif path == "/api/result":
                self._json(results.read(query.get("file", "")))
            elif path == "/api/calls":
                self._json({"calls": calls.load(), "statuses": calls.STATUSES})
            elif path == "/api/download":
                self._download(query.get("file", ""))
            elif path == "/api/job":
                job = self.server.job
                if job is None or (query.get("id") and query["id"] != job.id):
                    self._json({"job": None})
                else:
                    self._json({"job": job.status(int(query.get("since", 0) or 0))})
            else:
                self._error(HTTPStatus.NOT_FOUND, "Not found.")
        except FileNotFoundError:
            self._error(HTTPStatus.NOT_FOUND, "That spreadsheet is no longer in the output folder.")
        except Exception as e:
            log.debug("GET %s failed", path, exc_info=True)
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Could not read it: {e}")

    def do_POST(self):
        if not self._trusted(write=True):
            return
        path = urlparse(self.path).path
        try:
            body = self._body()
            if path == "/api/search":
                self._start(body)
            elif path == "/api/stop":
                job = self.server.job
                if job and job.state == "running":
                    job.stop.set()
                self._json({"ok": True})
            elif path == "/api/calls":
                self._json({"call": calls.update(body.get("key"), body)})
            elif path == "/api/reveal":
                self._reveal(body.get("file", ""))
            elif path == "/api/trash":
                results.trash(body.get("file", ""))
                self._json({"ok": True})
            else:
                self._error(HTTPStatus.NOT_FOUND, "Not found.")
        except FileNotFoundError:
            self._error(HTTPStatus.NOT_FOUND, "That spreadsheet is no longer in the output folder.")
        except (ValueError, OSError) as e:
            self._error(HTTPStatus.BAD_REQUEST, str(e))
        except Exception as e:
            log.debug("POST %s failed", path, exc_info=True)
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Something went wrong: {e}")

    # ---------- API ----------

    def _setup(self):
        return {
            "sources": [
                {"id": source, "name": name, "hasKey": has_key(source), "envVar": var, "today": usage.today(source)}
                for source, (name, var) in SOURCES.items()
            ],
            "output": str(results.OUTPUT),
            "version": _fingerprint(*PAGE),
            "stale": _fingerprint(*CODE) != STARTED_CODE,  # updated, but couldn't restart yet
        }

    def _start(self, body):
        queries = [q.strip() for q in body.get("queries", []) if isinstance(q, str) and q.strip()]
        location = str(body.get("location", "")).strip()
        source = body.get("source")
        if not queries:
            raise ValueError("Add at least one thing to search for.")
        if not location:
            raise ValueError("Say where to search, e.g. Tbilisi, Georgia.")
        if source not in SOURCES:
            raise ValueError("Choose Google Maps or TomTom.")
        if not has_key(source):
            name, var = SOURCES[source]
            raise ValueError(f"There's no {name} key yet. Put {var}=your-key in the .env file.")
        limit = body.get("limit")
        search = Search(
            queries=queries[:10],
            location=location,
            source=source,
            deep=bool(body.get("deep")),
            limit=int(limit) if limit else None,
            language=(str(body.get("language") or "").strip() or None),
            crawl=bool(body.get("crawl", True)),
        )
        with self.server.lock:
            if self.server.job and self.server.job.state == "running":
                self._error(HTTPStatus.CONFLICT, "A search is already running. Stop it or wait for it to finish.")
                return
            self.server.job = Job(search)
            self.server.job.start()
        self._json({"job": self.server.job.status()})

    def _download(self, name):
        path = results.find(name)
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(path.name)}")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _reveal(self, name):
        path = results.find(name)
        if sys.platform != "darwin":
            raise OSError(f"The file is in {path.parent}")
        subprocess.run(["open", "-R", str(path)], check=False)
        self._json({"ok": True})

    # ---------- plumbing ----------

    def _trusted(self, write=False):
        """Only serve this computer's browser and the app's own page. The Host check stops
        other websites reaching the app through DNS tricks; the Origin and JSON checks stop
        them from starting searches that would use up your API allowance."""
        if self.headers.get("Host", "") not in self.server.hosts:
            self._error(HTTPStatus.FORBIDDEN, "Open the app at http://127.0.0.1:%d" % self.server.port)
            return False
        if write:
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc not in self.server.hosts:
                self._error(HTTPStatus.FORBIDDEN, "Not allowed.")
                return False
            if self.headers.get_content_type() != "application/json":
                self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Send JSON.")
                return False
        return True

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ValueError("Request too large.")
        data = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(data, dict):
            raise ValueError("Send a JSON object.")
        return data

    def _static(self, rel):
        path = (STATIC / rel).resolve()
        if not path.is_relative_to(STATIC) or not path.is_file():
            self._error(HTTPStatus.NOT_FOUND, "Not found.")
            return
        self._file(path)

    def _file(self, path):
        data = path.read_bytes()
        kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if kind.startswith("text/") or kind in ("application/javascript", "image/svg+xml"):
            kind += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, data, status=HTTPStatus.OK):
        body = json.dumps(data, ensure_ascii=False, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status, message):
        self._json({"error": message}, status)


def serve(port=DEFAULT_PORT, open_browser=True):
    """Start the app and open it in the browser. If it's already running, just open it."""
    for candidate in range(port, port + 10):
        if _is_running(candidate):
            print(f"Bizfinder is already running at http://127.0.0.1:{candidate}")
            if open_browser:
                webbrowser.open(f"http://127.0.0.1:{candidate}/")
            return
        try:
            app = App(candidate)
            break
        except OSError:  # port taken by something else
            continue
    else:
        sys.exit(f"Ports {port}-{port + 9} are all in use. Try: bizfinder app --port 9000")

    url = f"http://127.0.0.1:{app.port}/"
    threading.Thread(target=_restart_when_updated, args=[app], name="updates", daemon=True).start()
    print(f"Bizfinder is running at {url}")
    print("Keep this window open while you use it. Press Ctrl+C to stop.\n")
    if open_browser:
        threading.Timer(0.3, webbrowser.open, [url]).start()
    try:
        app.serve_forever()
    except KeyboardInterrupt:
        if app.job and app.job.state == "running":
            app.job.stop.set()
        print("\nStopped.")
    finally:
        app.server_close()


def _restart_when_updated(app):
    """Restart this process when its code changes, once the change has settled, no search
    is running and the new code starts without errors. The terminal window stays the same."""
    settled = STARTED_CODE
    reported = None
    while True:
        time.sleep(2)
        now = _fingerprint(*CODE)
        if now == STARTED_CODE or now != settled:  # unchanged, or still being changed
            settled = now
            continue
        if app.job and app.job.state == "running":
            continue
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(PACKAGE.parent), os.environ.get("PYTHONPATH")]))}
        check = subprocess.run(
            [sys.executable, "-c", "import bizfinder.server"], env=env, capture_output=True, text=True, timeout=60
        )
        if check.returncode:
            if reported != now:
                reported = now
                print(f"\nBizfinder was updated, but the new version doesn't start, so the old one keeps running:\n{check.stderr[-1500:]}")
            continue
        print("\nBizfinder was updated. Restarting...", flush=True)
        os.execve(
            sys.executable,
            [sys.executable, "-m", "bizfinder", "app", "--port", str(app.port), "--no-open"],
            env,
        )


def _is_running(port):
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=0.5) as resp:
            return json.load(resp).get("app") == "bizfinder"
    except (URLError, OSError, ValueError):
        return False
