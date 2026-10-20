#!/usr/bin/env python3
"""Render the dashboard from made-up projects, without a GitHub token.

    python3 dev/demo.py            # writes dev/out/index.html (+ data.json)

Feeds fixture data through the real collector by replacing app.graphql, the same way
docs/scope.md → Testing describes, so the page shows every state: focus, paused,
archived, quiet, stage possibly out of date, no project file, an invalid project
file, and an empty repo.
Traffic comes from a fake app.rest for public repos. Older history is seeded in
traffic.json first (30, 180 and 420 days), so the 90d/All ranges and weekly
bucketing show. One public repo answers 403 (traffic unavailable). Two repos are
hidden in settings.json, one of them a fork, and one repo is "new" in seen.json.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)

# app.py reads these at import time.
config = Path(tempfile.mkdtemp()) / "config.toml"
config.write_text('[[sources]]\nowner = "example-user"\ntoken_env = "DEMO_TOKEN"\n')
os.environ.update(CONFIG=str(config), DATA_DIR=str(OUT), DEMO_TOKEN="demo")
sys.path.insert(0, str(HERE.parent / "app"))
import app  # noqa: E402

NOW = datetime.now(timezone.utc)
app.SITE_DIR = OUT


def ts(days_ago):
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def stage_file(stage, next_step, summary, category, **extra):
    lines = [f'stage = "{stage}"', f'next = "{next_step}"', f'summary = "{summary}"', f'category = "{category}"']
    lines += [f"{k} = true" for k, v in extra.items() if v is True]
    if "notes" in extra:
        lines.append(f'notes = """\n{extra["notes"]}\n"""')
    return "\n".join(lines)


HARBOR_NOTES = """## Scope
Notes that work fully offline and sync between my laptop and phone. Nothing depends on a hosted service.
Target is a few thousand notes; search matters more than sharing.

## M1 · sync engine
- Local-first: the server only relays encrypted blobs
- Conflict resolution: last writer wins per field
- Retry with backoff when the relay is unreachable
Done when two devices converge after a day offline.

## Open questions
- Mobile shell, or PWA only?
- Do attachments sync, or stay local?

