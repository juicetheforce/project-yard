# Project yard — scope v0.1

## Problem
[confirmed] Projects are spread across Claude chats, Claude Projects, Claude Code and GitHub.
The owner wants one place to see what's in flight, what stage each is at, and what's gone quiet.

## Decisions
- [decided] GitHub is the source of truth. Claude chats/Projects/Code sessions can't be queried
  from outside; anything worth tracking gets a repo, even design-only projects (scope docs committed).
- [decided] Stage lives in a `.project.toml` at each repo root; Claude Code updates it via a
  CLAUDE.md instruction. Commits show activity; the file shows stage.
- [decided] Self-hosted behind a reverse proxy, LAN-only. GitHub Pages rejected: Pages sites
  are publicly reachable even from private repos without Enterprise Cloud.
- [decided] Multiple sources: any number of GitHub users/orgs, one token each (fine-grained tokens
  have a single resource owner). Optional `api_url` per source for GHES.
- [decided] Standard-library Python, one container, static page regenerated each poll.
- [decided] A failing source keeps its last good data and shows a banner.
- [decided] "Possibly out of date" flag: stage file unchanged for `stale_days` while newer commits exist.
- [decided] Replaces the earlier hosted claude.ai "Project yard" page (its data has been deleted).
- [decided] UI v2 follows the Claude Design mockups in `docs/design/` (Nocturne tokens): overview, compact
  layout ≤560px for the KDE panel popup, `#/owner/repo` detail pages. Inter is not loaded from Google Fonts.
- [decided] Weeks run Monday 00:00 UTC. Every refresh fetches 12 weekly counts; the detail page's 52-week
  chart comes from a per-repo query cached in `last-good.json`, re-run only after a push and at most daily.
- [confirmed] 2026-09-29 cost on api.github.com (12 repos): refresh = 7 rate-limit points, ~4 s; first run with
  all 12 year queries = 19 points, ~22 s; one year query = 1 point, ~1.3 s. 52 weekly counts inside the main
  query for a page of repos returned HTTP 502 (GitHub timeout), hence the split.
- [inference] Page size 20 keeps the main query under GitHub's timeout for larger orgs; untested past 12 repos.

### v0.3: metrics and show/hide (M4)
- [confirmed] 2026-10-02 against GitHub docs: the REST traffic endpoints (`/traffic/views`, `/traffic/clones`
  with `per=day`, `/traffic/popular/referrers`, `/traffic/popular/paths`) cover the last 14 days, align days
  to UTC midnight, and need the fine-grained permission Administration: Read.
- [decided] Traffic is read once a day per repo (`TRAFFIC_REFRESH`), public repos only unless
  `[traffic] include_private = true`. Daily counts are merged by date into `/data/traffic.json`, kept
  separate from `last-good.json` because it can't be rebuilt. A failed read changes nothing stored; network
  errors retry after an hour, 403/404 marks the repo "unavailable" (quiet note, no banner) and retries daily.
- [confirmed] 2026-10-02 live: the daily list always has 14 entries, zero days included, and ends a day or
  two before today, differently per repo (one ended Sep 30, another Oct 1, read Oct 2 08:00 UTC). Only
  returned days are stored; a day never returned stays unknown in the chart. (An earlier build zero-filled
  a guessed window, which wrote false zeros for days GitHub hadn't reported yet.)
- [confirmed] 2026-10-02 live: a fine-grained token without access gets 403 "Resource not accessible by
  personal access token" (tested on a repo outside the token's owner), handled as "unavailable".
  No token gives 401, which the main query already reports as a bad token.
- [decided] "Unique · 14d" on the overview is GitHub's own 14-day unique count from the latest read.
  Totals since tracking started sum daily counts; the summed daily uniques are labelled as such (they
  double-count repeat visitors).
- [confirmed] 2026-10-02 against GitHub docs: `stargazerCount`, `forkCount`, `watchers { totalCount }`,
  `releases` and `ReleaseAsset.downloadCount` exist in GraphQL. Added to the main query: the newest 10
  releases (drafts skipped) and 20 assets each.
- [confirmed] 2026-10-02 live, 12 repos, one page: main query 5.7–6.9 s and 9 points with releases, 4.8–5.3 s
  and 7 points without (3 runs each). Full first run incl. 12 year queries and 24 traffic calls: 27 s.
  [inference] a full 20-repo page may get close to GitHub's timeout; a 502 shows the usual banner and
  retries next refresh. Lower RELEASES or PAGE_SIZE if it happens.
- [confirmed] 2026-10-02: GHCR pull counts aren't available. The REST packages API has no download field,
  and the GraphQL packages API doesn't support registries with granular permissions (the Container
  registry is one). Skipped; the page says so under release downloads.
