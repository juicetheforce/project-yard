#!/usr/bin/env python3
"""Project dashboard.

Every few minutes: read each configured GitHub account/org, pull repos,
their .project.toml stage file and recent commit activity, and render a
static dashboard page. Serves that page on PORT.

Standard library only (Python 3.11+ for tomllib).
"""
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

CONFIG_PATH = Path(os.environ.get("CONFIG", "/config/config.toml"))
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
SITE_DIR = DATA_DIR / "site"
STATE_FILE = DATA_DIR / "last-good.json"
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
DEFAULT_API = "https://api.github.com/graphql"

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
""" % (week_var_decls(RECENT_WEEKS), PAGE_SIZE, ISSUES, COMMITS, week_fields(RECENT_WEEKS))

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

def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def atomic_write(path, text):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def refresh(cfg, state):
    now = datetime.now(timezone.utc)

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
        except SourceError as e:
            # Keep the last good data so one bad token doesn't blank the board.
            entry["error"] = str(e)
            log.error("%s: %s", owner, e)

    # Drop sources that were removed from the config.
    configured = {s["owner"] for s in cfg["sources"]}
    for gone in set(state) - configured:
        del state[gone]

    atomic_write(STATE_FILE, json.dumps(state))
    render(cfg, state, now)


def render(cfg, state, now):
    data = {
        "generatedAt": now.isoformat(),
        "staleDays": cfg["stale_days"],
        "refreshMinutes": cfg["refresh_minutes"],
        "stages": STAGES,
        "sources": [
            {"owner": o, "error": e.get("error"), "fetchedAt": e.get("fetchedAt"), "count": len(e["projects"])}
            for o, e in state.items()
        ],
        "projects": [p for e in state.values() for p in e["projects"]],
    }
    blob = json.dumps(data).replace("</", "<\\/")
    page = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", blob)
    atomic_write(SITE_DIR / "index.html", page)
    atomic_write(SITE_DIR / "data.json", json.dumps(data, indent=2))


def refresh_loop(cfg):
    state = load_state()
    if state:
        render(cfg, state, datetime.now(timezone.utc))
    while True:
        try:
            refresh(cfg, state)
        except Exception:  # never let the loop die
            log.exception("refresh failed")
        time.sleep(cfg["refresh_minutes"] * 60)


# ---------------------------------------------------------------- web

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        super().do_GET()

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
    threading.Thread(target=refresh_loop, args=(cfg,), daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), partial(Handler, directory=str(SITE_DIR)))
    log.info("serving on :%d", PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
