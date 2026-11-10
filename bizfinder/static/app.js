// Bizfinder app: saved searches on the left; a form for a new search; live progress while
// one runs; each result as a spreadsheet, a map and a summary. Talks to server.py.

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ESC[c]);
const fmt = new Intl.NumberFormat('en-US');
const share = (n, of) => (of ? Math.round((n / of) * 100) : 0);
const many = (n, one, other) => `${fmt.format(n)} ${n === 1 ? one : other}`;

const ICONS = {
  download: '<path d="M12 4v11m0 0l-4-4m4 4l4-4M5 19h14"/>',
  folder: '<path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>',
  more: '<circle cx="5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="19" cy="12" r="1.2"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
  table: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 4v16"/>',
  map: '<path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  columns: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M15 4v16"/>',
  filter: '<path d="M3 5h18l-7 8v6l-4-2v-4z"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 00-2-2H6a2 2 0 00-2 2v8a2 2 0 002 2h2"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  up: '<path d="M6 15l6-6 6 6"/>',
  down: '<path d="M6 9l6 6 6-6"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1h5"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 002 2h6a2 2 0 002-2l1-12M9 7V4h6v3"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  share: '<path d="M4 12v7a1 1 0 001 1h14a1 1 0 001-1v-7M12 3v13M7 8l5-5 5 5"/>',
  phone: '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 005 5L15 13l5 2v4a2 2 0 01-2 2A16 16 0 013 6a2 2 0 012-2"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 010 18M12 3a14 14 0 000 18"/>',
  pin: '<path d="M12 21s-7-6.2-7-11a7 7 0 0114 0c0 4.8-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/>',
};
const icon = (name) => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;

// Remembered per browser: column widths and visibility, the open tab, the last search.
const store = {
  get(key, fallback) {
    try {
      const value = localStorage.getItem(`bizfinder:${key}`);
      return value == null ? fallback : JSON.parse(value);
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(`bizfinder:${key}`, JSON.stringify(value));
    } catch {
      /* private window or storage off: settings just aren't remembered */
    }
  },
};

async function api(path, body) {
  const init =
    body === undefined
      ? {}
      : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), keepalive: true };
  let res;
  try {
    res = await fetch(path, init);
  } catch {
    throw new Error("Can't reach Bizfinder. Is it still running in the terminal?");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Something went wrong (HTTP ${res.status}).`);
  return data;
}

let toastTimer;
function toast(message) {
  const el = $('.toast');
  el.textContent = message;
  el.classList.add('is-on');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('is-on'), 2800);
}

async function copy(text, message) {
  try {
    await navigator.clipboard.writeText(text);
    toast(message);
  } catch {
    toast("Couldn't copy. Your browser blocked it.");
  }
}

// ---------- What the spreadsheet columns mean ----------

// Website statuses that mean the site is down (bizfinder/enrich.py BROKEN_STATUSES).
const BROKEN = ["Domain doesn't exist", 'Unreachable', 'Timed out', 'Not found', 'Server error'];
const SOCIAL = [
  ['Facebook', 'FB'],
  ['Instagram', 'IG'],
  ['LinkedIn', 'in'],
  ['X (Twitter)', 'X'],
  ['TikTok', 'TT'],
  ['YouTube', 'YT'],
  ['WhatsApp', 'WA'],
  ['Telegram', 'TG'],
];

// How a call went (calls.py STATUSES), with the colour of its label.
const CALL_STATUSES = {
  'No answer': 'warn',
  'Call back': 'warn',
  Interested: 'good',
  'Somewhat interested': 'good',
  Client: 'good',
  'Not interested': 'bad',
  'Wrong number': 'bad',
};
// What a result means, shown when you point at its button.
const CALL_HINTS = {
  'Somewhat interested': 'Send them a demo on WhatsApp',
};
const CALL_COLUMNS = ['Call status', 'Their response', 'How to improve', 'Called on'];
const CALL_FILTERS = [
  ['any', 'All calls'],
  ['todo', 'Not called yet'],
  ['called', 'Called'],
  ...Object.keys(CALL_STATUSES).map((s) => [s, s]),
];

// How each column shows in the grid. Columns not listed here show as plain text.
const COLUMNS = {
  Name: { width: 250 },
  Category: { width: 170 },
  Phone: { width: 150, kind: 'phone' },
  // Your call notes, edited in the details panel
  'Call status': { width: 140, kind: 'call' },
  'Their response': { width: 240 },
  'How to improve': { width: 240 },
  'Called on': { width: 130, kind: 'date', hidden: true },
  'Has website': { width: 150, kind: 'presence' },
  Website: { width: 210, kind: 'link' },
  'Website status': { width: 190, kind: 'status' },
  Email: { width: 230, kind: 'email' },
  'Social media': { width: 160, kind: 'socials' }, // made here from the platform columns
  Rating: { width: 86, kind: 'rating', num: true },
  Reviews: { width: 92, kind: 'int', num: true },
  'Business status': { width: 150, kind: 'business' },
  Address: { width: 320 },
  'Google Maps': { width: 116, kind: 'maps' },
  Search: { width: 170 },
  'Intl. phone': { width: 160, kind: 'phone', hidden: true },
  'Other emails': { width: 240, hidden: true },
  ...Object.fromEntries(SOCIAL.map(([name]) => [name, { width: 210, kind: 'link', hidden: true }])),
  Latitude: { width: 100, num: true, hidden: true },
  Longitude: { width: 100, num: true, hidden: true },
  'Place ID': { width: 220, hidden: true },
  'Google types': { width: 260, hidden: true },
};
const ORDER = Object.keys(COLUMNS);

// Kinds of web presence: the map colours and the main filters use these.
const KINDS = {
  own: 'Own website',
  broken: 'Broken website',
  social: 'Only a social or listing page',
  none: 'No website',
};

const QUICK = [
  { id: 'all', label: 'All', test: () => true },
  {
    id: 'leads',
    label: 'Needs a website',
    title: 'No website, only a social or listing page, or a broken website',
    test: (r) => r._kind !== 'own',
  },
  { id: 'none', label: 'No website', dot: 'none', test: (r) => r._kind === 'none' },
  { id: 'social', label: 'Social page only', dot: 'social', test: (r) => r._kind === 'social' },
  { id: 'broken', label: 'Broken website', dot: 'broken', test: (r) => r._kind === 'broken' },
  { id: 'own', label: 'Own website', dot: 'own', test: (r) => r._kind === 'own' },
  { id: 'email', label: 'Has email', test: (r) => !!r.Email },
];

function kindOf(r) {
  const has = String(r['Has website'] ?? '');
  if (has === 'Yes' || (!has && r.Website)) {
    return BROKEN.some((b) => String(r['Website status'] ?? '').startsWith(b)) ? 'broken' : 'own';
  }
  return has.startsWith('Only') ? 'social' : 'none';
}

function prepare(sheet) {
  const cols = sheet.columns;
  return sheet.rows.map((values, i) => {
    const r = { _i: i };
    cols.forEach((col, k) => {
      r[col] = values[k] ?? '';
    });
    r._social = SOCIAL.filter(([name]) => r[name]).map(([name, short]) => ({ name, short, url: r[name] }));
    r['Social media'] = r._social.map((s) => s.name).join(', ');
    r._kind = kindOf(r);
    r._base = cols.map((col) => r[col]).join(' \u0001 ').toLowerCase();
    applyCall(r);
    return r;
  });
}

// Call notes are keyed like in calls.py: by place ID, so they follow a business into other searches.
const callKey = (r) => String(r['Place ID'] || `${r.Name}|${r.Address}`);

function applyCall(r) {
  const key = callKey(r);
  const c = { ...state.calls[key], ...unsavedFields(key) };
  r._call = c;
  r['Call status'] = c.status || '';
  r['Their response'] = c.response || '';
  r['How to improve'] = c.improve || '';
  r['Called on'] = c.calledAt || '';
  r._text = `${r._base} \u0001 ${[c.status, c.response, c.improve].filter(Boolean).join(' ').toLowerCase()}`;
}

function callFilter(id) {
  if (id === 'todo') return (r) => !r['Call status'];
  if (id === 'called') return (r) => !!r['Call status'];
  if (CALL_STATUSES[id]) return (r) => r['Call status'] === id;
  return () => true;
}

function safeUrl(value) {
  const s = String(value ?? '').trim();
  if (/^(https?:|mailto:|tel:)/i.test(s)) return s;
  return /^[\w-]+(\.[\w-]+)+(\/|$)/.test(s) ? `http://${s}` : '';
}

function shortUrl(value) {
  let s = String(value ?? '');
  try {
    s = decodeURI(s);
  } catch {
    /* keep it encoded */
  }
  return s.replace(/^https?:\/\/(www\.)?/i, '').replace(/\/$/, '');
}

const ext = (url, text, cls = '') =>
  safeUrl(url)
    ? `<a class="${cls}" href="${esc(safeUrl(url))}" target="_blank" rel="noopener noreferrer">${text}</a>`
    : text;

function presenceTone(value) {
  return value === 'Yes' ? 'good' : value === 'No' ? 'bad' : 'warn';
}

function statusTone(value) {
  return value === 'OK' ? 'good' : BROKEN.some((b) => value.startsWith(b)) ? 'bad' : 'warn';
}

const pill = (text, tone = '') => `<span class="pill ${tone}">${esc(text)}</span>`;

function businessPill(value) {
  if (!value || value === 'Open') return value ? `<span class="t">${esc(value)}</span>` : '';
  return pill(value, value.startsWith('Permanently') ? 'bad' : 'warn');
}

function emails(r) {
  return [r.Email, ...String(r['Other emails'] || '').split(',')].map((e) => e.trim()).filter(Boolean);
}

