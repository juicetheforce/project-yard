# Design reference — Project yard v5

Designed in Claude Design (design system "Nocturne"). The final handoff is kept unchanged in `v5/`:
`v5/README.md` is the spec (tokens, rows, flags, compact panel, detail rows, traffic, settings),
`v5/screenshots/` shows the intended look, and `v5/source/` is the design-tool source. The build is
`app/template.html`: plain HTML/CSS/vanilla JS in one file, no build step. It recreates the design
rather than porting the design-tool runtime. The Nocturne stylesheet is inlined verbatim (minus its
Google Fonts import), and the three Phosphor icons (`gear-six`, `check`, `chart-bar`, regular weight,
MIT) are inlined as SVG. `v3/` is the previous handoff, kept for history.

## Screens

Renders of the actual page with the made-up projects from `dev/demo.py`
(`python3 dev/demo.py`, then open `dev/out/index.html` at these widths):

| File | What it is |
| --- | --- |
| `screens/overview-1920.png` | Desktop overview, 1920 wide |
| `screens/overview-2600.png` | Wide overview: past 2400px an open-issue-titles column appears |
| `screens/compact-420.png` | Compact layout, 420×600, e.g. for a desktop panel popup |
| `screens/detail-1920.png` | Detail route `#/owner/repo`: a public repo with traffic, sectioned notes and releases |
| `screens/settings-1920.png` | Settings route `#/settings` (show/hide repos) |

## Data mapping

The page reads the collector's existing `data.json` field names and maps them to the handoff's:

| Handoff | data.json |
| --- | --- |
| `stage` (`Building`) | `stage` (`building`), labelled in the page |
| `stageChanged` | `stageUpdated`, now the commit that last changed the `stage` value |
| `issues`, `issueList[]` | `openIssues`, `issues[]` |
| `last {msg, date}`, `commits[]` | `lastCommit {message, date, url}`, `commits[]` |
| `weeks[12]`, `weeks52[52]` | `weekly`, `year.weeks` (null = not fetched yet) |
| `release`, `older[]` | `releases[]` (newest first) |
| `social {stars, forks, watchers}` | `stars`, `forks`, `watchers` |
| `traffic` | `traffic` (`views`/`clones` by date, `last14`, `referrers`, `paths`, `status`) + `trafficCollected` |
| `fork`, `firstSeen` | `fork`, `firstSeen`; "new" also needs the data-level `seenSince` |
| source `kind` | `sources[].kind` (`User` / `Organization`) |

## Where the build differs from the handoff

- **Unique counts over a range.** The 14d range and the header stats use GitHub's own 14-day window
  uniques, as the handoff asks. The 90d and All ranges, like the since-tracking totals, add up daily
  uniques, so they're shown with "≈". [decided]
- **Chart end date.** GitHub's daily list ends a day or two before today, so the traffic chart's right
  edge shows the latest reported date instead of "today". [decided]
- **Traffic states the handoff doesn't have.**
  - A repo whose traffic is collected but not read yet: a quiet line, "Traffic is read once a day…".
  - A repo that has stored history but has since become unreadable: the history stays visible, with
    the quiet "Traffic unavailable" line above it (the handoff replaces the row).
  - Private repos with `[traffic] include_private = true` get the traffic row like public ones. [decided]
- **Releases.** "Downloads all time" counts the newest 10 releases the collector reads; when a repo has
  more, a quiet line says so. [decided]
- **Kept from v0.3–v0.5**: "N more issues on GitHub" under a truncated issue list, and a note while
  older weeks of the 52-week chart are still being fetched. [decided]
- **Project file link** points at `/blob/HEAD/.project.toml`, so it follows the default branch. [decided]
- **Parser messages** for an invalid project file are the collector's existing ones (e.g. "Unknown
  stage 'shipping' in .project.toml."), not the handoff's example wording. [decided]
- **"New" in Settings** means first seen within 7 days *and* after tracking began (`seenSince`), so
  repos that existed when the collector first ran aren't all tagged new. [decided]
- **Font.** Inter isn't loaded from Google Fonts: the page is LAN-only and self-contained. It lists
  `"Inter", system-ui, sans-serif`, so it uses Inter if installed and the system font otherwise. [decided]
