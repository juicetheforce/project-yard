## Project status (Project yard)

My project dashboard reads a `.project.toml` at the root of each of my repos. Keep it current.

**Which repos:** only git repos whose `origin` is on github.com under `<your-github-user>`
(add accounts/orgs here as they join the dashboard). Anywhere else, such as client repos, other
people's repos, or folders without a GitHub remote, ignore this section entirely.

**Fields:**

```toml
name = "Project name"       # optional; defaults to the repo name
summary = "One line on what this is."
stage = "building"          # idea | scoping | design | building | testing | live
next = "The very next concrete step."
category = "Personal"       # free text: Work, Personal, Homelab, Games...
paused = false
focus = false
# notes = """
# Optional. Decisions, constraints, anything worth seeing at a glance.
# """
```

**When to update:** at the end of any session that finishes a milestone, changes direction, or
leaves a clear next step. Update `stage`, `next` (one line), and `paused` if work is being set
aside. Update `notes` only when a decision worth remembering was made. Don't change `name`,
`category` or `focus` unless I ask.

**If the file is missing:** in the first session in that repo, propose one drafted from the
repo itself (README, code, docs, commit history, GitHub description): every field, with
`paused` and `focus` false. Show it to me, adjust anything I correct, then create it.

**Committing:** commit it with the session's other changes (e.g. `chore: update project status`),
or on its own if nothing else changed. The dashboard reads the default branch on GitHub, so it
shows up once pushed. Mention that if I haven't pushed.