function cellHtml(r, key) {
  const v = r[key];
  if (v === '' || v == null) return '';
  switch ((COLUMNS[key] || {}).kind) {
    case 'phone':
      return `<a href="tel:${esc(String(v).replace(/[^\d+]/g, ''))}">${esc(v)}</a>`;
    case 'presence':
      return pill(v === 'Yes' ? 'Yes' : v, presenceTone(v));
    case 'status':
      return pill(v, statusTone(String(v)));
    case 'link':
      return ext(v, `<span class="t">${esc(shortUrl(v))}</span>`);
    case 'email':
      return `<a href="mailto:${esc(v)}"><span class="t">${esc(v)}</span></a>`;
    case 'socials':
      return `<span class="socials">${r._social
        .map((s) => ext(s.url, esc(s.short), 'soc').replace('<a ', `<a title="${esc(s.name)}" `))
        .join('')}</span>`;
    case 'rating':
      return `<span class="stars" aria-hidden="true">★</span>${esc(Number(v).toFixed(1))}`;
    case 'int':
      return esc(fmt.format(v));
    case 'business':
      return businessPill(String(v));
    case 'call':
      return pill(v, CALL_STATUSES[v] || '');
    case 'date':
      return `<span class="t">${esc(niceDate(v))}</span>`;
    case 'maps':
      return ext(v, `Open map ${icon('external')}`);
    default:
      return `<span class="t">${esc(v)}</span>`;
  }
}

function sortValue(r, key) {
  if (key === 'Social media') return r._social.length || '';
  return r[key];
}

function compareRows(a, b, key, dir) {
  const x = sortValue(a, key);
  const y = sortValue(b, key);
  const ex = x === '' || x == null;
  const ey = y === '' || y == null;
  if (ex || ey) return ex === ey ? 0 : ex ? 1 : -1; // empty cells last either way
  const c =
    typeof x === 'number' && typeof y === 'number'
      ? x - y
      : String(x).localeCompare(String(y), undefined, { numeric: true, sensitivity: 'base' });
  return dir === 'asc' ? c : -c;
}

// ---------- App state ----------

const state = {
  setup: null,
  saved: [],
  job: null,
  jobPolling: false,
  current: null, // file name of the open result
  cache: new Map(),
  calls: {}, // call notes by callKey()
  prefill: null, // for "Search again": the next new-search form starts with these
};

const prefs = {
  hidden: store.get('hidden', {}), // column -> true/false, overriding the default
  widths: store.get('widths', {}),
};

const view = {
  data: null,
  sheet: 'businesses',
  all: [], // rows of the open sheet
  rows: [], // after filters and sorting
  available: [],
  columns: [],
  quick: 'all',
  call: 'any', // CALL_FILTERS id
  q: '',
  filters: {},
  showFilters: false,
  sort: null,
  tab: store.get('tab', 'table'),
  selected: null,
  selIndex: -1, // where the selected row was, for next/previous once a filter hides it
};

const main = $('#main');
const ROW_H = 36;
const RN_W = 52;

// ---------- Sidebar ----------

function splitTitle(title) {
  const at = String(title).lastIndexOf(' in ');
  return at > 0 ? [title.slice(0, at), title.slice(at + 4)] : [title, ''];
}

