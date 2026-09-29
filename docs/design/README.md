# Design reference — Project yard v2

Designed in Claude Design (design system "Nocturne"), 2026. Built as `app/template.html`
(plain HTML/CSS/vanilla JS, one file, no build step). This page records the design decisions
the build follows; the original mockups aren't part of the repo.

## Screens

Renders of the actual page with the made-up projects from `dev/demo.py`
(`python3 dev/demo.py`, then open `dev/out/index.html` at these widths):

| File | What it is |
| --- | --- |
| `screens/overview-1920.png` | Desktop overview, 1920 wide |
| `screens/overview-2600.png` | Wide overview: past 2400px an open-issue-titles column appears |
| `screens/compact-420.png` | Compact layout, 420×600, e.g. for a desktop panel popup |
| `screens/detail-1920.png` | Detail route `#/owner/repo` |

## Tokens

These are the Nocturne values the page uses, copied into its own `:root`.

### Colour
Dark only.

| Role | Token | Value |
| --- | --- | --- |
| Page ground | `--color-bg` | `#161826` |
| Panel / hover surface | `--color-surface` | `#232532` |
| Text | `--color-text` | `#e9e9ed` |
| Accent (lines, marks, current stage) | `--color-accent` | `#9184d9` |
| Divider (fading rules) | `--color-divider` | text at 16% |
| Row rule inside panels | — | text at 8% |
| Error (invalid stage, source down) | — | `oklch(0.74 0.13 25)` |
| Warning (quiet, stale, no commits) | — | `oklch(0.8 0.1 80)` |

Tonal ramps in use:
- Neutral:
  - 300 `#cfd3e5` for secondary text
  - 400 `#b2b6ca` for tertiary text
  - 500 `#9397ab` for labels and done stages
  - 600 `#75798c` for faint text
  - 700 `#595d6c` for borders
  - 800 `#3f424d` for empty bars and separators
- Accent:
  - 200–300 for text on accent tints and "No stage file"
  - 500–600 for the current-week bar and glow
  - 700–900 for pressed and active fills and rings

Rules:
- Use the accent as a line or a glow, never as a large fill.
- Rules fade to transparent over 48px at each end (24–32px inside panels).
- Elevation is a hairline: `--shadow-sm: 0 0 0 1px #3f424d`.

### Spacing
The design uses fixed px values rather than the token scale:
- Page gutter: 24px (12px in compact).
- Rows: 11–12px vertical padding and a 28px column gap.
- Panels: 18px/20px padding and a 16px grid gap.
- Nocturne's scale, for reference, runs at 0.7× density: 2.8 / 5.6 / 8.4 / 11.2 / 16.8 / 22.4px.

Radii: 4px (small), 8px (medium), 14px (large).

### Type
- Font: Inter at weights 400 and 500. Headings never go above 500.
  - The design loads Inter from Google Fonts. The build does not, because the page is LAN-only and self-contained. It lists `"Inter", system-ui, sans-serif`, so it uses Inter if it's installed and the system font otherwise. [decided]
- Numbers use `tabular-nums` throughout.
- Sizes:

| Size | Used for |
| --- | --- |
| 30px | Detail title; the "projects" count in the summary strip |
| 22px | Other strip counts and detail stats |
| 20px | Detail stage label |
| 17px | Page title; detail next step |
| 15px | Row name; panel titles |
| 14px | Body; next step in rows |
| 12–12.5px | Metadata |
| 10–11px | Captions, kickers (uppercase, 0.06–0.08em tracking) and tags |

## Components and behaviour

- **Stage rail**: six nodes joined by 1px connectors.
  - Done: filled neutral-500.
  - Current: filled accent with a 3px accent-900 ring and a glow.
  - To do: neutral-700 outline.
  - No stage file: dashed accent-600 outline.
  - Invalid stage: dotted red outline.
  - Node sizes: 7px (compact), 10px (rows), 14px (detail, with labels).
- **Sparkline**: 12 weekly bars, 22px tall. The current week is accent-500; empty weeks are a 2px neutral-800 stub.
  - The 52-week detail chart is 64px tall, with the last 12 weeks brighter than the older 40.
- **Summary strip**: the counts are also filter buttons. Clicking one again clears it.
  - Groups: all, Focus │ six stages │ Paused, No stage file, Invalid stage.
  - Category chips and the sort control sit under the strip.
- **Grouping**: "Focus" and "Everything else" appear whenever any focus project is in the list.
- **Flags**: one short warning per row.
  - The build shows only what the row doesn't already say. The design repeated "No stage file" / "Invalid stage" as both the stage label and the flag, and "Archived" / "Paused" as both a tag and a flag.
  - Precedence: no commits → quiet (no commit in `stale_days`) → stage possibly out of date.
- **Compact** (≤560px wide):
  - One header line with an All/Focus toggle.
  - Rows are a three-column grid: name + stage | mini rail | last commit age. The second line holds the flag and the next step.
  - Archived repos are hidden.
- **Detail**:
  - Header with tags and four stats.
  - Panels: Stage (spans 2 columns), Notes, Recent commits, Open issues, then Activity and Repository stacked.
  - The grid is 3fr/3fr/2fr from 1000px wide, one column below that.
  - Commit dates never wrap.
- **Sorting**: furthest along, most recent commit, quietest first, or name. Archived repos always go last.
