#!/usr/bin/env python3
"""Render the dashboard from made-up projects, without a GitHub token.

    python3 dev/demo.py            # writes dev/out/index.html (+ data.json)

Feeds fixture data through the real collector by replacing app.graphql, the same way
docs/scope.md → Testing describes, so the page shows every state: focus, paused,
archived, quiet, no stage file, an invalid stage file, and an empty repo.
Traffic comes from a fake app.rest: a month of older history is seeded in
traffic.json first, so the charts show history merged past GitHub's 14 days.
One repo answers 403 (traffic unavailable) and one is hidden in settings.json.
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


# name, stage file text, days since last commit, weekly commit pattern (oldest→newest, 52),
# commit messages (newest first), issues [(title, labels, days ago)], archived
def weeks(active_from, active_to, base):
    return [0 if not (active_from <= i <= active_to) else base + (i * 7) % 5 for i in range(52)]


PROJECTS = [
    ("harbor", stage_file("building", "Wire the sync engine to the real API", "Offline-first notes app with end-to-end sync.",
                          "Personal", focus=True, notes="Local-first: the server only relays encrypted blobs.\nConflict resolution: last writer wins per field.\nOpen: mobile shell, or PWA only?"),
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


def fake_repo(name, stage_text, last_days, weekly, messages, issues, archived):
    commits = [{"messageHeadline": m, "committedDate": ts(last_days + i * 2), "url": "#"} for i, m in enumerate(messages)] \
        if last_days is not None else []
    target = {
        "commits": {"nodes": commits},
        "stageHistory": {"nodes": [{"committedDate": ts(min(last_days or 0, 20) + 14)}] if stage_text else []},
        **{f"w{i}": {"totalCount": n} for i, n in enumerate(weekly[-app.RECENT_WEEKS:])},
    }
    return {
        "name": name, "nameWithOwner": f"example-user/{name}", "url": "#", "description": None,
        "isPrivate": name != "weather-station", "isArchived": archived, "isFork": False,
        "stargazerCount": len(name) * 3, "forkCount": len(name) // 3, "watchers": {"totalCount": len(name) // 2},
        "releases": {"totalCount": 12 if name == "harbor" else 0, "nodes": [
            {"name": f"v0.{n}", "tagName": f"v0.{n}", "url": "#", "publishedAt": ts(n * 9), "isDraft": False,
             "releaseAssets": {"nodes": [{"downloadCount": 40 - n * 3}, {"downloadCount": 12 - n}]}}
            for n in range(10)] if name == "harbor" else []},
        "pushedAt": ts(last_days) if last_days is not None else None,
        "stageFile": {"text": stage_text} if stage_text else None,
        "issues": {"totalCount": len(issues), "nodes": [
            {"title": t, "url": "#", "createdAt": ts(d), "labels": {"nodes": [{"name": l} for l in labels]}}
            for t, labels, d in issues]},
        "defaultBranchRef": {"target": target} if commits else None,
        "_weekly": weekly,
    }


REPOS = [fake_repo(*p) for p in PROJECTS]


def fake_graphql(api_url, token, query, variables, key):
    if key == "repositoryOwner":
        return {"repositoryOwner": {"repositories": {"pageInfo": {"hasNextPage": False}, "nodes": REPOS}}}
    repo = next(r for r in REPOS if r["name"] == variables["name"])
    return {"repository": {"defaultBranchRef": {"target": {f"w{i}": {"totalCount": n} for i, n in enumerate(repo["_weekly"])}}}}


def daily(days_ago, name):
    n = (len(name) * 7 + days_ago * 5) % 23
    return {"timestamp": (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT00:00:00Z"), "count": n, "uniques": n // 3}


def fake_rest(url, token):
    rid = url.split("/repos/")[1].split("/traffic")[0]
    name = rid.split("/")[1]
    if name == "recipe-box":
        raise app.TrafficUnavailable("HTTP 403")
    if url.endswith("/views?per=day") or url.endswith("/clones?per=day"):
        kind = "views" if "/views" in url else "clones"
        days = [daily(d, name + kind) for d in range(14) if d % 4]  # some days missing, as GitHub omits zeros
        return {"count": sum(d["count"] for d in days), "uniques": max(d["uniques"] for d in days) + 3, kind: days}
    if url.endswith("/referrers"):
        return [{"referrer": r, "count": c, "uniques": c // 2} for r, c in [("github.com", 41), ("news.ycombinator.com", 17), ("google.com", 6)]]
    return [{"path": f"/{rid}{p}", "title": t, "count": c, "uniques": c // 2}
            for p, t, c in [("", name, 52), ("/blob/main/README.md", "README", 14), ("/releases", "Releases", 5)]]


# Start clean, then seed 30 older days for two repos so merging past 14 days is visible.
for f in ("traffic.json", "settings.json", "last-good.json"):
    (OUT / f).unlink(missing_ok=True)
app.TRAFFIC_FILE.write_text(json.dumps({
    f"example-user/{n}": {k: {(NOW - timedelta(days=d)).date().isoformat(): {"count": d % 9, "uniques": d % 4} for d in range(14, 44)}
                          for k in ("views", "clones")}
    for n in ("harbor", "weather-station")}))
app.SETTINGS_FILE.write_text(json.dumps({"hidden": ["example-user/scratchpad"]}))

app.graphql = fake_graphql
app.rest = fake_rest
cfg = app.load_config()
cfg["filters"]["include_archived"] = True
cfg["traffic"]["include_private"] = True
app.refresh(app.Board(cfg))
print(f"Wrote {OUT / 'index.html'}")