function niceDate(text) {
  const d = new Date(String(text).replace(' ', 'T'));
  if (Number.isNaN(d.getTime())) return text;
  const sameYear = d.getFullYear() === new Date().getFullYear();
  return d.toLocaleString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: sameYear ? undefined : 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

const shortSource = (source) => (String(source).startsWith('Google') ? 'Google' : source);

function renderSaved() {
  const filter = ($('.side-filter').value || '').trim().toLowerCase();
  const items = state.saved.filter((s) => !filter || s.title.toLowerCase().includes(filter));
  $('.side-count').textContent = state.saved.length || '';
  $('.side-filter').hidden = state.saved.length < 7;
  $('.saved').innerHTML = items.length
    ? items
        .map((s) => {
          const [what, where] = splitTitle(s.title);
          const meta = [where, `${fmt.format(s.found)} found`, shortSource(s.source), niceDate(s.generated)];
          return `<a class="saved-item${s.file === state.current ? ' is-active' : ''}" href="#r/${encodeURIComponent(s.file)}">
            <span class="saved-title">${esc(what)}</span>
            <span class="saved-meta">${esc(meta.filter(Boolean).join(' · '))}</span>
          </a>`;
        })
        .join('')
    : `<p class="saved-empty">${state.saved.length ? 'Nothing matches.' : 'Your searches will show up here.'}</p>`;
}

function renderUsage() {
  const sources = (state.setup?.sources || []).filter((s) => s.hasKey);
  $('.usage').innerHTML = sources
    .map((s) => {
      const t = s.today;
      const resets = new Date(t.resets).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
      const used = t.free ? `<b>${fmt.format(t.used)}</b> of ${fmt.format(t.free)}` : `<b>${fmt.format(t.used)}</b>`;
      return `<div class="usage-row" title="Requests to ${esc(s.name)} today. The count starts again at ${resets}.">
        <div class="usage-line"><span>${esc(s.name)} today</span><span class="num">${used}</span></div>
        ${t.free ? `<div class="meter"><i style="width:${Math.min(100, share(t.used, t.free))}%"></i></div>` : ''}
      </div>`;
    })
    .join('');
}

function renderSideJob() {
  const el = $('.side-job');
  const job = state.job;
  if (!job || job.state !== 'running') {
    el.hidden = true;
    return;
  }
  const p = job.progress || {};
  const text =
    p.stage === 'websites'
      ? `Checking websites ${fmt.format(p.checked || 0)} of ${fmt.format(p.total || 0)}`
      : p.stage === 'save'
        ? 'Saving the spreadsheet'
        : `${fmt.format(p.found || 0)} found so far`;
  el.hidden = false;
  el.classList.toggle('is-active', location.hash === '#job');
  el.innerHTML = `<span class="side-job-top"><span class="spinner"></span>${job.stopping ? 'Stopping…' : 'Searching…'}</span>
    <span class="side-job-text">${esc(job.queries.join(', '))} · ${esc(text)}</span>`;
}

async function loadSaved() {
  const { saved } = await api('/api/saved');
  state.saved = saved;
  renderSaved();
}

async function loadCalls() {
  try {
    state.calls = (await api('/api/calls')).calls;
  } catch (err) {
    toast(`Call notes: ${err.message}`);
  }
}

async function loadSetup() {
  state.setup = await api('/api/setup');
  renderUsage();
  checkVersion();
  if (state.started && Object.keys(unsaved).length && !state.setup.stale && state.setup.version) retryUnsaved();
}

// The app restarts itself after an update; the page then needs a reload. An app started
// before this check existed has no version and needs one manual restart.
function checkVersion() {
  const s = state.setup;
  state.pageVersion ??= s.version;
  const banner = $('.banner');
  if (!s.version || s.stale) {
    banner.innerHTML = `<span><b>Bizfinder needs a restart</b> to use its latest version. Until then call notes can't be saved (this browser keeps them meanwhile). In the terminal window where it runs, press Ctrl+C, then type <code>bizfinder</code>.</span>`;
    banner.hidden = false;
  } else if (s.version !== state.pageVersion) {
    banner.innerHTML = `<span><b>Bizfinder was updated.</b> Reload the page to use the new version.</span><button class="btn btn-sm btn-primary" data-reload>Reload</button>`;
    banner.hidden = false;
  } else {
    banner.hidden = true;
  }
}

// ---------- Routing ----------

function setMain(kind) {
  main.className = `main${kind === 'result' ? ' is-result' : ''}`;
  if (kind !== 'result') {
    destroyMap();
    closeDrawer();
  }
}

async function route() {
  const hash = decodeURIComponent(location.hash.replace(/^#/, ''));
  if (!hash.startsWith('r/')) state.current = null;
  renderSaved();
  renderSideJob();
  if (hash === 'new') {
    const prefill = state.prefill || {};
    state.prefill = null;
    return showNew(prefill);
  }
  if (hash === 'job') return state.job ? showJob() : location.replace('#');
  if (hash.startsWith('r/')) return showResult(hash.slice(2));
  if (state.job?.state === 'running') return location.replace('#job');
  if (state.saved.length) return location.replace(`#r/${encodeURIComponent(state.saved[0].file)}`);
  return showNew();
}

// ---------- New search ----------

const SUGGESTIONS = [
  'dentist',
  'beauty salon',
  'restaurant',
  'cafe',
  'hotel',
  'car repair',
  'flower shop',
  'pharmacy',
  'gym',
  'law firm',
  'real estate agency',
  'clothing store',
];

const LANGUAGES = [
  ['', 'As on the map'],
  ['en', 'English'],
  ['ka', 'Georgian'],
  ['ru', 'Russian'],
];

function showNew(prefill = {}) {
  setMain('new');
  const sources = state.setup?.sources || [];
  const draft = store.get('draft', {});
  const withKey = sources.filter((s) => s.hasKey).map((s) => s.id);
  let source = prefill.source || draft.source;
  if (!withKey.includes(source)) source = withKey[0] || 'google';
  const queries = [...(prefill.queries || [])];

  const sourceCard = (s) => {
    const t = s.today;
    const text =
      s.id === 'google'
        ? 'Best data: finds many more websites, plus ratings and reviews.'
        : 'Free: 2,500 requests a day. Finds fewer websites.';
    const used = s.hasKey
      ? `Used today: ${fmt.format(t.used)}${t.free ? ` of ${fmt.format(t.free)}` : ''} requests`
      : `No key yet. Add ${s.envVar} to the .env file.`;
    return `<label class="source">
      <input type="radio" name="source" value="${s.id}" ${s.id === source ? 'checked' : ''} ${s.hasKey ? '' : 'disabled'} />
      <span class="source-name">${esc(s.name)}</span>
      <span class="source-text">${text}</span>
      <span class="source-used">${esc(used)}</span>
    </label>`;
  };

  main.innerHTML = `<div class="page">
    <header class="page-head">
      <h1>New search</h1>
      <p>Find businesses on the map, then visit their websites for emails and social media.</p>
    </header>
    <form class="form" novalidate>
      <div class="field">
        <label for="q-input">What are you looking for?</label>
        <div class="tags" data-tags></div>
        <p class="hint">Press Enter after each one. Add the Georgian words too (for example სტომატოლოგია): Google finds more that way.</p>
        <div class="suggest" aria-label="Suggestions">${SUGGESTIONS.map((s) => `<button type="button" data-suggest="${esc(s)}">+ ${esc(s)}</button>`).join('')}</div>
      </div>

      <div class="field">
        <label for="where">Where?</label>
        <input class="input" id="where" name="location" autocomplete="off" value="${esc(prefill.location || draft.location || 'Tbilisi, Georgia')}" placeholder="City or area, e.g. Batumi, Georgia" />
      </div>

      <div class="field">
        <span class="field-label">Map service</span>
        <div class="sources" role="radiogroup">${sources.map(sourceCard).join('')}</div>
      </div>

      <div class="checks">
        <label class="check">
          <input type="checkbox" name="deep" ${draft.deep ? 'checked' : ''} />
          <span>Search the whole area, part by part</span>
          <small data-deep-hint></small>
        </label>
        <label class="check">
          <input type="checkbox" name="crawl" ${draft.crawl === false ? '' : 'checked'} />
          <span>Visit websites to find emails and social media</span>
          <small>Takes a few minutes for a few hundred websites.</small>
        </label>
      </div>

      <details class="more">
        <summary>More options</summary>
        <div class="more-grid">
          <div class="field">
            <label for="limit">Most businesses per search</label>
            <input class="input" id="limit" name="limit" type="number" min="1" step="1" placeholder="No limit" />
          </div>
          <div class="field">
            <label for="language">Language of names and addresses</label>
            <select class="input" id="language" name="language">${LANGUAGES.map(([v, l]) => `<option value="${v}">${l}</option>`).join('')}</select>
          </div>
        </div>
      </details>

      <p class="form-error" role="alert" hidden></p>

      <div class="form-foot">
        <p class="estimate" data-estimate></p>
        <button class="btn btn-primary btn-lg" type="submit">${icon('search')} Start search</button>
      </div>
    </form>
  </div>`;

  const form = $('form', main);
  const tagsEl = $('[data-tags]', form);

  const renderTags = () => {
    tagsEl.innerHTML =
      queries
        .map(
          (q, i) =>
            `<span class="tag">${esc(q)}<button type="button" data-remove="${i}" aria-label="Remove ${esc(q)}">${icon('close')}</button></span>`,
        )
        .join('') +
      `<input id="q-input" autocomplete="off" placeholder="${queries.length ? 'Add another…' : 'e.g. dentist'}" />`;
    update();
  };
  const addTag = (text) => {
    for (const part of String(text).split(',')) {
      const q = part.trim();
      if (q && !queries.some((x) => x.toLowerCase() === q.toLowerCase())) queries.push(q);
    }
  };
  const commitTyped = () => {
    const input = $('#q-input', form);
    if (input?.value.trim()) {
      addTag(input.value);
      input.value = '';
      return true;
    }
    return false;
  };

  const update = () => {
    const src = form.source?.value || source;
    const deep = form.deep;
    deep.disabled = src === 'tomtom';
    $('[data-deep-hint]', form).textContent =
      src === 'tomtom'
        ? 'TomTom always does this, and its requests are free.'
        : 'Google gives at most 60 places per search. This finds hundreds in a big city, but uses up to about 60 requests per search word.';
    const n = Math.max(1, queries.length + ($('#q-input', form)?.value.trim() ? 1 : 0));
    const info = sources.find((s) => s.id === src);
    let estimate;
    if (src === 'tomtom') estimate = `Usually 5 to 60 free requests per search word.`;
    else if (deep.checked) estimate = `Up to about ${fmt.format(64 * n)} Google requests.`;
    else estimate = `About ${n} to ${3 * n} Google requests.`;
    if (info?.hasKey) estimate += ` Used today: ${fmt.format(info.today.used)}.`;
    $('[data-estimate]', form).textContent = estimate;
    $$('[data-suggest]', form).forEach((b) => {
      b.hidden = queries.some((q) => q.toLowerCase() === b.dataset.suggest);
    });
  };

  tagsEl.addEventListener('click', (e) => {
    const remove = e.target.closest('[data-remove]');
    if (remove) {
      queries.splice(+remove.dataset.remove, 1);
      renderTags();
    }
    $('#q-input', form).focus();
  });
  tagsEl.addEventListener('keydown', (e) => {
    if (e.target.id !== 'q-input') return;
    if ((e.key === 'Enter' || e.key === ',') && e.target.value.trim()) {
      e.preventDefault();
      commitTyped();
      renderTags();
      $('#q-input', form).focus();
    } else if (e.key === 'Backspace' && !e.target.value && queries.length) {
      queries.pop();
      renderTags();
      $('#q-input', form).focus();
    }
  });
  tagsEl.addEventListener('input', update);
  $('.suggest', form).addEventListener('click', (e) => {
    const b = e.target.closest('[data-suggest]');
    if (!b) return;
    addTag(b.dataset.suggest);
    renderTags();
  });
  form.addEventListener('change', update);

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    commitTyped();
    renderTags();
    const error = $('.form-error', form);
    const button = $('button[type="submit"]', form);
    const body = {
      queries,
      location: form.location.value.trim(),
      source: form.source?.value,
      deep: form.deep.checked && !form.deep.disabled,
      crawl: form.crawl.checked,
      limit: form.limit.value ? Number(form.limit.value) : null,
      language: tomtomLanguage(form.language.value, form.source?.value),
    };
    error.hidden = true;
    if (!body.queries.length) return showError(error, 'Add at least one thing to search for.', '#q-input');
    if (!body.location) return showError(error, 'Say where to search, for example Tbilisi, Georgia.', '#where');
    if (!body.source) return showError(error, 'Add a Google Maps or TomTom key to the .env file first.');
    store.set('draft', { location: body.location, source: body.source, deep: form.deep.checked, crawl: body.crawl });
    button.disabled = true;
    try {
      const { job } = await api('/api/search', body);
      state.job = job;
      location.hash = '#job';
      pollJob();
    } catch (err) {
      showError(error, err.message);
      button.disabled = false;
    }
  });

  renderTags();
  $('#q-input', form).focus();
}

// TomTom wants region codes ("en-GB") and has no Georgian.
function tomtomLanguage(lang, source) {
  if (source !== 'tomtom' || !lang) return lang || null;
  return { en: 'en-GB', ru: 'ru-RU' }[lang] || null;
}

function showError(el, message, focus) {
  el.textContent = message;
  el.hidden = false;
  if (focus) $(focus)?.focus();
}

// ---------- Running search ----------

const STAGES = ['search', 'websites', 'save'];

function showJob() {
  setMain('job');
  main.innerHTML = `<div class="page job">
    <div class="job-card">
      <div class="job-top">
        <div>
          <h1 data-title></h1>
          <p data-sub></p>
        </div>
        <button class="btn" data-stop>${icon('stop')} Stop and save</button>
      </div>
      <div class="steps">
        <div class="step" data-step="search"><span class="step-name"><span class="step-dot">1</span>Find on the map</span><span class="step-value"></span></div>
        <div class="step" data-step="websites"><span class="step-name"><span class="step-dot">2</span>Check websites</span><span class="step-value"></span></div>
        <div class="step" data-step="save"><span class="step-name"><span class="step-dot">3</span>Save spreadsheet</span><span class="step-value"></span></div>
      </div>
      <div class="bar-track" data-bar><i></i></div>
      <div class="job-result" data-result hidden></div>
    </div>
    <pre class="log" data-log aria-label="Search log"></pre>
  </div>`;
  $('[data-stop]', main).addEventListener('click', async (e) => {
    e.currentTarget.disabled = true;
    e.currentTarget.textContent = 'Stopping…';
    try {
      await api('/api/stop', {});
    } catch (err) {
      toast(err.message);
    }
  });
  paintJob(true);
}

function paintJob(full) {
  const job = state.job;
  if (!job || !$('[data-step]', main)) return;
  const p = job.progress || {};
  const running = job.state === 'running';
  const at = job.state === 'done' ? 3 : Math.max(0, STAGES.indexOf(p.stage));
  const mm = `${Math.floor(job.seconds / 60)}:${String(job.seconds % 60).padStart(2, '0')}`;

  $('[data-title]', main).textContent = `${running ? 'Searching' : job.state === 'done' ? 'Done' : 'Stopped'}: ${job.queries.join(', ')}`;
  $('[data-sub]', main).textContent = `${p.source || ''} · ${job.location} · ${mm}`;
  const stop = $('[data-stop]', main);
  stop.hidden = !running;
  if (job.stopping && running) {
    stop.disabled = true;
    stop.textContent = 'Stopping…';
  }

  const values = {
    search:
      `${fmt.format(p.found || 0)} found` +
      (p.steps > 1 && at === 0 ? ` · word ${p.step} of ${p.steps}` : '') +
      (p.requests ? ` · ${fmt.format(p.requests)} requests` : ''),
    websites:
      p.total != null
        ? `${fmt.format(p.checked || 0)} of ${fmt.format(p.total)}`
        : at > 1 || job.state === 'done'
          ? 'Skipped'
          : 'Waiting',
    save: job.state === 'done' ? 'Saved' : at === 2 ? 'Saving…' : 'Waiting',
  };
  STAGES.forEach((stage, i) => {
    const el = $(`[data-step="${stage}"]`, main);
    el.classList.toggle('is-now', running && i === at);
    el.classList.toggle('is-done', i < at || job.state === 'done');
    $('.step-dot', el).textContent = i < at || job.state === 'done' ? '✓' : running && i === at ? '' : i + 1;
    $('.step-value', el).textContent = values[stage];
  });

  const bar = $('[data-bar]', main);
  const busy = running && (at === 0 || at === 2);
  bar.classList.toggle('is-busy', busy);
  bar.hidden = !running;
  $('i', bar).style.width = at === 1 && p.total ? `${share(p.checked || 0, p.total)}%` : '0%';

  const result = $('[data-result]', main);
  if (job.state === 'done') {
    const r = job.result;
    result.hidden = false;
    result.classList.remove('is-failed');
    result.innerHTML = `<span>${r.stopped ? 'Stopped early. ' : ''}Saved ${many(r.found, 'business', 'businesses')}${r.requests ? ` using ${fmt.format(r.requests)} requests` : ''}.</span>
      <a class="btn btn-primary" href="#r/${encodeURIComponent(r.file)}">Open results</a>`;
  } else if (job.state === 'failed') {
    result.hidden = false;
    result.classList.add('is-failed');
    result.innerHTML = `<span>${esc(job.error)}</span><a class="btn" href="#new">Try again</a>`;
  }

  const log = $('[data-log]', main);
  const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
  if (full) log.innerHTML = '';
  const lines = full ? job.allLines || [] : job.newLines || [];
  log.insertAdjacentHTML(
    'beforeend',
    lines.map((l) => `<span class="${esc(l.level)}">${esc(l.text)}</span>\n`).join(''),
  );
  if (atBottom || full) log.scrollTop = log.scrollHeight;
}

async function pollJob() {
  if (state.jobPolling) return;
  state.jobPolling = true;
  try {
    while (state.job && state.job.state === 'running') {
      await new Promise((r) => setTimeout(r, 700));
      let job;
      try {
        ({ job } = await api(`/api/job?id=${state.job.id}&since=${state.job.allLines?.length || 0}`));
      } catch {
        continue; // the server may be busy; try again
      }
      if (!job) {
        state.job = null;
        break;
      }
      const allLines = [...(state.job.allLines || []), ...job.lines];
      state.job = { ...job, allLines, newLines: job.lines };
      paintJob(false);
      renderSideJob();
    }
  } finally {
    state.jobPolling = false;
  }
  const job = state.job;
  if (!job) return;
  loadSetup().catch(() => {});
  if (job.state === 'done') {
    await loadSaved().catch(() => {});
    const r = job.result;
    toast(`Saved ${many(r.found, 'business', 'businesses')}`);
    if (location.hash === '#job') location.hash = `#r/${encodeURIComponent(r.file)}`;
  } else if (job.state === 'failed' && location.hash !== '#job') {
    toast(`The search stopped: ${job.error}`);
  }
}

// ---------- Result ----------

async function showResult(file) {
  closeDrawer();
  state.current = file;
  renderSaved();
  setMain('result');
  let data = state.cache.get(file);
  if (!data) {
    main.innerHTML = `<div class="empty"><span class="spinner"></span></div>`;
    try {
      data = await api(`/api/result?file=${encodeURIComponent(file)}`);
    } catch (err) {
      main.innerHTML = `<div class="empty"><p>${esc(err.message)}</p><a class="btn" href="#">Back</a></div>`;
      return;
    }
    state.cache.set(file, data);
  }
  if (state.current !== file) return; // the user clicked something else meanwhile
  view.data = data;
  view.quick = 'all';
  view.call = 'any';
  view.q = '';
  view.filters = {};
  view.sort = null;
  view.selected = null;
  openSheet('businesses');
  renderResult();
}

function openSheet(sheet) {
  view.sheet = sheet;
  const data = view.data[sheet === 'others' ? 'otherResults' : 'businesses'];
  view.all = prepare(data);
  const present = new Set(data.columns);
  if (SOCIAL.some(([name]) => present.has(name))) present.add('Social media');
  CALL_COLUMNS.forEach((c) => present.add(c));
  const keys = [...ORDER.filter((k) => present.has(k)), ...data.columns.filter((k) => k && !COLUMNS[k])];
  // Leave out columns that are empty in every row (e.g. ratings for TomTom).
  view.available = keys.filter(
    (k) => k === 'Name' || CALL_COLUMNS.includes(k) || view.all.some((r) => r[k] !== '' && r[k] != null),
  );
  pickColumns();
}

function pickColumns() {
  view.columns = view.available.filter((k) => k === 'Name' || !(prefs.hidden[k] ?? COLUMNS[k]?.hidden));
}

const colWidth = (key) => prefs.widths[key] || COLUMNS[key]?.width || 160;

function applyFilters() {
  const words = view.q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const quick = QUICK.find((f) => f.id === view.quick) || QUICK[0];
  const called = callFilter(view.call);
  const filters = Object.entries(view.filters)
    .map(([k, v]) => [k, v.trim().toLowerCase()])
    .filter(([, v]) => v);
  let rows = view.all.filter(
    (r) =>
      quick.test(r) &&
      called(r) &&
      words.every((w) => r._text.includes(w)) &&
      filters.every(([k, v]) => String(r[k] ?? '').toLowerCase().includes(v)),
  );
  if (view.sort) rows = rows.slice().sort((a, b) => compareRows(a, b, view.sort.key, view.sort.dir));
  view.rows = rows;
}

function renderResult() {
  const d = view.data;
  const [what, where] = splitTitle(d.title);
  const tabs = [
    ['table', 'Table', 'table'],
    ['map', 'Map', 'map'],
    ['summary', 'Summary', 'chart'],
  ];
  main.innerHTML = `
    <header class="result-head">
      <div>
        <p class="eyebrow">${esc(d.source)} · ${esc(niceDate(d.generated))}</p>
        <h1>${esc(what)}${where ? ` <span class="muted">in ${esc(where)}</span>` : ''}</h1>
      </div>
      <div class="head-actions">
        <a class="btn" href="/api/download?file=${encodeURIComponent(d.file)}">${icon('download')} Download .xlsx</a>
        <button class="btn" data-act="reveal">${icon('folder')} Show in Finder</button>
        <button class="btn btn-icon" data-act="menu" aria-label="More" aria-haspopup="true" aria-expanded="false">${icon('more')}</button>
        <div class="menu" data-menu hidden>
          <button data-act="again">${icon('search')} Search again</button>
          <button class="is-danger" data-act="trash">${icon('trash')} Move to Trash</button>
        </div>
      </div>
    </header>
    <section class="tiles" data-tiles></section>
    ${
      d.source === 'TomTom'
        ? `<p class="note">TomTom knows few websites, so “No website” often only means TomTom doesn't have it. Use the Google Maps link in a row to check before you contact them.</p>`
        : ''
    }
    <div class="views">
      <div class="tabs" role="tablist" aria-label="View">${tabs
        .map(
          ([id, label, ic]) =>
            `<button role="tab" data-tab="${id}" aria-selected="${view.tab === id}">${icon(ic)} ${label}</button>`,
        )
        .join('')}</div>
      ${
        d.others
          ? `<div class="tabs" role="tablist" aria-label="Sheet">
              <button role="tab" data-sheet="businesses" aria-selected="${view.sheet === 'businesses'}">Businesses <span class="count">${fmt.format(d.found)}</span></button>
              <button role="tab" data-sheet="others" aria-selected="${view.sheet === 'others'}" title="Results that don't look like what you searched for">Other results <span class="count">${fmt.format(d.others)}</span></button>
            </div>`
          : ''
      }
    </div>
    <div class="tools" data-tools>
      <div class="chips" data-chips role="group" aria-label="Show"></div>
      <select class="select" data-call aria-label="Show by call"></select>
      <label class="search">${icon('search')}<input type="search" data-q placeholder="Search this list" aria-label="Search the results" value="${esc(view.q)}" /></label>
      <button class="btn btn-sm" data-act="filters" aria-pressed="${view.showFilters}">${icon('filter')} Filters</button>
      <div class="popover-wrap">
        <button class="btn btn-sm" data-act="columns" aria-haspopup="true">${icon('columns')} Columns</button>
        <div class="popover" data-pop="columns" hidden></div>
      </div>
      <div class="popover-wrap">
        <button class="btn btn-sm" data-act="export" aria-haspopup="true">${icon('share')} Export</button>
        <div class="popover menu" data-pop="export" hidden>
          <button data-act="copy-emails">${icon('mail')} Copy emails</button>
          <button data-act="copy-phones">${icon('phone')} Copy phone numbers</button>
          <button data-act="csv">${icon('download')} Download these as CSV</button>
        </div>
      </div>
    </div>
    <div class="view" data-view></div>
    <div class="statusbar" data-status></div>`;

  $('[data-q]', main).addEventListener('input', debounce((e) => {
    view.q = e.target.value;
    refresh({ top: true });
  }, 120));
  renderView();
  refresh({ fit: true });
}

function renderTiles() {
  const all = view.sheet === 'businesses' ? view.all : prepare(view.data.businesses);
  const n = all.length;
  const count = (test) => all.filter(test).length;
  const leads = count((r) => r._kind !== 'own');
  const none = count((r) => r._kind === 'none');
  const withEmail = count((r) => r.Email);
  const checked = all.some((r) => r['Has website'] === 'Yes' && r['Website status']);
  const ratings = all.map((r) => r.Rating).filter((v) => typeof v === 'number');
  const avg = ratings.length ? ratings.reduce((a, b) => a + b, 0) / ratings.length : null;
  const tile = (quick, label, value, sub) =>
    `<button class="tile${view.sheet === 'businesses' && quick !== 'all' && view.quick === quick ? ' is-on' : ''}" data-quick="${quick}" aria-pressed="${view.quick === quick}">
      <span class="tile-label">${label}</span><span class="tile-value">${value}</span><span class="tile-sub">${sub}</span>
    </button>`;
  const tiles = [
    tile('all', 'Businesses found', fmt.format(n), view.data.others ? `+ ${fmt.format(view.data.others)} other results` : 'in this search'),
    tile('leads', 'Need a website', `${share(leads, n)}%`, many(leads, 'business', 'businesses')),
    tile('none', 'No website at all', `${share(none, n)}%`, many(none, 'business', 'businesses')),
    tile('email', 'Have an email', checked ? `${share(withEmail, n)}%` : '–', checked ? many(withEmail, 'business', 'businesses') : 'websites not checked'),
  ];
  const called = count((r) => r['Call status']);
  if (called) {
    const keen = count((r) => ['Interested', 'Somewhat interested', 'Client'].includes(r['Call status']));
    tiles.push(`<div class="tile"><span class="tile-label">Called</span><span class="tile-value">${fmt.format(called)}</span><span class="tile-sub">${fmt.format(keen)} interested or clients</span></div>`);
  }
  if (avg != null) {
    tiles.push(`<div class="tile"><span class="tile-label">Average Google rating</span><span class="tile-value">${avg.toFixed(1)}</span><span class="tile-sub">from ${fmt.format(ratings.length)} rated</span></div>`);
  }
  $('[data-tiles]', main).innerHTML = tiles.join('');
}

function renderChips() {
  $('[data-chips]', main).innerHTML = QUICK.map((f) => {
    const n = view.all.filter(f.test).length;
    if (!n && f.id !== 'all' && view.quick !== f.id) return '';
    return `<button class="chip" data-quick="${f.id}" aria-pressed="${view.quick === f.id}" ${f.title ? `title="${esc(f.title)}"` : ''}>
      ${f.dot ? `<span class="dot ${f.dot}"></span>` : ''}${esc(f.label)} <span class="count">${fmt.format(n)}</span>
    </button>`;
  }).join('');
}

function renderCallSelect() {
  const el = $('[data-call]', main);
  if (!el) return;
  el.innerHTML = CALL_FILTERS.map(([id, label]) => {
    const n = view.all.filter(callFilter(id)).length;
    if (!n && !['any', 'todo', 'called'].includes(id) && view.call !== id) return '';
    return `<option value="${id}" ${view.call === id ? 'selected' : ''}>${esc(label)}${id === 'any' ? '' : ` (${fmt.format(n)})`}</option>`;
  }).join('');
}

function renderStatus() {
  const n = view.rows.length;
  const total = view.all.length;
  const sort = view.sort ? ` · sorted by ${view.sort.key} ${view.sort.dir === 'asc' ? '↑' : '↓'}` : '';
  const what = view.sheet === 'others' ? ['other result', 'other results'] : ['business', 'businesses'];
  const tip =
    view.tab === 'table'
      ? 'Click a row for details. Drag a column edge to resize it.'
      : view.tab === 'map'
        ? 'Click a dot for details.'
        : '';
  $('[data-status]', main).innerHTML = `<span>${
    n === total ? many(total, ...what) : `Showing ${fmt.format(n)} of ${many(total, ...what)}`
  }${sort}</span><span>${tip}</span>`;
}

function renderView() {
  destroyMap();
  $$('[data-tab]', main).forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === view.tab)));
  $('[data-tools]', main).hidden = view.tab === 'summary';
  const el = $('[data-view]', main);
  if (view.tab === 'table') {
    el.innerHTML = `<div class="grid" tabindex="0"><div class="grid-head"></div><div class="grid-body"></div></div>`;
    const grid = $('.grid', el);
    grid.addEventListener('scroll', () => requestAnimationFrame(() => paintRows()));
    renderHead();
  } else if (view.tab === 'map') {
    el.innerHTML = `<div class="map" id="map"></div><div class="legend" data-legend></div><div class="map-note" data-map-note hidden></div>`;
    createMap();
  } else {
    el.innerHTML = `<div class="summary" data-summary></div>`;
  }
}

function refresh({ head = false, top = false, fit = false, drawer = true } = {}) {
  if (!$('[data-view]', main)) return; // not showing a result
  applyFilters();
  renderTiles();
  renderChips();
  renderCallSelect();
  renderStatus();
  if (view.tab === 'table') {
    if (head) renderHead();
    const grid = $('.grid', main);
    if (grid && top) grid.scrollTop = 0;
    paintRows(true);
  } else if (view.tab === 'map') {
    paintMap(fit);
  } else {
    renderSummary();
  }
  if (!$('.drawer').hidden) {
    if (drawer) renderDrawer();
    else updateDrawerNav();
  }
}

// ---------- Spreadsheet grid ----------

let painted = { first: -1, last: -1 };

function setTemplate() {
  const grid = $('.grid', main);
  if (!grid) return;
  const widths = [RN_W, ...view.columns.map(colWidth)];
  grid.style.setProperty('--grid-cols', widths.map((w) => `${w}px`).join(' '));
  grid.style.setProperty('--grid-w', `${widths.reduce((a, b) => a + b, 0)}px`);
}

function renderHead() {
  const grid = $('.grid', main);
  if (!grid) return;
  setTemplate();
  const head = $('.grid-head', grid);
  const cells = view.columns.map((key) => {
    const c = COLUMNS[key] || {};
    const sorted = view.sort?.key === key ? view.sort.dir : null;
    const sticky = key === 'Name';
    return `<div class="gc${c.num ? ' is-num' : ''}${sticky ? ' is-sticky is-edge' : ''}" ${sticky ? `style="left:${RN_W}px"` : ''} role="columnheader" aria-sort="${sorted ? (sorted === 'asc' ? 'ascending' : 'descending') : 'none'}">
      <button class="hc-sort" data-sort="${esc(key)}" title="Sort by ${esc(key)}"><span>${esc(key)}</span><b class="sort-ind">${sorted === 'asc' ? '▲' : sorted === 'desc' ? '▼' : ''}</b></button>
      <span class="hc-resize" data-resize="${esc(key)}" aria-hidden="true"></span>
    </div>`;
  });
  let html = `<div class="gr" role="row"><div class="gc rn is-sticky" style="left:0"></div>${cells.join('')}</div>`;
  if (view.showFilters) {
    const lists = [];
    const inputs = view.columns.map((key, i) => {
      const values = [...new Set(view.all.map((r) => String(r[key] ?? '')).filter(Boolean))];
      const list = values.length && values.length <= 40 ? `dl-${i}` : '';
      if (list) lists.push(`<datalist id="${list}">${values.sort().map((v) => `<option value="${esc(v)}">`).join('')}</datalist>`);
      const sticky = key === 'Name';
      return `<div class="gc${sticky ? ' is-sticky is-edge' : ''}" ${sticky ? `style="left:${RN_W}px"` : ''}>
        <input data-filter="${esc(key)}" ${list ? `list="${list}"` : ''} value="${esc(view.filters[key] || '')}" placeholder="Filter" aria-label="Filter ${esc(key)}" />
      </div>`;
    });
    html += `<div class="gr filter-row" role="row"><div class="gc rn is-sticky" style="left:0"></div>${inputs.join('')}</div>${lists.join('')}`;
  }
  head.innerHTML = html;
}

function paintRows(force = false) {
  const grid = $('.grid', main);
  if (!grid) return;
  const body = $('.grid-body', grid);
  body.style.height = `${view.rows.length * ROW_H}px`;
  if (!view.rows.length) {
    body.innerHTML = `<div class="grid-empty">Nothing matches these filters.</div>`;
    body.style.height = 'auto';
    painted = { first: -1, last: -1 };
    return;
  }
  const headH = $('.grid-head', grid).offsetHeight;
  const top = Math.max(0, grid.scrollTop - headH);
  const first = Math.max(0, Math.floor(top / ROW_H) - 10);
  const last = Math.min(view.rows.length, Math.ceil((top + grid.clientHeight) / ROW_H) + 10);
  if (!force && first === painted.first && last === painted.last) return;
  painted = { first, last };
  let html = '';
  for (let i = first; i < last; i++) {
    const r = view.rows[i];
    html += `<div class="gr${i % 2 ? ' is-alt' : ''}${r === view.selected ? ' is-selected' : ''}" style="top:${i * ROW_H}px" data-row="${i}" role="row">`;
    html += `<div class="gc rn is-sticky" style="left:0">${i + 1}</div>`;
    for (const key of view.columns) {
      const c = COLUMNS[key] || {};
      const plain = !c.kind;
      const sticky = key === 'Name';
      html += `<div class="gc${c.num ? ' is-num' : ''}${sticky ? ' name is-sticky is-edge' : ''}"${sticky ? ` style="left:${RN_W}px"` : ''}${plain && r[key] ? ` title="${esc(r[key])}"` : ''}>${cellHtml(r, key)}</div>`;
    }
    html += '</div>';
  }
  body.innerHTML = html;
}

function sortBy(key) {
  const s = view.sort;
  const numeric = COLUMNS[key]?.num || COLUMNS[key]?.kind === 'date' || key === 'Social media';
  const firstDir = numeric ? 'desc' : 'asc'; // biggest ratings first, names A to Z
  if (!s || s.key !== key) view.sort = { key, dir: firstDir };
  else if (s.dir === firstDir) view.sort = { key, dir: firstDir === 'asc' ? 'desc' : 'asc' };
  else view.sort = null;
  refresh({ head: true });
}

function startResize(handle, e) {
  e.preventDefault();
  const key = handle.dataset.resize;
  const startX = e.clientX;
  const startW = colWidth(key);
  handle.setPointerCapture(e.pointerId);
  handle.classList.add('is-dragging');
  const move = (ev) => {
    prefs.widths[key] = Math.max(60, Math.round(startW + ev.clientX - startX));
    setTemplate();
  };
  const up = () => {
    handle.removeEventListener('pointermove', move);
    handle.classList.remove('is-dragging');
    store.set('widths', prefs.widths);
  };
  handle.addEventListener('pointermove', move);
  handle.addEventListener('pointerup', up, { once: true });
  handle.addEventListener('pointercancel', up, { once: true });
}

function renderColumnsPopover() {
  const pop = $('[data-pop="columns"]', main);
  pop.innerHTML =
    view.available
      .map(
        (k) =>
          `<label><input type="checkbox" data-col="${esc(k)}" ${view.columns.includes(k) ? 'checked' : ''} ${k === 'Name' ? 'disabled' : ''} /> ${esc(k)}</label>`,
      )
      .join('') +
    `<div class="popover-foot"><button class="btn btn-sm btn-quiet" data-act="cols-reset">Reset columns</button></div>`;
}

// ---------- Map ----------

let map = null;
let markers = null;

function createMap() {
  if (typeof L === 'undefined') {
    $('#map').innerHTML = `<div class="empty">The map couldn't load.</div>`;
    return;
  }
  map = L.map('map', { preferCanvas: true, worldCopyJump: true });
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);
  markers = L.layerGroup().addTo(map);
  map.setView([41.7151, 44.8271], 12); // Tbilisi until the results are placed
  $('#map').addEventListener('click', (e) => {
    const b = e.target.closest('[data-open]');
    if (b) openDrawer(view.all[+b.dataset.open]);
  });
}

