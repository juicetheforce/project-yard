# Handoff: Project yard (v5)

## Overview
Project yard is a read-only, LAN-only glance page. It lists every repo the collector finds for one GitHub account and shows each repo's stage on a six-step pipeline, its next step, and recent activity. You open it, read it in seconds, and close it. The only interactive settings are the show/hide toggles on the Settings screen.

Screens:
1. **Overview** (`#/`): one sorted list, desktop through 32:9.
2. **Compact panel**: the same page at ≤560px wide, used in a KDE panel popup.
3. **Detail** (`#/owner/repo`): one page per repo.
4. **Settings** (`#/settings`): show/hide repos.

## About the design files
The files here are **design references built in HTML**, not production code. Build the real thing as **one self-contained file of plain HTML/CSS/vanilla JS**, rendered from the collector's JSON. Don't port the design-tool runtime (`support.js`, the `.dc.html` template syntax).

- `Project Yard v5 (standalone).html`: opens offline and shows every state.
- `source/Project Yard v5.dc.html`: the readable source. The template is HTML with `{{ }}` holes, `<sc-for>` loops and `<sc-if>` conditionals. The `Component` class at the bottom is the reference for all business logic: flags, sorting, traffic windows, note parsing and formatting.

Preview props (for review only; not part of the real build):
- `view`: `hash | overview | detail-private | detail-public | detail-traffic-unavailable | detail-nostage | settings | settings-failed | empty`
- `layout`: `auto` (switch on width, the real behaviour) `| full | compact`
- `sourceError`: shows the token-expired banner.

## Fidelity
**High fidelity.** Colours, type, spacing and states are final.

## Design tokens (Nocturne)
Colours:
- `--color-bg` #161826 (page) · `--color-surface` #232532 (panels, row hover)
- `--color-text` #e9e9ed · `--color-divider` = #e9e9ed at 16% alpha
- Neutral ramp: 300 #cfd3e5 · 400 #b2b6ca · 500 #9397ab · 600 #75798c · 700 #595d6c · 800 #3f424d · 900 #292b31
- Accent: base #9184d9 · 200 #e7e5fe · 300 #d2cefd · 400 #b5abfc · 500 #968ae0 · 600 #796cbf · 700 #5d5294 · 800 #423a6a · 900 #2b2741
- Warn (quiet, no commits, stale stage): `oklch(0.8 0.1 80)` ≈ #e0b872
- Error (invalid file, failed source or save): `oklch(0.74 0.13 25)` ≈ #f08f84

Type: Inter (a system-ui fallback is fine), headings at weight 500 and never bolder. `font-variant-numeric: tabular-nums` on body.
Scale: 30 (h1), 22 (stat values; 30 for the projects total), 20 (stage title, since-tracking totals), 17 (detail next step, release tag), 15 (row name, panel titles), 14 (body), 13.5 (notes), 13, 12.5, 12, 11 (labels), 10 (uppercase labels, letter-spacing .08em).

Radii: 4px (sm), 8px (md). Panels use `--shadow-sm` = `0 0 0 1px #3f424d`.

Rules fade out over 48px on each side (24px in compact, 32px inside panels):
`linear-gradient(to right, transparent, var(--color-divider) 48px, var(--color-divider) calc(100% - 48px), transparent) no-repeat bottom / 100% 1px`.

Focus: `:focus-visible { outline: 2px solid #9184d9; outline-offset: 2px }`.
Scrollbars: `scrollbar-width: thin; scrollbar-color: #595d6c transparent`.
Icons: Phosphor regular. Only `gear-six` (settings), `check` (saved) and `chart-bar` (traffic unavailable) are used; inline them as SVG in the real build so it stays self-contained.
`source/_ds/.../styles.css` holds the full token sheet plus the `.btn`, `.tag`, `.seg` and `.input` classes. Inline it.

## Project file: `.project.toml`
The file sits at the repo root. Fields:

```toml
name     = "Patchbay"
summary  = "Daemon for USB macro pads on Linux."
stage    = "Building"   # Idea | Scoping | Design | Building | Testing | Live
next     = "Bring-up on the 15-key and 32-key boards"
category = "Desktop"
paused   = false
focus    = true
notes    = """
Free text. Lines starting with "## " are headings, "- " are bullets,
anything else is a paragraph. Blank lines are ignored.
"""
```

- `stageChanged` is **not** in the file. The collector derives it from git history: the date of the most recent commit that changed the `stage` value.
- No file → **No project file**: accent-300 text, dashed accent pipeline dots, Next shows "Set in .project.toml".
- Unparseable file, or an unknown `stage` → **Invalid project file**: error colour and dotted error-coloured dots. The detail page shows the parser message in monospace, e.g. `.project.toml: stage = "Shipping" is not one of …`.

