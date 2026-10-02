#!/usr/bin/env python3
"""Project dashboard.

Every few minutes: read each configured GitHub account/org, pull repos,
their .project.toml stage file and recent commit activity, and render a
static dashboard page. Once a day per repo, also read its traffic (views,
clones, referrers, paths) and keep the daily counts in traffic.json, since
GitHub only keeps 14 days. Serves the page on PORT, plus one endpoint that
saves which repos are hidden.

Standard library only (Python 3.11+ for tomllib).
"""
import copy
import json
import logging
import os
import signal
import sys
import threading
import time
import tomllib
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

CONFIG_PATH = Path(os.environ.get("CONFIG", "/config/config.toml"))
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
SITE_DIR = DATA_DIR / "site"
STATE_FILE = DATA_DIR / "last-good.json"
TRAFFIC_FILE = DATA_DIR / "traffic.json"    # history beyond GitHub's 14 days: worth backing up
SETTINGS_FILE = DATA_DIR / "settings.json"  # choices made on the settings screen
TEMPLATE = Path(__file__).with_name("template.html")
PORT = int(os.environ.get("PORT", "8087"))

STAGE_FILE = ".project.toml"
STAGES = ["idea", "scoping", "design", "building", "testing", "live"]
RECENT_WEEKS = 12   # weekly commit counts fetched every refresh (overview sparkline)
YEAR_WEEKS = 52     # weekly commit counts on the detail page, cached (see fetch_years)
YEAR_REFRESH = timedelta(hours=24)
COMMITS = 15        # recent commits listed on the detail page
ISSUES = 20         # open issues listed on the detail page (the count is always exact)
PAGE_SIZE = 20      # repos per request; bigger pages risk GitHub's request timeout
RELEASES = 10       # newest releases whose asset downloads are counted
ASSETS = 20         # assets read per release
DEFAULT_API = "https://api.github.com/graphql"
TRAFFIC_REFRESH = timedelta(hours=24)  # traffic is daily data; read it once a day per repo
TRAFFIC_RETRY = timedelta(hours=1)     # after a network error or GitHub hiccup
TRAFFIC_DAYS = 14                      # how far back GitHub's traffic endpoints go

log = logging.getLogger("dashboard")


# Weekly commit counts come from one history(since, until) { totalCount } per week.
# Asking for counts instead of commit nodes avoids GitHub's 100-per-page cap, which
# silently truncated busy repos. Weeks start Monday 00:00 UTC, so a week's count can
# be cached under its start date and merged with fresher data later.

def week_var_decls(n):
    return ", ".join(f"$s{i}: GitTimestamp!, $u{i}: GitTimestamp!" for i in range(n))


def week_fields(n):
    return "\n".join(
        f"              w{i}: history(first: 0, since: $s{i}, until: $u{i}) {{ totalCount }}"
        for i in range(n)
    )


QUERY = """
query($owner: String!, $cursor: String, %s) {
  rateLimit { cost }
  repositoryOwner(login: $owner) {
    repositories(first: %d, after: $cursor, orderBy: {field: PUSHED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name nameWithOwner url description isPrivate isArchived isFork pushedAt
        stargazerCount forkCount watchers { totalCount }
        releases(first: %d, orderBy: {field: CREATED_AT, direction: DESC}) {
          totalCount
          nodes { name tagName url publishedAt isDraft releaseAssets(first: %d) { nodes { downloadCount } } }
        }
        stageFile: object(expression: "HEAD:.project.toml") { ... on Blob { text } }
        issues(states: OPEN, first: %d, orderBy: {field: CREATED_AT, direction: DESC}) {
          totalCount
          nodes { title url createdAt labels(first: 5) { nodes { name } } }
        }
        defaultBranchRef {
          target {
            ... on Commit {
              commits: history(first: %d) { nodes { messageHeadline committedDate url } }
%s
              stageHistory: history(first: 1, path: ".project.toml") { nodes { committedDate } }
            }
          }
        }
      }
    }
  }
}
""" % (week_var_decls(RECENT_WEEKS), PAGE_SIZE, RELEASES, ASSETS, ISSUES, COMMITS, week_fields(RECENT_WEEKS))

