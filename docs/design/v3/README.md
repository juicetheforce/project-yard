# Handoff: Project yard

## Overview
Project yard is a read-only, LAN-only glance page listing every repo owned by one account, showing where each sits on a six-stage pipeline, its next step, and recent activity. You open it, read it in seconds, and close it. No editing, no auth UI.

There are three surfaces:
1. **Overview** (desktop → 32:9 ultrawide), one sorted list.
2. **Compact panel** (~420 × 600) for a KDE panel popup.
3. **Detail page** per repo at `#/owner/repo`.

## About the design files
The files in this bundle are **design references built in HTML**. They show the intended look and behaviour; they are not production code. The target build is **one self-contained file of plain HTML/CSS/vanilla JS**, rendered from a JSON snapshot that a collector writes every 15 minutes. Recreate the design in that environment; don't port the design-tool runtime (`support.js`, `.dc.html` template syntax).

- `Project Yard v3 (standalone).html` opens offline in any browser. Use it to view every state.
- `source/Project Yard v3.dc.html` is the readable source. The template is HTML with `{{ }}` holes, `<sc-for>` loops and `<sc-if>` conditionals; all derived values are computed in the `Component` class at the bottom, and that class is the reference for business logic (flags, sorting, formatting).

Preview switches (top of the logic class, read from props): `view` = `hash | overview | detail-sample | detail-nostage | empty`, `layout` = `full | compact`, `sourceError` = boolean. In the real build, `layout` should come from a query string (e.g. `?compact`), since the panel popup loads the same file.

## Fidelity
**High fidelity.** Colours, type, spacing and states are final. Recreate them closely.

## Design tokens (Nocturne)
Colours:
- `--color-bg` #161826 (page ground) · `--color-surface` #232532 (panels, row hover)
- `--color-text` #e9e9ed · `--color-divider` = #e9e9ed at 16% alpha
- Neutral ramp: 300 #cfd3e5 · 400 #b2b6ca · 500 #9397ab · 600 #75798c · 700 #595d6c · 800 #3f424d · 900 #292b31
- Accent: base #9184d9 · 200 #e7e5fe · 300 #d2cefd · 400 #b5abfc · 500 #968ae0 · 600 #796cbf · 700 #5d5294 · 800 #423a6a · 900 #2b2741
- Warn (quiet / no commits / stale): `oklch(0.8 0.1 80)` ≈ #e0b872
- Error (invalid stage / source error): `oklch(0.74 0.13 25)` ≈ #f08f84

Type: Inter (system-ui fallback is acceptable), headings weight 500, never bolder. `font-variant-numeric: tabular-nums` on body.
Scale used: 30 (detail h1), 22 (stat values; 30 for the "projects" total), 20 (stage title), 17 (next step on detail, release tag, product name in header), 15 (row name, panel titles, detail summary), 14 (body, row next step), 13.5 (notes), 13, 12.5, 12, 11 (labels), 10 (uppercase tags, letter-spacing .08em).

Radii: 4px (sm), 8px (md). Shadows: `--shadow-sm` = `0 0 0 1px #3f424d` (hairline edge on panels); `--shadow-md` = `0 0 0 1px #595d6c, 0 6px 18px rgba(0,0,0,.55)`.

Rules: horizontal separators fade out over 48px on each side (24px in compact, 32px inside panels):
`linear-gradient(to right, transparent, var(--color-divider) 48px, var(--color-divider) calc(100% - 48px), transparent) no-repeat bottom / 100% 1px`.

Focus: `:focus-visible { outline: 2px solid #9184d9; outline-offset: 2px }`. `source/_ds/.../styles.css` holds the full token sheet plus the `.btn`, `.tag`, `.seg`, `.input` classes used. It is safe to inline it.

## Data model (collector → JSON)
Per project:
`name, repo, owner, summary, category, private, archived, paused, focus, stage (Idea|Scoping|Design|Building|Testing|Live|null), stageError (string|null), stageChanged (date), next (string), notes (markdown-lite string), issues (count), last {msg, date}, weeks[12] (commit counts, oldest→newest)`.

Detail extras (dashed **"needs collector"** panels, not gathered yet): `weeks52[52]`, `commits[≤15] {msg, date, sha}`, `issueList[] {title, labels[], createdAt, number}`, `release {tag, date, prerelease, assets[] {name, size, downloads}, older[] {tag, date, downloads}}`, `social {stars, forks, watchers}`.

Source-level: `{name, kind, ok, error, lastGoodAt}` plus a global `refreshedAt`.

Stage file (`.yard/stage.yml` in each repo): `stage`, `focus`, `paused`, `next`, `notes`, `category`, `stageChanged`. The states it produces:
- No file → **No stage file** (accent-300 text, dashed accent pipeline dots).
- Unparseable, or an unknown stage → **Invalid stage file** (error colour, dotted error-coloured dots; detail page shows the parser message in monospace).

## Derived flags (one per row, first match wins)
1. Invalid stage file (error)
2. No stage file (accent-300)
3. Archived (neutral-500)
4. Paused (neutral-500)
5. No commits yet (warn)
6. Quiet · Nd: last commit ≥ 30 days ago and not paused/archived (warn)
7. Stage may be out of date: stage unchanged > 30 days while commits exist after the stage change (warn)

