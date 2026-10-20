# Design reference — Project yard v3

Designed in Claude Design (design system "Nocturne"). The handoff is kept unchanged in `v3/`:
`v3/README.md` is the spec (tokens, type scale, rows, flags, compact panel, detail layout),
`v3/screenshots/` shows the intended look, and `v3/source/` is the design-tool source. The build is
`app/template.html`: plain HTML/CSS/vanilla JS in one file, no build step. It recreates the design
rather than porting the design-tool runtime.

## Screens

Renders of the actual page with the made-up projects from `dev/demo.py`
(`python3 dev/demo.py`, then open `dev/out/index.html` at these widths):

| File | What it is |
| --- | --- |
| `screens/overview-1920.png` | Desktop overview, 1920 wide |
| `screens/overview-2600.png` | Wide overview: past 2400px an open-issue-titles column appears |
| `screens/compact-420.png` | Compact layout, 420×600, e.g. for a desktop panel popup |
| `screens/detail-1920.png` | Detail route `#/owner/repo` (a repo with notes, releases and traffic) |
| `screens/settings-1920.png` | Settings route `#/settings` (show/hide repos) |

## Where the build differs from the handoff

The real system wins where the two disagree.

- **Stage file.** The handoff names `.yard/stage.yml`. The real file is `.project.toml` at the repo root,
  unchanged in format and parsing; only captions name it. "Stage changed" comes from git history. [decided]
- **No "needs collector" treatment.** All the data the handoff marked that way is collected since v0.3, so
  every panel uses the normal hairline edge, with no dashed borders, tags or explanatory line. [decided]
- **Release assets.** The handoff's Releases panel lists the latest release's files with size and downloads,
  plus a pre-release tag. v0.3 only had a download total per release, so the collector now also reads each
  asset's name, size and download link and the release's `isPrerelease` (existing fields kept as they were).
  Releases saved by v0.3 show without the file list until the next refresh. [decided]
- **Traffic.** Not in the handoff. Kept from v0.3:
  - a Traffic panel in Row C next to Recent commits and Open issues (Row C is `1fr 1fr 1.3fr` from 1100px)
  - Views · 14d and Clones · 14d (unique) as a third row of the header stats
  - "Unique · 14d" on overview rows for repos that have traffic. [decided]
- **Settings.** Not in the handoff. The gear icon (overview header, right) and `#/settings` stay, restyled
  with the same tokens: a panel of repos with a Shown/Hidden switch each. [decided]
- **Compact mode** switches on width (560px and narrower), not on a `?compact` query string, so the
  panel popup and a narrow window behave the same. [decided]
- **Data field names** are the collector's existing ones (`stage` in lower case, `stageUpdated`, `weekly`,
  `year.weeks`, `lastCommit`, `openIssues`, `issues`, `commits`), mapped in the page. [decided]
- **Font.** Inter isn't loaded from Google Fonts: the page is LAN-only and self-contained. It lists
  `"Inter", system-ui, sans-serif`, so it uses Inter if installed and the system font otherwise. [decided]
- **Detail extras kept from v0.3**: a "hidden" tag on hidden repos, the "N more issues on GitHub" link,
  "Counts the newest 10 of N releases" when a repo has more, and a note while older weeks of the
  52-week chart are still being fetched. The "Earlier" releases list scrolls past about 7 entries. [decided]

## Changes from v2 that come from the handoff

- Flags: one per row, first match wins, in the handoff's order (invalid → no stage file → archived →
  paused → no commits → quiet → stage may be out of date). v2 left out flags the row already showed.
- Sorting no longer forces archived repos to the bottom.
- Compact shows archived repos (dimmed) instead of hiding them.
- Detail is three independent rows with `align-items: start`, and long lists scroll inside their panel:
  Row A stage / activity / repository / releases (`4fr 3fr 3fr 3fr` from 1100px), Row B notes in sectioned
  columns, Row C commits / issues / traffic.
- Notes render markdown-lite: `## ` starts a section, `- ` a bullet, any other line a paragraph.
- Relative times count from the snapshot's refresh time, not the viewer's clock.