function destroyMap() {
  if (map) {
    map.remove();
    map = null;
    markers = null;
  }
}

function paintMap(fit) {
  if (!map) return;
  requestAnimationFrame(() => map && map.invalidateSize());
  markers.clearLayers();
  const style = getComputedStyle(document.documentElement);
  const colors = Object.fromEntries(Object.keys(KINDS).map((k) => [k, style.getPropertyValue(`--m-${k}`).trim()]));
  const order = { own: 0, broken: 1, social: 2, none: 3 }; // businesses without a website on top
  const placed = view.rows
    .filter((r) => Number.isFinite(parseFloat(r.Latitude)) && Number.isFinite(parseFloat(r.Longitude)))
    .sort((a, b) => order[a._kind] - order[b._kind]);
  const points = [];
  for (const r of placed) {
    const at = [parseFloat(r.Latitude), parseFloat(r.Longitude)];
    points.push(at);
    L.circleMarker(at, {
      radius: r._kind === 'own' ? 5 : 7,
      color: '#ffffff',
      weight: 1.5,
      fillColor: colors[r._kind],
      fillOpacity: 0.95,
    })
      .bindTooltip(esc(r.Name), { direction: 'top', offset: [0, -6] })
      .bindPopup(() => popupHtml(r), { maxWidth: 280 })
      .addTo(markers);
  }
  if (fit && points.length) map.fitBounds(points, { padding: [40, 40], maxZoom: 15 });

  const counts = Object.fromEntries(Object.keys(KINDS).map((k) => [k, placed.filter((r) => r._kind === k).length]));
  $('[data-legend]', main).innerHTML =
    `<span class="legend-title">Web presence</span>` +
    Object.entries(KINDS)
      .filter(([k]) => counts[k])
      .map(([k, label]) => `<span class="legend-item"><span class="dot ${k}"></span>${label}<span class="count">${fmt.format(counts[k])}</span></span>`)
      .join('');
  const missing = view.rows.length - placed.length;
  const note = $('[data-map-note]', main);
  note.hidden = !missing;
  note.textContent = `${fmt.format(missing)} of these have no location, so they aren't on the map.`;
}