# One repo at a time: 52 counts for a whole page of repos in one request made
# GitHub time out (HTTP 502) during testing, while one repo takes about a second.
YEAR_QUERY = """
query($owner: String!, $name: String!, %s) {
  rateLimit { cost }
  repository(owner: $owner, name: $name) {
    defaultBranchRef {
      target {
        ... on Commit {
%s
        }
      }
    }
  }
}
""" % (week_var_decls(YEAR_WEEKS), week_fields(YEAR_WEEKS))


class SourceError(Exception):
    """A problem reading one account/org, phrased for the dashboard banner."""


class TrafficUnavailable(Exception):
    """The token may not read this repo's traffic (needs Administration: Read)."""


# ---------------------------------------------------------------- config

def load_config():
    with CONFIG_PATH.open("rb") as f:
        cfg = tomllib.load(f)
    if not cfg.get("sources"):
        raise SystemExit(f"{CONFIG_PATH}: add at least one [[sources]] entry")
    cfg.setdefault("refresh_minutes", 15)
    cfg.setdefault("stale_days", 30)
    flt = cfg.setdefault("filters", {})
    flt.setdefault("include_archived", False)
    flt.setdefault("include_forks", False)
    flt["exclude"] = {s.lower() for s in flt.get("exclude", [])}
    cfg.setdefault("traffic", {}).setdefault("include_private", False)
    return cfg


# ---------------------------------------------------------------- GitHub