## Data (collector → JSON)
All of it is collected today. Nothing on the page is a placeholder.

Per repo:
- From the project file: `name`, `summary`, `stage`, `next`, `category`, `paused`, `focus`, `notes`.
- From GitHub: `repo`, `owner`, `private`, `archived`, `fork`, `stageChanged` (derived), `issues` (count), `last {msg, date}`, `weeks[12]`, `weeks52[52]`, `commits[≤15] {msg, date, sha}`, `issueList[] {title, labels[], createdAt, number}`, `release {tag, date, prerelease, assets[] {name, size, downloads}, older[] {tag, date, downloads}}`, `social {stars, forks, watchers}`.
- Collector bookkeeping: `firstSeen` (drives the "new" tag in Settings).

`traffic` takes one of three forms:
- absent, for private repos;
- `"unavailable"`, for a public repo the token lacks permission to read;
- an object: `{ daily[] {date, views, viewsUnique, clones, clonesUnique}, views14 {count, uniques}, clones14 {count, uniques}, referrers[] {source, views, uniques}, paths[] {path, title, views, uniques}, since }`.

Notes on traffic:
- GitHub only returns the last 14 days, so the collector appends each day to its own store. History runs anywhere from 14 days to a year or more.
- The 14-day unique figures must come from the API's window `uniques`. They are lower than the sum of daily uniques; don't add those up.
- The since-tracking totals are sums over the stored history. Label their unique figures as approximate, since daily uniques overlap.

Source-level: `{name, kind, ok, error, lastGoodAt}` and a global `refreshedAt`. Settings: `hidden[]` (repo names), persisted by the collector.

## Derived flags (one per row, first match wins)
1. Invalid project file (error colour)
2. No project file (accent-300)
3. Archived (neutral-500)
4. Paused (neutral-500)
5. No commits yet (warn)
6. Quiet · Nd: last commit 30+ days ago, not paused or archived (warn)
7. Stage may be out of date: stage unchanged for over 30 days while commits exist after the stage change (warn)

Paused and archived rows render at 50% opacity.

## Screens

### 1. Overview
- **Header**: "Project yard" at 17/500 on the left. On the right: the source with a 6px status dot (neutral-400 when ok, error colour on failure), "Refreshed HH:MM · every 15 min" in neutral-600, and a 30×30 **gear icon link to `#/settings`** (neutral-400; hover fills surface and turns text colour).
- **Source error banner** (on failure): surface panel, max-width 1200, `shadow-sm`, 13px. "{source}: token expired." in error colour, followed by "Showing its last good data from HH:MM. The page will recover on the next successful refresh." in neutral-400.
- **Summary strip, which is also the stage filter.** Buttons in order: `N projects` (30px), Focus, divider, the six stages, divider, Paused, No project file (accent-300), Invalid file (error).
  - Each button is a 22/500 number over an 11px label, padding 6/12/7, radius 8. Zero counts drop to neutral-600. Hover fills surface.
  - **Active**: accent-900 fill, inset 1px accent-700 ring, number accent-200, label accent-300, `aria-pressed`. Clicking the active button resets to All.
  - Counts reflect the current category filter and exclude hidden repos.
- **Category chips + sort.**
  - Chips: "All categories", a divider, then one chip per category. 12.5px, 1px neutral-800 border, the count at 55% opacity. Active chip: accent-900 fill, accent-700 border, accent-200 text.
  - Sort `<select>`: Furthest along · Most recent commit · Quietest first · Name.
  - There's no owner filter (one owner).
- **List**: a single column at every width. Group labels are "Focus" (accent) and "Everything else" (neutral-500). Grouping is skipped when the Focus filter is on or nothing is focused.
- **Row** (`<a href="#/owner/repo">`): a wrapping flex row, gap 8×28, hover fills surface.
  1. **Identity** (flex `1 1 240px`, max 380): focus dot, name 15/500, a "private" tag, archived/paused tags; summary 12.5 neutral-400; category plus the flag.
  2. **Next** (flex `2 1 280px`, max 640): "Next" label 11 neutral-600 over the step at 14px in full text colour. Empty: "No next step" in neutral-600.
  3. **Pipeline** (`0 0 180px`): 10px dots with 1px connectors. Done = neutral-500; current = accent with `0 0 0 3px accent-900, 0 0 10px accent-600`; future = neutral-700 outline. Below it: the stage label and "changed Nd ago".
  4. **Sparkline** (`0 0 100px`): 12 weekly bars, 22px max. The current week is accent-500 and empty weeks are 2px neutral-800. Caption "N commits · 12w" (nowrap).
  5. **Last commit** (flex `1 1 210px`, max 300), as label/value lines:
     - Last commit / age (warn when quiet)
     - the message (ellipsis)
     - Open issues / N
     - **Unique · 14d / N views · N clones**, only for repos with traffic; repos without show nothing.
  6. **Top open issues** (container ≥2400px only): up to 3 titles with ages.