## Decisions
- 2026-09-12 · No hosted sync service
- 2026-09-24 · One SQLite file per vault"""


# name, stage file text, days since last commit, weekly commit pattern (oldest→newest, 52),
# commit messages (newest first), issues [(title, labels, days ago)], archived
def weeks(active_from, active_to, base):
    return [0 if not (active_from <= i <= active_to) else base + (i * 7) % 5 for i in range(52)]


PROJECTS = [
    ("harbor", stage_file("building", "Wire the sync engine to the real API", "Offline-first notes app with end-to-end sync.",
                          "Personal", focus=True, notes=HARBOR_NOTES),
     1, weeks(20, 51, 4), ["Sync: retry with backoff", "Encrypt blobs before upload", "Field-level merge", "Settings screen",
                           "Export to Markdown", "Search index in a worker", "First sync prototype", "Initial scaffold"],
     [("Sync loses edits made while offline", ["bug", "sync"], 3), ("Decide on a mobile shell", ["design"], 12),
      ("Keyboard shortcuts", ["enhancement"], 30)], False),
    ("lantern", stage_file("testing", "Beta with three households", "Home energy monitor for smart plugs.", "Homelab", focus=True),
     0, weeks(30, 51, 2), ["Alert when a plug goes offline", "Daily summary email", "Chart hourly usage", "MQTT listener"],
     [("Summary email times are UTC", ["bug"], 5)], False),
    ("recipe-box", stage_file("design", "Pick a storage format for recipes", "Family recipe collection with scaling.", "Family", paused=True),
     95, weeks(5, 38, 1), ["Wireframes for the recipe page", "Notes on unit conversion"], [], False),
    ("field-notes", stage_file("idea", "Write down what it should replace", "Birding log that works without signal.", "Personal"),
     64, weeks(10, 42, 1), ["Rough idea doc"], [], False),
    ("weather-station", stage_file("live", "Replace the humidity sensor", "Backyard weather station with a small web page.", "Homelab"),
     20, weeks(0, 48, 1), ["Calibrate the rain gauge", "Graphs for the last 30 days", "Serve JSON for the dashboard"], [], False),
    ("garden-planner", None, 6, weeks(40, 51, 3), ["Frost dates by region", "Bed layout grid", "Start"], [("Import seed list", [], 9)], False),
    ("photo-sorter", 'stage = "shipping"\nnext = "Dedupe by hash"', 45, weeks(20, 45, 2), ["Sort by EXIF date", "Initial"], [], False),
    ("scratchpad", None, None, [0] * 52, [], [], False),
    ("old-site", stage_file("live", "", "The previous personal site.", "Personal"), 300, [0] * 52, ["Final update"], [], True),
]


PUBLIC = {"harbor", "weather-station", "recipe-box", "old-site"}
# Days since the stage value last changed, where it differs from the file's last edit.
STAGE_AGE = {"weather-station": 60, "harbor": 30, "old-site": 300}


def stage_touch(last_days):
    """Days since a commit last touched .project.toml (next/notes edits included)."""
    return min(last_days or 0, 20) + 3


def fake_repo(name, stage_text, last_days, weekly, messages, issues, archived, fork=False):
    commits = [{"messageHeadline": m, "committedDate": ts(last_days + i * 2), "url": "#"} for i, m in enumerate(messages)] \
        if last_days is not None else []
    target = {
        "commits": {"nodes": commits},
        "stageHistory": {"nodes": [{"committedDate": ts(stage_touch(last_days)), "oid": name + "-head"}] if stage_text else []},
        **{f"w{i}": {"totalCount": n} for i, n in enumerate(weekly[-app.RECENT_WEEKS:])},
    }
    return {
        "name": name, "nameWithOwner": f"example-user/{name}", "url": "#", "description": None,
        "isPrivate": name not in PUBLIC, "isArchived": archived, "isFork": fork,
        "stargazerCount": len(name) * 3, "forkCount": len(name) // 3, "watchers": {"totalCount": len(name) // 2},
        "releases": RELEASES.get(name, {"totalCount": 0, "nodes": []}),
        "pushedAt": ts(last_days) if last_days is not None else None,
        "stageFile": {"text": stage_text} if stage_text else None,
        "issues": {"totalCount": len(issues), "nodes": [
            {"title": t, "url": "#", "createdAt": ts(d), "labels": {"nodes": [{"name": l} for l in labels]}}
            for t, labels, d in issues]},
        "defaultBranchRef": {"target": target} if commits else None,
        "_weekly": weekly, "_stage_text": stage_text, "_last_days": last_days,
    }


def release(tag, days_ago, assets, pre=False):
    return {"name": tag, "tagName": tag, "url": "#", "publishedAt": ts(days_ago), "isDraft": False, "isPrerelease": pre,
            "releaseAssets": {"nodes": [{"name": n, "size": size, "downloadUrl": "#", "downloadCount": c} for n, size, c in assets]}}


# harbor: 12 releases, of which the newest 10 are fetched, latest a pre-release.
RELEASES = {
    "harbor": {"totalCount": 12, "nodes": [
        release("v0.10.0-beta.1", 6, [("harbor-0.10.0b1-x86_64.AppImage", 17_600_000, 214), ("harbor-0.10.0b1-1.x86_64.rpm", 9_100_000, 87),
                                      ("harbor-0.10.0b1.tar.gz", 2_200_000, 31), ("SHA256SUMS", 312, 12)], pre=True),
        *[release(f"v0.{n}.0", 6 + (10 - n) * 9, [("harbor.tar.gz", 2_000_000, 30 + n * 4), ("SHA256SUMS", 300, n)]) for n in range(9, 0, -1)]]},
    "weather-station": {"totalCount": 2, "nodes": [
        release("v1.2.0", 30, [("weather-station-1.2.0.tar.gz", 88_000, 9), ("weather.timer", 900, 7)]),
        release("v1.1.0", 120, [("weather-station-1.1.0.tar.gz", 85_000, 14)])]},
}

REPOS = [fake_repo(*p) for p in PROJECTS] + [
    fake_repo("tree-sitter-toml", None, 40, weeks(0, 30, 1), ["Upstream sync"], [], False, fork=True)]


def fake_graphql(api_url, token, query, variables, key):
    if key == "repositoryOwner":
        return {"repositoryOwner": {"repositories": {"pageInfo": {"hasNextPage": False}, "nodes": REPOS}}}
    repo = next(r for r in REPOS if r["name"] == variables["name"])
    if query is app.STAGE_QUERY:
        # Newest first: the last edit (notes/next), the commit that set the current stage,
        # and one before it with an earlier stage.
        text, touch = repo["_stage_text"], stage_touch(repo["_last_days"])
        changed = max(STAGE_AGE.get(repo["name"], touch + 11), touch)
        older = text.replace(text.split('"')[1], "idea", 1) if text.startswith("stage") else ""
        nodes = [{"committedDate": ts(d), "oid": f"{repo['name']}-{d}", "file": {"object": {"text": t}}}
                 for d, t in ((touch, text), (changed, text), (changed + 9, older))]
        return {"repository": {"defaultBranchRef": {"target": {"history": {
            "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}}}}}
    return {"repository": {"defaultBranchRef": {"target": {f"w{i}": {"totalCount": n} for i, n in enumerate(repo["_weekly"])}}}}


def daily(days_ago, name):
    n = (len(name) * 7 + days_ago * 5) % 23 if days_ago % 4 else 0
    return {"timestamp": (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT00:00:00Z"), "count": n, "uniques": n // 3}


def fake_rest(url, token):
    rid = url.split("/repos/")[1].split("/traffic")[0]
    name = rid.split("/")[1]
    if name == "recipe-box":
        raise app.TrafficUnavailable("HTTP 403")
    if url.endswith("/views?per=day") or url.endswith("/clones?per=day"):
        kind = "views" if "/views" in url else "clones"
        days = [daily(d, name + kind) for d in range(14, 0, -1)]  # GitHub's window ends before today
        return {"count": sum(d["count"] for d in days), "uniques": max(d["uniques"] for d in days) + 3, kind: days}
    if url.endswith("/referrers"):
        return [{"referrer": r, "count": c, "uniques": c // 2} for r, c in [("github.com", 41), ("news.ycombinator.com", 17), ("google.com", 6)]]
    return [{"path": f"/{rid}{p}", "title": t, "count": c, "uniques": c // 2}
            for p, t, c in [("", name, 52), ("/blob/main/README.md", "README", 14), ("/releases", "Releases", 5)]]


def history(days, scale):
    """Older daily counts (before GitHub's 14-day window) for seeding traffic.json."""
    out = {}
    for kind, k in (("views", scale), ("clones", max(1, scale // 3))):
        out[kind] = {}
        for d in range(14, days):
            n = (d * 7 + k * 3) % (k + 5) + (k if d % 9 == 0 else 0)
            out[kind][(NOW - timedelta(days=d)).date().isoformat()] = {"count": n, "uniques": max(1 if n else 0, n // 3)}
    return out


# Start clean, then seed older traffic so the 90d and All ranges have something to show.
for f in ("traffic.json", "settings.json", "last-good.json", "seen.json"):
    (OUT / f).unlink(missing_ok=True)
app.TRAFFIC_FILE.write_text(json.dumps({
    "example-user/harbor": history(180, 20), "example-user/weather-station": history(30, 8),
    "example-user/old-site": history(420, 4)}))
app.SETTINGS_FILE.write_text(json.dumps({"hidden": ["example-user/scratchpad", "example-user/tree-sitter-toml"]}))
# Tracking began 30 days ago with every repo but garden-planner, which shows as new.
app.SEEN_FILE.write_text(json.dumps({"baseline": ts(30), "repos": {
    r["nameWithOwner"]: ts(30) for r in REPOS if r["name"] != "garden-planner"}}))

app.graphql = fake_graphql
app.rest = fake_rest
cfg = app.load_config()
cfg["filters"]["include_archived"] = True
cfg["filters"]["include_forks"] = True
app.refresh(app.Board(cfg))
print(f"Wrote {OUT / 'index.html'}")