Paused and archived rows render at 50% opacity.

## Screens

### 1. Overview (full layout)
- **Header** (padding 14/24/6): "Project yard" at 17/500 on the left. On the right, the source with a 6px status dot (neutral-400 when ok, error colour when failing) and "Refreshed HH:MM · every 15 min" in neutral-600.
- **Source error banner** (when `sourceError`): a surface panel, max-width 1200, radius 8, `shadow-sm`, 13px text. "{source}: token expired." in error colour, followed by "Showing its last good data from 07:45. The page will recover on the next successful refresh." in neutral-400.
- **Summary strip = stage filter** (padding 20/24/4, flex-wrap, gap 10×22). Buttons, in order: `N projects` (30px number), `Focus`, divider, the six stages, divider, `Paused`, `No stage file` (accent-300), `Invalid stage` (error). Each button is a number (22px/500) over an 11px label, padding 6/12/7, radius 8. Zero counts drop to neutral-600. Hover: surface background. **Active**: accent-900 background, inset 1px accent-700 ring, number accent-200, label accent-300, `aria-pressed=true`. Clicking the active button resets to All. Counts reflect the current category filter.
- **Category chips + sort** (max-width 1600): "All categories", divider, then one chip per category. Each chip is 12.5px, padding 6/10, a 1px neutral-800 border, with the count at 55% opacity. Active chip: accent-900 background, accent-700 border, accent-200 text. Hover: border neutral-500. Sort `<select>` on the right: Furthest along (stage desc, then name) · Most recent commit · Quietest first · Name. **There is no owner filter**: with one owner it's hidden. If more owners are added later, add owner chips after a divider.
- **List**: a single column at every width. Group labels "Focus" (accent) and "Everything else" (neutral-500) are 11px uppercase with a 14px leading rule. Grouping is skipped when the Focus filter is active or nothing in the list is focused. Sort applies within each group.
- **Row** (an `<a href="#/owner/repo">`, padding 11/10/12, radius 8, fading bottom rule, hover fills surface). A wrapping flex row, gap 8×28:
  1. Identity, flex `1 1 240px`, max 380: optional focus dot (6px accent with 6px glow), name 15/500, "private" 10.5 neutral-600, archived/paused tags; summary 12.5 neutral-400; category 12 neutral-500 plus the flag in its colour.
  2. **Next step**, flex `2 1 280px`, max 640: "Next" label 11 neutral-600 over the step text at 14px **in full text colour**. If empty: "No next step" (or "Set in the stage file" when there's no stage file) in neutral-600.
  3. Pipeline, `0 0 180px`: 6 dots of 10px joined by 1px connectors. Done stages: neutral-500 fill. Current stage: accent fill with `0 0 0 3px accent-900, 0 0 10px accent-600`. Future stages: transparent with a neutral-700 border. Below: stage label 12 on the left, "changed Nd ago" 11 neutral-600 on the right.
  4. Sparkline, `0 0 90px`: 12 bars, 22px tall max, 2px gap. Bars with commits are neutral-500 (the current week accent-500); zero weeks are 2px neutral-800. Caption "N commits · 12w" 11px.
  5. Last commit, flex `1 1 190px`, max 280: "Last commit / 3d ago" (warn if quiet), the message on one line with ellipsis, and "Open issues / N".
  6. **Top open issues** (container width ≥ 2400 only), flex `2 1 320px`, max 720: "Open issues" label, then up to 3 titles with ellipsis and their age.
- **Empty state**: "No projects match" 17/500, a hint ("No project matches Idea in Gaming."), and a primary outline button "Show all projects" that clears both filters.

### 2. 32:9 overview
Same as screen 1. Line lengths are held by the max-widths above; the extra width goes to the Next column and the top-issues column. The list never splits into two columns, so sort order always reads top to bottom.

### 3. Compact panel (~420 × 600)
- Header: "Project yard" 14/500, a segmented **All / Focus** toggle (`.seg`, 11.5px), and the refresh time 11 neutral-600. A one-line error strip appears when the source fails.
- Groups: Focus, then Everything else (10px uppercase labels).
- Row: a grid `1fr 78px 42px` over 2 lines, padding 6, rule fade 24px. Line 1: focus dot (5px), name 13/500 with ellipsis, stage label 11 in its state colour, a mini pipeline (7px dots, 1px borders), and last-commit age 11 right-aligned. Line 2 (full width): the flag (if any), then the next step at 12px, one line with ellipsis. About 8 or more projects fit without scrolling. No sparklines, no summary strip. A row click goes to `#/owner/repo`; in the popup, open the detail in the full browser or navigate in place, whichever suits the plasmoid.

### 4. Detail page (`#/owner/repo`, max-width 1600, padding 14/24/56)
- "← All projects" link to `#/`. Unknown route: "No project at this address".
- **Header** (wrap, gap 14×40):
  - Left: focus dot, h1 30px, a category tag, a private/public outline tag, archived/paused tags; summary 15 neutral-300 (max 64ch); a repo link "owner/repo ↗" and the flag.
  - Right: a stat `<dl>`, 4 columns × 2 rows, gap 14×20. Labels 11 neutral-500; values 22/500. Row 1: Open issues · Commits · 12w · Last commit (warn if quiet) · Stage changed. Row 2: Stars · Forks · Watchers · Downloads (all-time release asset downloads).
- A line explaining the dashed "needs collector" panels (remove it once the collector supplies that data).
- **Body: three independent rows.** This is the key layout rule: a long panel must never stretch its neighbours. Every row uses `align-items: start`, and long lists scroll inside their panel.
  - **Row A** (≥1100px: `4fr 3fr 3fr 3fr`; below that, one column):
    - **Stage + next step**: a title (stage name 20/500 + "stage N of 6 · changed …"), or the no-stage/invalid variants. Below it, the large pipeline: 14px dots, labels underneath, a single track line that is neutral-500 up to the current stage and neutral-800 after it. Then a fading divider and "NEXT STEP" (11 uppercase) over the step at 17px.
    - **Commit activity**: 52 bars, 64px tall. The last 12 weeks are brighter (neutral-400, current week accent-500); older weeks are neutral-700. Captions: start month · "N commits · 52w · M in the last 12" · now.
    - **Repository**: `<dl>` with a 96px label column: Repo link, Visibility, Category, Last commit (linked message + date · age), Stage set.
    - **Releases**: header with "N downloads all time". Latest tag 17/500 (linked) with a pre-release tag, date · age, and "N downloads" on the right. Asset list (max-height 204, scrolls): "↓ filename" link, size 11 neutral-600, count 12.5 right-aligned at 44px, and a 3px bar below (accent-600 on neutral-800, width = share of the release's top asset). "EARLIER": one line per older tag with tag link, date and download total. Empty: "No releases yet."
  - **Row B: Notes**, full width. Rendered from markdown-lite: `## ` starts a section (13.5/500 title with a 10px accent lead rule), `- ` is a bullet, any other line is a paragraph. Laid out with `column-width: 340px; column-gap: 40px; column-rule: 1px solid divider`, and sections use `break-inside: avoid-column`. The header shows "N sections · .yard/stage.yml". Empty: "No notes in the stage file."
  - **Row C** (≥1100px: two equal columns):
    - **Recent commits** (last ≤15; list max-height 372, scrolls): 78px date column (12 neutral-500), then the message on one line with ellipsis, linked to the commit.
    - **Open issues** (list max-height 372, scrolls): title link, label tags (`.tag-neutral`, 10px), age right-aligned at 40px.
- Panels: surface background, radius 8, padding 18/20. Data that exists today uses `shadow-sm`; "needs collector" panels use a 1px dashed accent-800 border plus a small dashed accent-700 "NEEDS COLLECTOR" tag (10px uppercase, accent-300). Drop the dashed treatment once the data is real.

## Interactions & behaviour
- Hash routing: `#/` = overview; `#/owner/repo` = detail. Listen for `hashchange`.
- Filters (stage strip + category) live in memory only. Persisting them to `localStorage` is optional.
- Hover: rows and strip buttons fill with surface; links lighten to accent-400. The only motion is simple CSS transitions (≤150ms on background/border colour).
- Times are relative to `refreshedAt`: `<1h → just now`, `<24h → Nh`, `<90d → Nd`, then months, then years. Absolute dates are ISO `YYYY-MM-DD`.
- Accessibility: rows have `aria-label` = "name, stage, flag, next: …"; pipelines and sparklines are `role="img"` with text labels; filter buttons use `aria-pressed`.

## Responsive
- Overview rows wrap naturally (flex-wrap). On a phone each block stacks, with Next on its own line.
- The detail rows collapse to one column below 1100px of container width.
- Top-issues column shows from 2400px. The prototype uses container queries on the root; `@media (min-width: …)` is fine in the real build.

## Sample data
All projects in the prototype are fictional (owner `harbor-lab`) and chosen to show every state: Lanternfish (Design, focus, long notes, pre-release), Patchbay (Building), Tidepool (Testing, focus), Lodestar (stage may be out of date), Herbarium (paused), Ledgerline (no commits yet), Fernbridge (Live, quiet), Marginalia (no stage file), Workstation setup (invalid stage), Beacon relay (archived). The real build replaces this with the collector's JSON.

Preview `view` options in the source: `overview`, `detail-sample` (Lanternfish), `detail-nostage` (Marginalia), `empty`.

## Screenshots
`screenshots/`: 1-overview-desktop (1920), 2-overview-32x9 (5120×1440 at 0.5×), 3-compact-panel (420×600 at 2×), 4-detail (Lanternfish, 1920).

## Files
- `Project Yard v3 (standalone).html`: the offline viewable prototype (all views).
- `source/Project Yard v3.dc.html`: the readable source: template + logic + sample data.
- `source/support.js`: the design-tool runtime the `.dc.html` needs to open. Don't port it.
- `source/_ds/…/styles.css`: Nocturne tokens and component classes.
- `source/_ds/…/_ds_bundle.js`: the design-system component bundle (only loaded by the source file).
