# Draft lines for global agent instructions

Proposed text for the program lead's global instruction files, for review before
anyone edits them. The same text goes in all three files, which share one
structure: `~/.claude/CLAUDE.md`, `~/AGENTS.md` and `~/.codex/AGENTS.md`.
Nothing here has been applied.

## 1. New section

Insert after the "Feature & Bugfix Workflow" section and before "Keeping
CLAUDE.md Current" (in the two AGENTS.md files: before "Keeping AGENTS.md
Current").

```markdown
## Programs and Orchestration: Always Work From an Agreed Roadmap

**When work is part of a program (several issues, workers or sessions toward one
goal), invoke the `roadmap` skill (native name `roadmap:roadmap`) and keep one
roadmap agreed with me. Work only from it.** Diverge only with my approval, or
for a genuinely good reason stated in the next update.

- **Kickoff:** brainstorm the goal with me, draft `roadmap.json`, run
  `roadmap.py validate` and `roadmap.py render`, show me the page, and get my
  agreement. No worker starts before the roadmap is agreed.
- **Words:** Roadmap, Epic, Issue (two weeks or less), Depends on, Gate (D design
  agreed, R independent review, G quality gate with recorded visual inspection,
  S screen gate, M merged and released, U my explicit approval), Merge request,
  Status (To do, In progress, In review, Blocked, Done), Iteration. Never
  "milestone"; no codes like A1 or T1.1: short readable names, then real issue
  links once published.
- **Source of truth:** `roadmap.json` holds the plan, the forge tracks it for the
  team, Orca runs it. `publish` only an agreed version, as a dry run first;
  `sync` is read-only and reports drift.
- **Orca:** start a worker only when every issue its issue depends on is Done.
  Begin each task title and worker brief with the issue's short name and link.
- **Issue done:** update the roadmap (or `sync --write`), re-render, and send me
  a short plain-language update: what finished, gate results, what is ready
  next, any divergence and why.
- **New work:** inside an agreed issue, just do it. Otherwise propose a roadmap
  change, show it rendered, and wait for my agreement.
- **Handoff:** the roadmap is the first thing the next session reads; include
  the latest `sync` drift report.
```

## 2. Feature & Bugfix Workflow: two new steps

In the numbered list under "Feature & Bugfix Workflow", add a step before
"Discovery & Understanding" and a step after "Finishing":

```markdown
0. **Program check**: if this work is part of a program, the roadmap must exist
   and be agreed before any worker starts, and this work must be an issue on it
   (`roadmap` skill). If it is not on the roadmap, propose the change and wait.
```

```markdown
7. **Issue done** (program work): update the roadmap, re-render it, and send a
   short update (`roadmap` skill).
```

## 3. Development conventions block

The development-loop installer manages this block (`scripts/install.sh` in the
development-loop skill). Its next version adds this bullet, so re-running the
installer applies it; there is no need to edit the block by hand:

```markdown
- For program work (several issues, workers or sessions toward one goal), invoke
  `roadmap` first: the roadmap must be agreed before any worker starts, workers
  start only when their issue's dependencies are Done, and each finished issue
  updates and re-renders the roadmap with a short update.
```

## 4. Codex-specific notes (only `~/.codex/AGENTS.md`)

Add `roadmap` to the list of installed skills in the existing bullet:

```markdown
- The skills referenced in these instructions (superpowers, codegraph, development-loop, cross-repo-completeness, roadmap, orca-cli, orchestration) are installed for Codex (plugins plus ~/.codex/skills).
```
