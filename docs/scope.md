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
- M2 Deploy on the Docker host (README → Deploy) behind the reverse proxy. The global block is installed in
  `~/.claude/CLAUDE.md` [confirmed 2026-09-29].
  [decided] 2026-09-29: releases are annotated tags, never moved. The repo is published fresh as a public repo
  (MIT) with one clean first commit; the earlier private history stays in a separate private repo. Tag
  pushes build `ghcr.io/juicetheforce/project-yard:<tag>` and `:latest`; hosts need only `compose.yaml`,
  `config.toml` and `.env`, and update by bumping the pinned version and pulling. First public release: v0.2.
  [decided] 2026-09-29: stage files are created by Claude Code per repo via the global block, proposed
  from the repo itself on its first session. No seed files.
- M3 Watch a week of real updates as repos pick up their stage files; fix what the board shows is missing.
- M4+ Re-evaluate: filters, second source (an org), anything the live board shows is missing.

## Testing
Monkeypatch `app.graphql` to return a fixture shaped like the GraphQL response
(`repositoryOwner.repositories.nodes[]` with `stageFile`, `issues{totalCount,nodes}`, `defaultBranchRef.target.{commits,w0..w11,stageHistory}` where each `wN` is `{totalCount}`).
`app.graphql(api, token, query, variables, key)` is also called with `key="repository"` for the 52-week query
(`repository.defaultBranchRef.target.w0..w51`); branch on `key`. Then
point `DATA_DIR` at a temp dir, call `app.refresh(cfg, {})`, then open `site/index.html`.