- [decided] Show/hide lives on a settings screen (`#/settings`, gear icon), saved to `/data/settings.json`
  as a list of hidden repos, so new repos default to shown. `config.toml`'s `exclude` list is unchanged and
  applies first. Hidden repos still have traffic collected, so unhiding loses nothing.
- [decided] `POST /api/settings` accepts only `Content-Type: application/json` (cross-site forms can't send
  it without a CORS preflight, which is never answered), requires an `Origin` matching `Host` or
  `X-Forwarded-Host`, rejects `Sec-Fetch-Site` other than same-origin, and refuses unknown repo names.
  [inference] DNS rebinding could get past the Origin check; accepted, since the page is LAN-only and the
  worst outcome is hidden repos.

## Open
- [open] Repos that hold more than one project, or projects with no repo.
- [open] Whether to add Claude Code session activity (local transcripts) as a signal. Leaning no: per-machine and messy.

## Milestones
- M0 [confirmed] Code written; tested against fixture data only (missing/broken stage files, paused, missing token).
- M1 [confirmed] First live run: real token, real repos, fix whatever the API disagrees with.
  - [confirmed] 2026-09-29: query runs against api.github.com with a classic OAuth token (`gh auth token`,
    `repo` scope): 12 repos, stage file read, no GraphQL errors. Bad token → 401 → banner, last good data kept.
  - [confirmed] Fixed: `history(first: 100)` silently capped the sparkline at 100 commits (GitHub's page max).
    Now 12 per-week `history(first: 0, since, until) { totalCount }` fields; totals cross-checked with `git rev-list`.
  - [confirmed] 2026-09-29: fine-grained token (README §1 permissions) works with both queries: same 12 repos
    (private included), stage files, commits, issues and 52-week counts as the classic token, no GraphQL errors.
    M1 done.
- M1.5 UI v2 + collector: notes, last 15 commits, open issues (title, labels, age), 52-week activity. Done 2026-09-29.
- M2 [confirmed] Deploy on the Docker host (README → Deploy) behind the reverse proxy. v0.2 runs from the
  published image and is in daily use with no issues reported (confirmed 2026-10-02). The global block is installed in
  `~/.claude/CLAUDE.md` [confirmed 2026-09-29].
  [decided] 2026-09-29: releases are annotated tags, never moved. The repo is published fresh as a public repo
  (MIT) with one clean first commit; the earlier private history stays in a separate private repo. Tag
  pushes build `ghcr.io/juicetheforce/project-yard:<tag>` and `:latest`; hosts need only `compose.yaml`,
  `config.toml` and `.env`, and update by bumping the pinned version and pulling. First public release: v0.2.
  [decided] 2026-09-29: stage files are created by Claude Code per repo via the global block, proposed
  from the repo itself on its first session. No seed files.
- M3 Watch real updates as repos pick up their stage files; fix what the board shows is missing. Running
  alongside M4.
- M4 Feature requests for the next release. Record each under Open (or Decisions once agreed) before
  building it; ship as v0.3 per README → Releasing.
  - [confirmed] 2026-10-02: GitHub metrics (traffic history, stars/forks/watchers, release downloads) and the
    show/hide settings screen built and tested against fixtures (`dev/demo.py`). Run live the same day:
    traffic read for all 6 public repos of juicetheforce; see the v0.3 decisions above.
- M5+ Re-evaluate: filters, second source (an org), anything the live board shows is missing.

## Testing
Monkeypatch `app.graphql` to return a fixture shaped like the GraphQL response
(`repositoryOwner.repositories.nodes[]` with `stageFile`, `issues{totalCount,nodes}`, `defaultBranchRef.target.{commits,w0..w11,stageHistory}` where each `wN` is `{totalCount}`).
`app.graphql(api, token, query, variables, key)` is also called with `key="repository"` for the 52-week query
(`repository.defaultBranchRef.target.w0..w51`); branch on `key`. Then
point `DATA_DIR` at a temp dir, call `app.refresh(app.Board(cfg))`, then open `site/index.html`.
Traffic goes through `app.rest(url, token)`; monkeypatch it too, returning the REST shapes or raising
`app.TrafficUnavailable` (no permission) or `app.SourceError` (network). `dev/demo.py` does all of this.