function popupHtml(r) {
  const site = r._kind === 'own' || r._kind === 'broken' ? ext(r.Website, esc(shortUrl(r.Website))) : esc(KINDS[r._kind]);
  return `<div class="pop">
    <div class="pop-name">${esc(r.Name)}</div>
    <div class="pop-meta">${esc([r.Category, r.Rating ? `★ ${Number(r.Rating).toFixed(1)}` : ''].filter(Boolean).join(' · '))}</div>
    ${r.Phone ? `<div>${esc(r.Phone)}</div>` : ''}
    <div>${site}</div>
    ${r['Call status'] ? `<div>Call: <b>${esc(r['Call status'])}</b></div>` : ''}
    <button type="button" data-open="${r._i}">Details</button>
  </div>`;
}

// ---------- Summary ----------

function renderSummary() {
  const all = view.all;
  const n = all.length;
  const count = (test, group = all) => group.filter(test).length;
  const bars = (rows, of, dots = false) =>
    `<div class="bars">${rows
      .map(([label, value, kind]) => {
        const s = share(value, of);
        return `<div class="bar-row${value ? '' : ' is-dim'}" title="${esc(label)}: ${fmt.format(value)} (${s}%)">
          <span class="bar-label">${dots && kind ? `<span class="dot ${kind}"></span>` : ''}<span>${esc(label)}</span></span>
          <span class="bar-value"><b>${fmt.format(value)}</b> · ${s}%</span>
          <span class="bar-track"><i style="width:${s}%;${dots && kind ? `background:var(--m-${kind})` : ''}"></i></span>
        </div>`;
      })
      .join('')}</div>`;
  const card = (title, hint, body) =>
    `<section class="card"><h3>${esc(title)}</h3>${hint ? `<p class="hint">${esc(hint)}</p>` : ''}${body}</section>`;

  const cards = [];
  cards.push(
    card(
      'Web presence',
      `All ${view.sheet === 'others' ? many(n, 'other result', 'other results') : many(n, 'business', 'businesses')}`,
      bars(Object.entries(KINDS).map(([k, label]) => [label, count((r) => r._kind === k), k]), n, true),
    ),
  );

  const called = all.filter((r) => r['Call status']);
  if (called.length) {
    cards.push(
      card(
        'Your calls',
        `${many(called.length, 'business', 'businesses')} called so far`,
        bars(
          Object.keys(CALL_STATUSES).map((s) => [s, called.filter((r) => r['Call status'] === s).length]),
          called.length,
        ),
      ),
    );
  }

  const own = all.filter((r) => r['Has website'] === 'Yes');
  if (own.some((r) => r['Website status'])) {
    const works = count((r) => ['OK', 'SSL certificate problem'].includes(r['Website status']), own);
    const broken = count((r) => r._kind === 'broken', own);
    cards.push(
      card(
        'Their own websites',
        `${many(own.length, 'business has', 'businesses have')} one`,
        bars(
          [
            ['Works', works],
            ['Broken or expired', broken],
            ["Couldn't check (blocked, slow…)", own.length - works - broken],
          ],
          own.length,
        ),
      ),
    );
  }

  const contact = [
    ['Phone number', count((r) => r.Phone || r['Intl. phone'])],
    ['Own website', own.length],
    ['Email', count((r) => r.Email)],
    ['Social media', count((r) => r._social.length)],
  ];
  if (all.some((r) => typeof r.Rating === 'number')) contact.push(['Google rating', count((r) => typeof r.Rating === 'number')]);
  cards.push(card('Contact details', 'How many businesses have each', bars(contact.sort((a, b) => b[1] - a[1]), n)));

  const socials = SOCIAL.map(([name]) => [name, count((r) => r[name])]).filter(([, v]) => v);
  if (socials.length) cards.push(card('Social media', 'Linked from their websites', bars(socials.sort((a, b) => b[1] - a[1]), n)));

  const categories = new Map();
  for (const r of all) categories.set(r.Category || '(no category)', (categories.get(r.Category || '(no category)') || 0) + 1);
  const top = [...categories].sort((a, b) => b[1] - a[1]);
  const shown = top.slice(0, 8);
  const rest = top.slice(8).reduce((a, [, v]) => a + v, 0);
  if (rest) shown.push([`${top.length - 8} other categories`, rest]);
  cards.push(card('Categories', '', bars(shown, n)));

  const queries = [...new Set(all.flatMap((r) => String(r.Search || '').split(', ').filter(Boolean)))];
  if (queries.length > 1) {
    cards.push(
      card(
        'By search word',
        'A business found by several words counts for each',
        bars(queries.map((q) => [q, count((r) => String(r.Search).split(', ').includes(q))]), n),
      ),
    );
  }

  const ratings = all.map((r) => r.Rating).filter((v) => typeof v === 'number');
  if (ratings.length) {
    const reviews = all.map((r) => r.Reviews).filter((v) => typeof v === 'number').sort((a, b) => a - b);
    const median = reviews.length ? reviews[Math.floor(reviews.length / 2)] : 0;
    cards.push(
      card(
        'Ratings',
        `${many(ratings.length, 'business has', 'businesses have')} a Google rating`,
        bars(
          [
            ['4.5 stars or more', ratings.filter((v) => v >= 4.5).length],
            ['4 to 4.4', ratings.filter((v) => v >= 4 && v < 4.5).length],
            ['Under 4', ratings.filter((v) => v < 4).length],
          ],
          ratings.length,
        ) + `<p class="hint" style="margin:12px 0 0">Half of them have more than ${fmt.format(median)} reviews.</p>`,
      ),
    );
  }

  $('[data-summary]', main).innerHTML = `<div class="summary-grid">${cards.join('')}</div>`;
}