def graphql(api_url, token, query, variables, key):
    """Run a query; `key` is the top-level field that must come back for the result to count."""
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(api_url, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "project-dashboard",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise SourceError("GitHub rejected the token. It may have expired or been revoked.")
        if e.code == 403:
            raise SourceError("GitHub refused the request (rate limit or missing permission).")
        if e.code in (502, 504):
            raise SourceError(f"GitHub timed out answering (HTTP {e.code}). It usually passes on the next refresh.")
        raise SourceError(f"GitHub returned HTTP {e.code}.")
    except (urllib.error.URLError, TimeoutError) as e:
        raise SourceError(f"Couldn't reach GitHub ({e}).")

    errors = payload.get("errors") or []
    for err in errors:
        log.warning("GraphQL: %s", err.get("message"))
    data = payload.get("data") or {}
    if errors and not data.get(key):
        raise SourceError(errors[0].get("message", "GraphQL error."))
    return data


def source_auth(src):
    token = os.environ.get(src.get("token_env", ""), "").strip()
    if not token:
        raise SourceError(f"No token set. Put it in the {src.get('token_env')} environment variable.")
    return src.get("api_url", DEFAULT_API), token


def rest_base(src):
    """REST API root for a source: api.github.com, or GHES's /api/v3 next to its /api/graphql."""
    if src.get("rest_url"):
        return src["rest_url"].rstrip("/")
    api = src.get("api_url", DEFAULT_API)
    if api == DEFAULT_API:
        return "https://api.github.com"
    return api.removesuffix("/graphql").removesuffix("/api") + "/api/v3"


def rest(url, token):
    """GET one REST endpoint. Raises TrafficUnavailable for 403/404, SourceError otherwise."""
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "project-dashboard",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        rate_limited = e.headers.get("x-ratelimit-remaining") == "0" or e.headers.get("retry-after")
        if e.code in (403, 404) and not rate_limited:
            raise TrafficUnavailable(f"HTTP {e.code}")
        raise SourceError(f"GitHub returned HTTP {e.code}.")
    except (urllib.error.URLError, TimeoutError) as e:
        raise SourceError(f"Couldn't reach GitHub ({e}).")


def fetch_traffic(src, repos, traffic, include_private, now):
    """Read traffic for repos that are due (once a day each) and merge it into `traffic`.

    Daily counts are merged by date, so history keeps growing past GitHub's 14 days.
    A failed read changes nothing that was stored before; it only sets when to retry.
    """
    api, token = source_auth(src)
    base = rest_base(src)
    done, unavailable = 0, 0
    for repo in repos:
        if repo["isPrivate"] and not include_private:
            continue
        rid = repo["nameWithOwner"]
        t = traffic.setdefault(rid, {"views": {}, "clones": {}})
        if t.get("nextFetch") and now < parse_ts(t["nextFetch"]):
            continue
        try:
            views = rest(f"{base}/repos/{rid}/traffic/views?per=day", token)
            clones = rest(f"{base}/repos/{rid}/traffic/clones?per=day", token)
            referrers = rest(f"{base}/repos/{rid}/traffic/popular/referrers", token)
            paths = rest(f"{base}/repos/{rid}/traffic/popular/paths", token)
        except TrafficUnavailable as e:
            log.info("%s: traffic unavailable (%s); the token needs Administration: Read", rid, e)
            t["status"] = "unavailable"
            t["nextFetch"] = (now + TRAFFIC_REFRESH).isoformat()
            unavailable += 1
            continue
        except SourceError as e:
            log.warning("%s: traffic not updated: %s", rid, e)
            t["nextFetch"] = (now + TRAFFIC_RETRY).isoformat()
            continue
        merge_days(t["views"], views.get("views") or [], now)
        merge_days(t["clones"], clones.get("clones") or [], now)
        t["last14"] = {
            "views": {"count": views.get("count", 0), "uniques": views.get("uniques", 0)},
            "clones": {"count": clones.get("count", 0), "uniques": clones.get("uniques", 0)},
        }
        t["referrers"] = [{"referrer": r["referrer"], "count": r["count"], "uniques": r["uniques"]}
                          for r in referrers or []]
        t["paths"] = [{"path": p["path"], "title": p.get("title") or "", "count": p["count"], "uniques": p["uniques"]}
                      for p in paths or []]
        t["status"] = "ok"
        t["fetchedAt"] = now.isoformat()
        t["nextFetch"] = (now + TRAFFIC_REFRESH).isoformat()
        done += 1
    return done, unavailable


def merge_days(stored, days, now):
    """Fold one response's daily counts into `stored` ({"YYYY-MM-DD": {count, uniques}}).

    GitHub leaves out days with no traffic, so every day in the 14-day window that's
    missing from the response is stored as 0. Days outside the window are never touched.
    """
    today = now.date()
    for i in range(TRAFFIC_DAYS):
        stored[(today - timedelta(days=i)).isoformat()] = {"count": 0, "uniques": 0}
    for d in days:
        stored[d["timestamp"][:10]] = {"count": d["count"], "uniques": d["uniques"]}


def cost(data):
    return (data.get("rateLimit") or {}).get("cost") or 0


def fetch_source(src, now):
    """All repos for one owner, plus the rate-limit points spent getting them."""
    owner = src["owner"]
    api, token = source_auth(src)
    variables = week_vars(week_starts(now, RECENT_WEEKS))

    repos, cursor, points = [], None, 0
    while True:
        data = graphql(api, token, QUERY, {"owner": owner, "cursor": cursor, **variables}, "repositoryOwner")
        points += cost(data)
        ro = data.get("repositoryOwner")
        if ro is None:
            raise SourceError(f"GitHub has no account or org named '{owner}' visible to this token.")
        page = ro["repositories"]
        repos.extend(n for n in page["nodes"] if n)
        if not page["pageInfo"]["hasNextPage"]:
            return repos, points
        cursor = page["pageInfo"]["endCursor"]


def fetch_years(src, repos, years, now):
    """Update the cached 52-week counts in `years` (keyed by owner/name).

    A repo is re-read only when it has been pushed to since its last read, and at
    most once per YEAR_REFRESH. The newest weeks come from every refresh anyway.
    A failure here is logged and skipped; it never marks the source as broken.
    """
    api, token = source_auth(src)
    starts = week_starts(now, YEAR_WEEKS)
    variables = week_vars(starts)
    fetched, points = 0, 0
    for repo in repos:
        cached = years.get(repo["nameWithOwner"])
        if not repo.get("pushedAt"):
            continue  # empty repo
        if cached and (cached["pushedAt"] == repo["pushedAt"]
                       or now - parse_ts(cached["fetchedAt"]) < YEAR_REFRESH):
            continue
        try:
            data = graphql(api, token, YEAR_QUERY,
                           {"owner": src["owner"], "name": repo["name"], **variables}, "repository")
        except SourceError as e:
            log.warning("%s: 52-week activity not updated: %s", repo["nameWithOwner"], e)
            continue
        points += cost(data)
        fetched += 1
        target = ((data.get("repository") or {}).get("defaultBranchRef") or {}).get("target") or {}
        years[repo["nameWithOwner"]] = {
            "fetchedAt": now.isoformat(),
            "pushedAt": repo["pushedAt"],
            "weeks": {d.date().isoformat(): n for d, n in zip(starts, week_counts(target, YEAR_WEEKS))},
        }
    return fetched, points


# ---------------------------------------------------------------- shaping

def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def week_starts(now, n):
    """Monday 00:00 UTC of each of the last n weeks, oldest first. The last is this week."""
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return [monday - timedelta(weeks=n - 1 - i) for i in range(n)]


def week_vars(starts):
    """GraphQL variables $sN/$uN: the first and last second of each week."""
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    variables = {}
    for i, start in enumerate(starts):
        variables[f"s{i}"] = start.strftime(fmt)
        variables[f"u{i}"] = (start + timedelta(weeks=1, seconds=-1)).strftime(fmt)
    return variables


def week_counts(target, n):
    return [(target.get(f"w{i}") or {}).get("totalCount", 0) for i in range(n)]


def read_stage_file(repo):
    blob = repo.get("stageFile")
    if not blob or blob.get("text") is None:
        return {}, None
    try:
        return tomllib.loads(blob["text"]), None
    except tomllib.TOMLDecodeError as e:
        return {}, f"{STAGE_FILE} has a syntax error: {e}"


def shape(repo, owner, year, now):
    meta, err = read_stage_file(repo)
    stage = str(meta.get("stage", "")).strip().lower() or None
    if stage and stage not in STAGES:
        err = err or f"Unknown stage '{stage}' in {STAGE_FILE}."
        stage = None

    target = (repo.get("defaultBranchRef") or {}).get("target") or {}
    commits = [
        {"message": c["messageHeadline"], "date": c["committedDate"], "url": c["url"]}
        for c in (target.get("commits") or {}).get("nodes") or []
    ]
    issues = repo.get("issues") or {}
    releases = [
        {
            "name": r.get("name") or r["tagName"],
            "tag": r["tagName"],
            "url": r["url"],
            "publishedAt": r.get("publishedAt"),
            "downloads": sum(a["downloadCount"] for a in (r.get("releaseAssets") or {}).get("nodes") or []),
        }
        for r in (repo.get("releases") or {}).get("nodes") or [] if r and not r.get("isDraft")
    ]
    stage_hist = ((target.get("stageHistory") or {}).get("nodes") or [None])[0]

    # 52 weeks: this refresh's counts where we have them, the cached year for older
    # weeks, None where neither exists yet (first run, before fetch_years succeeds).
    weekly = week_counts(target, RECENT_WEEKS)
    known = dict((year or {}).get("weeks", {}))
    known.update(zip((d.date().isoformat() for d in week_starts(now, RECENT_WEEKS)), weekly))
    year_starts = week_starts(now, YEAR_WEEKS)

    return {
        "id": repo["nameWithOwner"],
        "owner": owner,
        "repo": repo["name"],
        "url": repo["url"],
        "private": repo["isPrivate"],
        "archived": repo["isArchived"],
        "hasStageFile": bool(repo.get("stageFile")),
        "stageError": err,
        "name": str(meta.get("name") or repo["name"]),
        "summary": str(meta.get("summary") or repo.get("description") or ""),
        "stage": stage,
        "next": str(meta.get("next") or ""),
        "notes": str(meta.get("notes") or "").strip(),
        "category": str(meta.get("category") or ""),
        "paused": bool(meta.get("paused", False)),
        "focus": bool(meta.get("focus", False)),
        "stars": repo.get("stargazerCount", 0),
        "forks": repo.get("forkCount", 0),
        "watchers": (repo.get("watchers") or {}).get("totalCount", 0),
        "releaseCount": (repo.get("releases") or {}).get("totalCount", 0),
        "releases": releases,
        "downloads": sum(r["downloads"] for r in releases),
        "openIssues": issues.get("totalCount", 0),
        "issues": [
            {
                "title": i["title"],
                "url": i["url"],
                "createdAt": i["createdAt"],
                "labels": [l["name"] for l in (i.get("labels") or {}).get("nodes") or []],
            }
            for i in issues.get("nodes") or []
        ],
        "pushedAt": repo.get("pushedAt"),
        "lastCommit": commits[0] if commits else None,
        "commits": commits,
        "commits12w": sum(weekly),
        "weekly": weekly,
        "year": {
            "start": year_starts[0].date().isoformat(),
            # An empty repo has nothing to fetch, so its unknown weeks are simply 0.
            "weeks": [known.get(d.date().isoformat(), None if target else 0) for d in year_starts],
            "fetchedAt": (year or {}).get("fetchedAt"),
        },
        "stageUpdated": stage_hist["committedDate"] if stage_hist else None,
    }


def keep(repo, flt):
    if repo["nameWithOwner"].lower() in flt["exclude"]:
        return False
    if repo["isArchived"] and not flt["include_archived"]:
        return False
    if repo["isFork"] and not flt["include_forks"]:
        return False
    return True


# ---------------------------------------------------------------- state + render

def load_json(path, default):
    """Read a JSON file from /data. A missing file gives `default`; a corrupt one is
    moved aside (never overwritten) so whatever it held can still be recovered."""
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        aside = path.with_name(f"{path.name}.corrupt-{int(time.time())}")
        path.replace(aside)
        log.error("%s was unreadable; moved it to %s and started fresh", path, aside.name)
        return default


def atomic_write(path, text):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


class Board:
    """Everything the page is rendered from.

    The refresh thread and the settings endpoint both change it, so each holds
    `lock` while it does. Fetching from GitHub happens on copies, outside the lock.
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.state = load_json(STATE_FILE, {})
        self.traffic = load_json(TRAFFIC_FILE, {})
        self.settings = load_json(SETTINGS_FILE, {})
        self.settings.setdefault("hidden", [])

    def known_repos(self):
        """Every repo the collector found (after config.toml's filters), by lowercase id."""
        return {p["id"].lower(): p["id"] for e in self.state.values() for p in e["projects"]}


def refresh(board):
    now = datetime.now(timezone.utc)
    cfg = board.cfg
    with board.lock:
        state = copy.deepcopy(board.state)
        traffic = copy.deepcopy(board.traffic)

    for src in cfg["sources"]:
        owner = src["owner"]
        entry = state.setdefault(owner, {"projects": [], "fetchedAt": None})
        try:
            repos, points = fetch_source(src, now)
            repos = [r for r in repos if keep(r, cfg["filters"])]
            years = {r["nameWithOwner"]: y for r in repos
                     if (y := entry.get("years", {}).get(r["nameWithOwner"]))}
            fetched, year_points = fetch_years(src, repos, years, now)
            entry["years"] = years
            entry["projects"] = [shape(r, owner, years.get(r["nameWithOwner"]), now) for r in repos]
            entry["fetchedAt"] = now.isoformat()
            entry["error"] = None
            log.info("%s: %d repos, 52-week activity updated for %d; %d rate-limit points",
                     owner, len(repos), fetched, points + year_points)
            done, unavailable = fetch_traffic(src, repos, traffic, cfg["traffic"]["include_private"], now)
            if done or unavailable:
                log.info("%s: traffic read for %d repos, unavailable for %d", owner, done, unavailable)
        except SourceError as e:
            # Keep the last good data so one bad token doesn't blank the board.
            entry["error"] = str(e)
            log.error("%s: %s", owner, e)

    # Drop sources that were removed from the config. Traffic history is kept regardless.
    configured = {s["owner"] for s in cfg["sources"]}
    for gone in set(state) - configured:
        del state[gone]

    with board.lock:
        board.state, board.traffic = state, traffic
        atomic_write(STATE_FILE, json.dumps(state))
        atomic_write(TRAFFIC_FILE, json.dumps(traffic))
        render(board, now)


def render(board, now):
    """Write index.html and data.json. Call with board.lock held."""
    cfg, state = board.cfg, board.state
    hidden = {h.lower() for h in board.settings["hidden"]}
    projects = []
    for e in state.values():
        for p in e["projects"]:
            collected = not p["private"] or cfg["traffic"]["include_private"]
            projects.append({**p, "hidden": p["id"].lower() in hidden,
                             "traffic": board.traffic.get(p["id"]) if collected else None,
                             "trafficCollected": collected})
    data = {
        "generatedAt": now.isoformat(),
        "staleDays": cfg["stale_days"],
        "refreshMinutes": cfg["refresh_minutes"],
        "stages": STAGES,
        "sources": [
            {"owner": o, "error": e.get("error"), "fetchedAt": e.get("fetchedAt"), "count": len(e["projects"])}
            for o, e in state.items()
        ],
        "projects": projects,
    }
    blob = json.dumps(data).replace("</", "<\\/")
    page = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", blob)
    atomic_write(SITE_DIR / "index.html", page)
    atomic_write(SITE_DIR / "data.json", json.dumps(data, indent=2))


def save_hidden(board, ids):
    """Store the hidden list from the settings screen and re-render at once.

    Returns an error message, or None. Only repos the collector knows are accepted.
    """
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        return "hidden must be a list of owner/name strings"
    with board.lock:
        known = board.known_repos()
        unknown = [i for i in ids if i.lower() not in known]
        if unknown:
            return "Unknown repo: " + ", ".join(unknown[:5])
        board.settings["hidden"] = sorted({known[i.lower()] for i in ids})
        atomic_write(SETTINGS_FILE, json.dumps(board.settings, indent=2))
        render(board, datetime.now(timezone.utc))
    return None


def refresh_loop(board):
    if board.state:
        with board.lock:
            render(board, datetime.now(timezone.utc))
    while True:
        try:
            refresh(board)
        except Exception:  # never let the loop die
            log.exception("refresh failed")
        time.sleep(board.cfg["refresh_minutes"] * 60)


# ---------------------------------------------------------------- web

MAX_BODY = 64 * 1024


class Handler(SimpleHTTPRequestHandler):
    board = None  # set in main()

    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        super().do_GET()

    def do_POST(self):
        if self.path != "/api/settings":
            return self.reply(404, {"error": "Not found"})
        problem = self.cross_origin_problem()
        if problem:
            return self.reply(403, {"error": problem})
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            return self.reply(415, {"error": "Send application/json"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if not 0 < length <= MAX_BODY:
            return self.reply(413, {"error": "Body missing or too large"})
        try:
            body = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self.reply(400, {"error": "Body isn't valid JSON"})
        if not isinstance(body, dict):
            return self.reply(400, {"error": 'Expected {"hidden": [...]}'})
        error = save_hidden(self.board, body.get("hidden"))
        if error:
            return self.reply(400, {"error": error})
        self.reply(200, {"hidden": self.board.settings["hidden"]})

    def cross_origin_problem(self):
        """Only the dashboard's own page may save. Browsers send Origin on every POST;
        it must name this host (as the client sees it, also via X-Forwarded-Host)."""
        origin = self.headers.get("Origin")
        hosts = {h for h in (self.headers.get("Host"), self.headers.get("X-Forwarded-Host")) if h}
        if not origin or urlsplit(origin).netloc not in hosts:
            return "Cross-origin request refused"
        if self.headers.get("Sec-Fetch-Site", "same-origin") != "same-origin":
            return "Cross-site request refused"
        return None

    def reply(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, *args):
        pass


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # As the container's PID 1, Python ignores SIGTERM unless told otherwise, so
    # `docker compose down` would wait 10 s and kill it. Writes are atomic, so just exit.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    cfg = load_config()
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    if not (SITE_DIR / "index.html").exists():
        atomic_write(SITE_DIR / "index.html",
                     "<!doctype html><meta http-equiv=refresh content=10>"
                     "<body style='background:#16191e;color:#e7e9ed;font-family:sans-serif;padding:2em'>"
                     "First refresh in progress. This page reloads itself.")
    board = Board(cfg)
    Handler.board = board
    threading.Thread(target=refresh_loop, args=(board,), daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), partial(Handler, directory=str(SITE_DIR)))
    log.info("serving on :%d", PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