- **Empty state**: "No projects match", a hint, and a "Show all projects" outline button.

### 2. 32:9 overview
Same as screen 1. Max-widths hold line length, and extra width goes to Next and the top-issues column. It stays one list, so the sort order reads top to bottom.

### 3. Compact panel
- **Switches on width, not a query string.** When the page's own width is ≤560px, render the compact layout instead of the overview. Use a `ResizeObserver` on the root, or `@media (max-width: 560px)` plus two DOM blocks. Detail and Settings routes keep their normal (stacked) layouts at any width.
- **Header**: "Project yard" 14/500, an **All / Focus** segmented toggle (`.seg`, 11.5px), and the refresh time. A one-line error strip shows when the source fails.
- **Row**: a two-line grid, `1fr 78px 42px`.
  - Line 1: focus dot, name 13/500, stage label in its state colour, mini pipeline (7px dots), and last-commit age.
  - Line 2: the flag, then the next step at 12px with ellipsis.
- 10 rows fit in 420×600 without scrolling. No sparklines, summary strip or traffic. A row click opens `#/owner/repo`.

### 4. Detail (`#/owner/repo`, max-width 1600)
- "← All projects". An unknown or hidden route shows "No project at this address … It may be hidden in Settings."
- **Header.** Left: the identity (h1 30px, category tag, private/public tag, archived/paused tags, summary, repo link, flag). Right: a stat `<dl>`, two rows of equal columns (labels 11 neutral-500, values 22/500):
  - Private repo (4×2):
    - Open issues · Commits · 12w · Last commit · Stage changed
    - Stars · Forks · Watchers · Downloads
  - Public repo (5×2): the same two rows plus **Views · 14d** at the end of row 1 and **Clones · 14d** at the end of row 2. Both show the API's unique counts. When traffic is unavailable, both show "—" in neutral-600.
  - Downloads = all-time release asset downloads.