// ---------- Details drawer ----------

function openDrawer(row) {
  if (!row) return;
  flushCallNote();
  view.selected = row;
  view.selIndex = view.rows.indexOf(row);
  $('.drawer').hidden = false;
  renderDrawer();
  paintRows(true);
  scrollToSelected();
}

function closeDrawer() {
  flushCallNote();
  $('.drawer').hidden = true;
  if (view.selected) {
    view.selected = null;
    paintRows(true);
  }
}

function scrollToSelected() {
  const grid = $('.grid', main);
  const i = view.rows.indexOf(view.selected);
  if (!grid || i < 0) return;
  const headH = $('.grid-head', grid).offsetHeight;
  const top = i * ROW_H;
  const visible = grid.clientHeight - headH;
  if (top < grid.scrollTop) grid.scrollTop = top;
  else if (top + ROW_H > grid.scrollTop + visible) grid.scrollTop = top + ROW_H - visible;
}

function moveSelection(step) {
  let i = view.rows.indexOf(view.selected);
  // Marking a call can hide the row (e.g. under "Not called yet"); the next one moved into its place.
  if (i < 0) i = step > 0 ? view.selIndex - 1 : view.selIndex;
  const next = view.rows[i + step];
  if (next) openDrawer(next);
}

function navHtml() {
  const i = view.rows.indexOf(view.selected);
  const n = view.rows.length;
  const prev = i >= 0 ? i > 0 : view.selIndex > 0;
  const next = i >= 0 ? i < n - 1 : view.selIndex < n;
  return `<button class="btn btn-quiet btn-icon btn-sm" data-act="prev" aria-label="Previous business" ${prev ? '' : 'disabled'}>${icon('up')}</button>
    <button class="btn btn-quiet btn-icon btn-sm" data-act="next" aria-label="Next business" ${next ? '' : 'disabled'}>${icon('down')}</button>
    <span>${i >= 0 ? `${fmt.format(i + 1)} of ${fmt.format(n)}` : 'Now hidden by your filters'}</span>`;
}

