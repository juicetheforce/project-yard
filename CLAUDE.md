# Project yard

Self-hosted dashboard showing every project across your GitHub accounts/orgs: stage, next step,
and commit activity. Polls GitHub's GraphQL API on a timer and serves a static page.

## Who this is for

The maintainer isn't a full-time developer and maintains this code long-term, so favour boring,
readable, dependency-free solutions over clever ones.

## Layout

- `app/app.py` — collector + HTTP server. Standard library only (Python 3.11+, uses `tomllib`).
- `app/template.html` — dashboard page. `/*__DATA__*/null` is replaced with JSON at render time.
- `config.example.toml`, `.env.example` — copied to `config.toml` / `.env` on the host (both gitignored).
- `compose.yaml` — runs the published image; `compose.build.yaml` overrides it to build locally.
- `.github/workflows/release.yml` — builds and publishes the image on `v*` tags.
- `dev/demo.py` — renders the page from made-up fixture data (no token needed).
- `templates/` — `project.toml` template and `global-CLAUDE.md`, the project-status block for `~/.claude/CLAUDE.md`.
- `docs/scope.md` — decisions, open questions, milestones. Read it before proposing changes.

## Rules

- No third-party Python dependencies without asking first. No frontend build step; the page stays one self-contained HTML file.
- Never log or render tokens. Tokens come only from env vars named in `config.toml`.
- One source's failure must never blank the board: keep last good data, show a banner.
- The dashboard has no auth and is LAN-only by design. Don't add features that assume public exposure.
- Dark UI only (design choice).
- Tag claims in docs as [decided], [confirmed], [inference] or [open]. Say when something is a guess — verify GitHub API behaviour against current docs rather than asserting it.
- Git auth: offer HTTPS (e.g. `gh auth login`) before SSH.

## Testing

No live token in dev by default. Test the collector against fixture data by monkeypatching
`app.graphql` (see `docs/scope.md` → Testing) and render the page to check it visually.
`python3 dev/demo.py` does this with made-up projects and writes `dev/out/index.html`.

## Deploy

Hosts run the published image `ghcr.io/juicetheforce/project-yard:<tag>` (README → Deploy, Releasing).
A release bumps the image version in `compose.yaml` in the commit that gets tagged; the workflow refuses a
tag that doesn't match. Don't tag or push tags unless asked. Details of the maintainer's own host live in
`CLAUDE.local.md` (gitignored), when present.

## Project status

This repo has a `.project.toml` at the root that feeds this dashboard.

- At the end of any session that finishes a milestone, changes direction, or leaves a clear next step, update `.project.toml`: `stage` (idea|scoping|design|building|testing|live), `next` (one line), `paused` if set aside.
- Commit it with the session's other changes (e.g. `chore: update project status`).
- Don't change `name`, `category` or `focus` unless asked.