- **Body rows.** Each row is independent. At ≥1100px container width every multi-panel row is `repeat(3, minmax(0,1fr))` with `align-items: stretch`, so the panels in a row share one height. Below 1100px everything stacks. Growing lists are capped at **372px** and scroll inside their panel.
  - **Row A, fixed-size facts.**
    - **Stage + next step**: stage title, large pipeline (14px dots), divider, "NEXT STEP" over the step at 17px.
    - **Commit activity**: 52 weekly bars in a flex:1 area (64–140px). Heights are percentages of the busiest week (min 4%, zero weeks 2px). The last 12 weeks are neutral-400, the current week accent-500, older weeks neutral-700.
    - **Repository**: `<dl>` with Repo, Visibility, Category, Last commit, and Project file (`.project.toml ↗` link, or "None").
  - **Row B, Notes** (full width).
    - Parse into a **flat list of blocks** (heading, paragraph, bullet) inside one `column-width: 340px; column-gap: 40px; column-rule: 1px solid divider` container.
    - Put `break-inside: avoid` on each paragraph and bullet, and `break-after: avoid` on each heading. **Don't wrap sections in a container that avoids breaks**, or one long section can't flow into a second column.
    - Headings are 13.5/500 with a 10px accent lead rule and 10px top padding (except the first). Paragraphs have a 10px bottom margin. Bullets are flex rows with a neutral-500 "•".
    - Header meta: "N sections · .project.toml", "N paragraphs · .project.toml" for long plain notes, or just ".project.toml".
    - Empty: "No notes in .project.toml."
  - **Row C, Traffic** (public repos with traffic only):
    - **Views & clones**.
      - Header: a `.seg` range control showing only the ranges the stored history covers: **14d** always, **90d** when there are more than 14 days, **All** when there are more than 90. Default is 90d, or the longest available.
      - Two charts. Views: flex, min 72px. Clones: 40px. Each bar is a neutral-700 total with an accent-500 unique overlay, sized as a percentage of the busiest bar.
      - Ranges over 120 days bucket into weeks. The caption reads "daily" or "weekly", and each bar's title gives the date and counts.
      - Each chart's header shows "N unique · N total" for the range.
      - Footer: a legend, then a divider and "SINCE TRACKING BEGAN · date" with Views and Clones totals (20/500) and their approximate uniques.
    - **Top referrers** ("last 14 days"): column heads Source / Views / Unique. Each row has a 3px accent-600 share bar relative to the top referrer. Empty: "No referrers in the last 14 days."
    - **Popular pages** ("last 14 days"): the path in monospace with the `/owner/repo` prefix stripped ("/" for the repo home), linked to github.com, with the full path in the title. Columns and bars as for referrers.
    - Omit the whole row for private repos.
    - **Traffic unavailable** (public, but the token can't read it): replace the row with one quiet line, 12.5px neutral-500 with a chart-bar icon: "Traffic unavailable. The token can’t read traffic for this repo."
  - **Row D, growing lists.**
    - **Recent commits**: last ≤15, a 78px date column and the message.
    - **Open issues**: title, label tags, age.
    - **Releases**: all-time downloads in the header. The body scrolls as one region: latest tag with a pre-release tag, date and download total; asset rows with size, count and share bar; then an "EARLIER" list with tag, date and downloads. Empty: "No releases yet."
  - A short list leaves space at the bottom of its panel; that's intended, so the row's bottom edges align.

### 5. Settings (`#/settings`, max-width 880)
- "← All projects", an h1 "Settings", and a **save status** on the right (`role="status"`, `aria-live="polite"`). States:
  - idle: "Changes save automatically" (neutral-500)
  - saving: "Saving…"
  - saved: check icon + "Saved · HH:MM" (neutral-300)
  - failed: "Not saved" (error colour)
- Intro (14px neutral-400): every repo the collector finds; hidden repos leave the board and panel straight away and stay listed here; new repos are shown by default.
- **Failure banner** (`role="alert"`): surface panel, `shadow-sm`. "Couldn’t save: hiding {name}." in error colour, "Nothing was changed." in neutral-400, and a `.btn-secondary` **Try again** button. On failure, revert the toggle.
- **Repositories panel**: header with "N shown · N hidden", then one row per repo sorted by name. Each row is a grid `44px 1fr auto`:
  - **Switch** (`role="switch"`, `aria-checked`, `aria-label` "Hide X" / "Show X"): 36×20 pill with a 14px knob. On: accent-700 track, accent-500 border, accent-200 knob, knob at 18px. Off: neutral-800 track, neutral-700 border, neutral-500 knob, knob at 2px. 150ms transitions.
  - **Name** 14/500 over `owner/repo` 12 neutral-500. Hidden rows sit at 55% opacity.
  - **Status tags**: `hidden` (outline), `archived` (neutral), `fork` (neutral), `new` (accent; first seen within 7 days). A repo with none of these shows `shown` (neutral).
- **Behaviour**:
  - Toggling applies to the board immediately, then saves.
  - Hidden repos are removed from the overview, compact panel, counts and detail routes.
  - Repos the collector hasn't seen before default to shown.

## Interactions
- Hash routing: `#/`, `#/owner/repo`, `#/settings`. Listen for `hashchange`.
- Filters, sort and traffic range live in memory only.
- Motion is limited to ≤150ms transitions on colour and the switch knob.
- Relative times: `<1h` just now, `<24h` Nh, `<90d` Nd, then months, then years. Absolute dates are `YYYY-MM-DD`.
- Accessibility:
  - Rows carry `aria-label` "name, stage, flag, next: …".
  - Charts are `role="img"` with text labels.
  - Filters use `aria-pressed`.
  - Switches use `role="switch"`.

## Sample data
All projects are fictional (owner `harbor-lab`):
- **Patchbay**: public, traffic (180 days), releases, 12 plain-paragraph notes.
- **Lanternfish**: private, no traffic, sectioned notes.
- **Fernbridge**: public, traffic unavailable, quiet.
- **Lodestar**: public, 30 days of traffic, stage may be out of date.
- **Beacon relay**: public, archived, 420 days of traffic (shows weekly bucketing under All).
- **Tidepool**: Testing.
- **Herbarium**: paused.
- **Ledgerline**: no commits.
- **Marginalia**: no project file, new.
- **Workstation setup**: invalid project file.
- Two hidden repos: advent-of-code-2025, and tree-sitter-toml (a fork).

## Screenshots (`screenshots/`)
1. `1-overview-desktop`: 1920 wide
2. `2-overview-32x9`: 5120×1440, at 0.5×
3. `3-compact-panel`: 420×600, at 2×
4. `4-detail-private`: Lanternfish
5. `5-detail-public-traffic`: Patchbay (traffic row, long plain notes in four columns)
6. `6-settings`
7. `7-settings-save-failed`
8. `8-detail-traffic-unavailable`: Fernbridge

## Files
- `Project Yard v5 (standalone).html`: the offline prototype.
- `source/Project Yard v5.dc.html`: readable source with template, logic and sample data.
- `source/support.js`: the design-tool runtime the source file needs; don't port it.
- `source/_ds/…/styles.css`: Nocturne tokens and component classes.
- `source/_ds/…/_ds_bundle.js`: the design-system bundle, loaded only by the source file.