function updateDrawerNav() {
  const nav = $('.drawer .drawer-nav');
  if (nav) nav.innerHTML = navHtml();
}

function renderDrawer() {
  const r = view.selected;
  if (!r) return;
  const fact = (label, value, copyValue) =>
    value
      ? `<div class="fact"><dt>${esc(label)}</dt><dd>${value}</dd>${
          copyValue ? `<button class="copy" data-copy="${esc(copyValue)}" aria-label="Copy ${esc(label)}" title="Copy">${icon('copy')}</button>` : '<span></span>'
        }</div>`
      : '';
  const tel = (p) => `<a href="tel:${esc(String(p).replace(/[^\d+]/g, ''))}">${esc(p)}</a>`;
  const mails = emails(r);
  const pills = [
    r['Has website'] ? pill(r['Has website'] === 'Yes' ? 'Has a website' : r['Has website'], presenceTone(r['Has website'])) : '',
    r['Website status'] ? pill(r['Website status'], statusTone(String(r['Website status']))) : '',
    r['Business status'] && r['Business status'] !== 'Open' ? businessPill(String(r['Business status'])) : '',
    typeof r.Rating === 'number'
      ? pill(`★ ${r.Rating.toFixed(1)}${r.Reviews ? ` · ${fmt.format(r.Reviews)} reviews` : ''}`)
      : '',
  ].join('');
  const site = r.Website ? ext(r.Website, esc(shortUrl(r.Website))) : '';
  const socials = r._social.map((s) => fact(s.name, ext(s.url, esc(shortUrl(s.url))), s.url)).join('');
  const coords = r.Latitude && r.Longitude ? `${Number(r.Latitude).toFixed(5)}, ${Number(r.Longitude).toFixed(5)}` : '';

  $('.drawer').innerHTML = `
    <div class="drawer-top">
      <div class="drawer-nav">${navHtml()}</div>
      <button class="btn btn-quiet btn-icon" data-act="close" aria-label="Close details">${icon('close')}</button>
    </div>
    <div class="drawer-body">
      <div>
        <h2>${esc(r.Name)}</h2>
        <p class="drawer-sub">${esc(r.Category || '')}</p>
        <div class="pills">${pills}</div>
      </div>
      <div class="drawer-actions">
        ${r.Phone || r['Intl. phone'] ? `<a class="btn btn-sm" href="tel:${esc(String(r['Intl. phone'] || r.Phone).replace(/[^\d+]/g, ''))}">${icon('phone')} Call</a>` : ''}
        ${mails.length ? `<a class="btn btn-sm" href="mailto:${esc(mails[0])}">${icon('mail')} Email</a>` : ''}
        ${safeUrl(r.Website) ? ext(r.Website, `${icon('globe')} Website`, 'btn btn-sm') : ''}
        ${safeUrl(r['Google Maps']) ? ext(r['Google Maps'], `${icon('pin')} Google Maps`, 'btn btn-sm') : ''}
      </div>
      ${callFormHtml(r)}
      <section class="section">
        <h3>Contact</h3>
        <dl class="facts">
          ${fact('Phone', r.Phone ? tel(r.Phone) : '', r.Phone)}
          ${fact('Intl. phone', r['Intl. phone'] && r['Intl. phone'] !== r.Phone ? tel(r['Intl. phone']) : '', r['Intl. phone'])}
          ${mails.map((m, k) => fact(k ? 'Other email' : 'Email', `<a href="mailto:${esc(m)}">${esc(m)}</a>`, m)).join('')}
          ${fact('Website', site, r.Website)}
          ${!r.Phone && !mails.length && !site ? '<p class="muted">No contact details found.</p>' : ''}
        </dl>
      </section>
      ${socials ? `<section class="section"><h3>Social media</h3><dl class="facts">${socials}</dl></section>` : ''}
      <section class="section">
        <h3>Location</h3>
        <dl class="facts">
          ${fact('Address', esc(r.Address), r.Address)}
          ${fact('Coordinates', esc(coords), coords)}
        </dl>
      </section>
      <section class="section">
        <h3>From the search</h3>
        <dl class="facts">
          ${fact('Found by', esc(r.Search))}
          ${fact('Place types', esc(r['Google types']))}
          ${fact('Place ID', `<span class="muted">${esc(r['Place ID'])}</span>`, r['Place ID'])}
        </dl>
      </section>
    </div>`;
}

// ---------- Call notes ----------

function callFormHtml(r) {
  const c = { ...r._call };
  if (pendingNote?.r === r) c[pendingNote.field] = pendingNote.value; // typed but not saved yet
  const options = ['', ...Object.keys(CALL_STATUSES)]
    .map(
      (s) =>
        `<button type="button" class="call-opt ${s ? CALL_STATUSES[s] : ''}" data-status="${esc(s)}" aria-pressed="${(c.status || '') === s}"${CALL_HINTS[s] ? ` title="${esc(CALL_HINTS[s])}"` : ''}>${s || 'Not called'}</button>`,
    )
    .join('');
  return `<section class="section call-box" data-call-key="${esc(callKey(r))}">
    <h3>Your call</h3>
    <div class="call-opts" role="group" aria-label="How the call went">${options}</div>
    <label class="call-field">
      <span>Their response</span>
      <textarea data-field="response" rows="3" placeholder="What did they say? E.g. already has a website, wants prices, call after 6 pm…">${esc(c.response || '')}</textarea>
    </label>
    <label class="call-field">
      <span>How could I improve?</span>
      <textarea data-field="improve" rows="2" placeholder="What to say or do better next time">${esc(c.improve || '')}</textarea>
    </label>
    <p class="call-meta"><span data-call-meta>${callMetaText(c)}</span><span data-call-state></span></p>
  </section>`;
}

function callMetaText(c) {
  const history = c.history || [];
  if (!history.length) return 'Not called yet. Pick how the call went to log it.';
  return history.map((h) => `${esc(niceDate(h.at))}: ${esc(h.status)}`).join(' · ');
}

// Typing is saved shortly after you stop, and right away when you leave the box or the business.
let pendingNote = null;

function queueCallNote(r, field, value) {
  if (pendingNote && (pendingNote.r !== r || pendingNote.field !== field)) flushCallNote();
  clearTimeout(pendingNote?.timer);
  pendingNote = { r, field, value, timer: setTimeout(flushCallNote, 600) };
  setCallState(callKey(r), 'Typing…');
}

function flushCallNote() {
  if (!pendingNote) return;
  const { r, field, value, timer } = pendingNote;
  clearTimeout(timer);
  pendingNote = null;
  saveCall(r, { [field]: value });
}

// Changes the app hasn't confirmed yet are kept in this browser, so nothing typed is lost
// when a save fails (e.g. while the app restarts) or the page reloads. They're sent again
// until they get through.
const CALL_FIELDS = ['status', 'response', 'improve'];
let unsaved = store.get('unsaved-calls', {});
let retryTimer = null;

function unsavedFields(key) {
  const u = unsaved[key] || {};
  return Object.fromEntries(CALL_FIELDS.filter((f) => f in u).map((f) => [f, u[f]]));
}

// One save at a time, in order, so an older version of a note never lands after a newer one.
let saving = Promise.resolve();

function saveCall(r, changes) {
  const key = callKey(r);
  unsaved[key] = {
    ...unsaved[key],
    ...changes,
    name: r.Name,
    phone: r.Phone || r['Intl. phone'] || '',
    search: view.data?.title || '',
  };
  store.set('unsaved-calls', unsaved);
  view.all.forEach((row) => callKey(row) === key && applyCall(row)); // show it right away
  refresh({ drawer: false });
  saving = saving.then(() => sendCall(key, changes));
  return saving;
}

function retryUnsaved() {
  clearTimeout(retryTimer);
  for (const key of Object.keys(unsaved)) {
    const changes = unsavedFields(key);
    if (Object.keys(changes).length) saving = saving.then(() => sendCall(key, changes));
    else delete unsaved[key];
  }
  store.set('unsaved-calls', unsaved);
}

async function sendCall(key, changes) {
  const { name, phone, search } = unsaved[key] || {};
  setCallState(key, 'Saving…');
  try {
    const { call } = await api('/api/calls', { key, ...changes, name, phone, search });
    // Forget what got through, unless it was changed again meanwhile.
    const left = unsaved[key];
    if (left) {
      for (const [field, value] of Object.entries(changes)) if (left[field] === value) delete left[field];
      if (!CALL_FIELDS.some((f) => f in left)) delete unsaved[key];
      store.set('unsaved-calls', unsaved);
    }
    if (call) state.calls[key] = call;
    else delete state.calls[key];
    view.all.forEach((row) => callKey(row) === key && applyCall(row));
    setCallState(key, 'Saved');
    const meta = $(`.drawer [data-call-key="${CSS.escape(key)}"] [data-call-meta]`);
    if (meta) meta.innerHTML = callMetaText(state.calls[key] || {});
    refresh({ drawer: false });
  } catch (err) {
    setCallState(key, `Not saved yet, will retry. ${err.message}`, true);
    clearTimeout(retryTimer);
    retryTimer = setTimeout(retryUnsaved, 5000);
    loadSetup().catch(() => {}); // shows the restart message if that's the reason
  }
}

function setCallState(key, text, bad = false) {
  const el = $(`.drawer [data-call-key="${CSS.escape(key)}"] [data-call-state]`);
  if (!el) return;
  el.textContent = text;
  el.classList.toggle('is-bad', bad);
}

// ---------- Export ----------

function downloadCsv() {
  const sheet = view.data[view.sheet === 'others' ? 'otherResults' : 'businesses'];
  const columns = [...sheet.columns, ...CALL_COLUMNS];
  const cell = (v) => {
    const s = String(v ?? '');
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [columns.map(cell).join(','), ...view.rows.map((r) => columns.map((c) => cell(r[c])).join(','))];
  // A BOM so Excel shows Georgian letters correctly.
  const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  const stem = view.data.file.replace(/\.xlsx$/i, '');
  a.download = `${stem}${view.quick === 'all' ? '' : `_${view.quick}`}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  toast(`Downloaded ${many(view.rows.length, 'row', 'rows')}`);
}

// ---------- Events ----------

function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

function closePopovers(except) {
  $$('[data-pop], [data-menu]', main).forEach((p) => {
    if (p !== except) p.hidden = true;
  });
}

main.addEventListener('click', async (e) => {
  const t = e.target;
  const quick = t.closest('[data-quick]');
  if (quick) {
    if (view.sheet !== 'businesses' && quick.classList.contains('tile')) {
      openSheet('businesses');
      renderResult();
    }
    view.quick = quick.dataset.quick === view.quick && quick.classList.contains('tile') ? 'all' : quick.dataset.quick;
    refresh({ top: true, fit: true });
    return;
  }
  const tab = t.closest('[data-tab]');
  if (tab) {
    view.tab = tab.dataset.tab;
    store.set('tab', view.tab);
    renderView();
    refresh({ fit: true });
    return;
  }
  const sheet = t.closest('[data-sheet]');
  if (sheet && sheet.dataset.sheet !== view.sheet) {
    openSheet(sheet.dataset.sheet);
    view.quick = 'all';
    view.call = 'any';
    view.filters = {};
    view.sort = null;
    renderResult();
    return;
  }
  const sort = t.closest('[data-sort]');
  if (sort) return sortBy(sort.dataset.sort);

  const row = t.closest('.grid-body .gr');
  if (row && !t.closest('a')) return openDrawer(view.rows[+row.dataset.row]);

  const act = t.closest('[data-act]')?.dataset.act;
  if (!act) {
    if (!t.closest('.popover, .menu')) closePopovers();
    return;
  }
  const d = view.data;
  if (act === 'menu' || act === 'columns' || act === 'export') {
    const pop = act === 'menu' ? $('[data-menu]', main) : $(`[data-pop="${act}"]`, main);
    if (act === 'columns') renderColumnsPopover();
    closePopovers(pop);
    pop.hidden = !pop.hidden;
    return;
  }
  closePopovers();
  if (act === 'filters') {
    view.showFilters = !view.showFilters;
    if (!view.showFilters) view.filters = {};
    t.closest('[data-act]').setAttribute('aria-pressed', String(view.showFilters));
    if (view.tab !== 'table') {
      view.tab = 'table';
      renderView();
    }
    refresh({ head: true });
    if (view.showFilters) $('.filter-row input', main)?.focus();
  } else if (act === 'reveal') {
    api('/api/reveal', { file: d.file }).catch((err) => toast(err.message));
  } else if (act === 'again') {
    const [what, where] = splitTitle(d.title);
    state.prefill = { queries: what.split(', '), location: where };
    location.hash = '#new';
  } else if (act === 'trash') {
    if (!confirm(`Move “${d.title}” to the Trash?\n\nYou can get it back from the Trash in Finder.`)) return;
    try {
      await api('/api/trash', { file: d.file });
      state.cache.delete(d.file);
      await loadSaved();
      toast('Moved to the Trash');
      location.hash = '';
    } catch (err) {
      toast(err.message);
    }
  } else if (act === 'copy-emails') {
    const list = [...new Set(view.rows.flatMap(emails))];
    if (!list.length) return toast('None of these have an email.');
    copy(list.join('\n'), `Copied ${fmt.format(list.length)} emails`);
  } else if (act === 'copy-phones') {
    const list = [...new Set(view.rows.map((r) => r.Phone || r['Intl. phone']).filter(Boolean))];
    if (!list.length) return toast('None of these have a phone number.');
    copy(list.join('\n'), `Copied ${fmt.format(list.length)} phone numbers`);
  } else if (act === 'csv') {
    downloadCsv();
  } else if (act === 'cols-reset') {
    prefs.hidden = {};
    prefs.widths = {};
    store.set('hidden', {});
    store.set('widths', {});
    pickColumns();
    renderColumnsPopover();
    refresh({ head: true });
  }
});

main.addEventListener('change', (e) => {
  if (e.target.matches('[data-call]')) {
    view.call = e.target.value;
    refresh({ top: true, fit: true });
    return;
  }
  const col = e.target.closest('[data-col]');
  if (!col) return;
  prefs.hidden[col.dataset.col] = !col.checked;
  store.set('hidden', prefs.hidden);
  pickColumns();
  if (view.tab === 'table') refresh({ head: true });
});

main.addEventListener(
  'input',
  debounce((e) => {
    const f = e.target.closest('[data-filter]');
    if (!f) return;
    view.filters[f.dataset.filter] = f.value;
    applyFilters();
    renderStatus();
    paintRows(true);
  }, 150),
);

main.addEventListener('pointerdown', (e) => {
  const handle = e.target.closest('[data-resize]');
  if (handle) startResize(handle, e);
});

$('.drawer').addEventListener('click', (e) => {
  const status = e.target.closest('[data-status]');
  if (status && view.selected) {
    $$('.drawer [data-status]').forEach((b) => b.setAttribute('aria-pressed', String(b === status)));
    saveCall(view.selected, { status: status.dataset.status });
    return;
  }
  const act = e.target.closest('[data-act]')?.dataset.act;
  if (act === 'close') closeDrawer();
  else if (act === 'prev') moveSelection(-1);
  else if (act === 'next') moveSelection(1);
  const c = e.target.closest('[data-copy]');
  if (c) copy(c.dataset.copy, 'Copied');
});

$('.drawer').addEventListener('input', (e) => {
  const field = e.target.closest('[data-field]');
  if (field && view.selected) queueCallNote(view.selected, field.dataset.field, field.value);
});
$('.drawer').addEventListener('change', (e) => {
  if (e.target.closest('[data-field]')) flushCallNote();
});
window.addEventListener('pagehide', flushCallNote);
$('.banner').addEventListener('click', (e) => {
  if (!e.target.closest('[data-reload]')) return;
  flushCallNote();
  saving.then(() => location.reload());
});
// Notice updates (and an app that came back after a restart) without reloading.
window.addEventListener('focus', () => loadSetup().catch(() => {}));
setInterval(() => loadSetup().catch(() => {}), 30000);

document.addEventListener('keydown', (e) => {
  if (e.target.closest('input, select, textarea')) return;
  if (e.key === 'Escape') {
    if ($$('[data-pop]:not([hidden]), [data-menu]:not([hidden])', main).length) closePopovers();
    else if (!$('.drawer').hidden) closeDrawer();
  } else if (!$('.drawer').hidden && (e.key === 'ArrowDown' || e.key === 'j')) {
    e.preventDefault();
    moveSelection(1);
  } else if (!$('.drawer').hidden && (e.key === 'ArrowUp' || e.key === 'k')) {
    e.preventDefault();
    moveSelection(-1);
  } else if (e.key === '/' && $('[data-q]', main)) {
    e.preventDefault();
    $('[data-q]', main).focus();
  }
});

$('.side-filter').addEventListener('input', renderSaved);
window.addEventListener('resize', debounce(() => paintRows(true), 100));
window.addEventListener('hashchange', route);

// ---------- Start ----------

(async function start() {
  try {
    await Promise.all([loadSetup(), loadSaved(), loadCalls()]);
    state.started = true; // notes loaded: safe to send any kept in this browser
    if (Object.keys(unsaved).length && state.setup.version && !state.setup.stale) retryUnsaved();
    const { job } = await api('/api/job');
    if (job) {
      state.job = { ...job, allLines: job.lines };
      if (job.state === 'running') pollJob();
    }
  } catch (err) {
    main.innerHTML = `<div class="empty"><p>${esc(err.message)}</p></div>`;
    return;
  }
  route();
})();
