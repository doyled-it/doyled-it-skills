---
name: roadmap
description: Use when orchestrating a program across issues, workers or sessions, before starting workers, or when asked to draft, render, publish, sync, update or hand off a roadmap.
---

<!-- diataxis: how-to -->

# Roadmap

Keep one `roadmap.json` agreed with the program lead. The JSON holds the plan,
the forge tracks real issues, and Orca records execution. On an existing program,
resolve the canonical file from an explicit program pointer or session context.
Carry that pointer across worktrees and hosts. Root (also called meta) is the
canonical writer and project coordinator. Give each active epic one lead for
its issues, dependencies, reviews and routine decisions. For delegated issue
coordination and shared ownership, read [coordination.md](references/coordination.md).
In Orca, also read [orca-operation.md](references/orca-operation.md) for placement,
mail and pending user decisions across turns. A program runs in three levels
(root, an epic lead per active epic, workers); [levels.md](references/levels.md)
says what each owns, decides alone and escalates.

| Word | Meaning |
| --- | --- |
| Roadmap | The agreed plan on one page. |
| Epic | A stream of related issues. |
| Issue | A deliverable of two weeks or less. |
| Depends on | Start only after these issues are Done. |
| Gate | A check required before Done. |
| Merge request | A reviewed change, called a pull request on GitHub and Forgejo. |
| Status | To do, In progress, In review, Blocked, Done. |
| Iteration | A fixed two-week period. |

Never say "milestone". Give work short readable names and genuine issue links
once published. The default gates are D (design agreed), R (independent review),
G (quality gate with recorded visual inspection), S (screen gate), M (merged
and released), and U (explicit lead approval). [Glossary](references/glossary.md)

## Run the command

Run `scripts/roadmap.py` by its full path in this skill's own directory, from
the project checkout that supplies the forge context, through the launcher:
`sh <skill dir>/scripts/python.sh <skill dir>/scripts/roadmap.py <command>`.
It runs a Python 3.11 or newer that uv already has, with
`uv run --no-project --no-python-downloads --python '>=3.11' python`, else `python3` only when it is 3.11 or newer
(macOS ships 3.9). It never downloads Python; otherwise it says what to install.
If the skill path is unavailable, look up the active installation with
`find ~/.claude ~/.codex ~/.agents -path '*roadmap/scripts/roadmap.py' 2>/dev/null`.
Use the loaded copy when several versions exist.

- `validate` checks the JSON. `render` makes the standalone roadmap page.
  `epic-preview` shows the generated forge section before its first write.
- `sync` reports drift read-only by default. `sync --write` saves derived
  status, gates, merge request links and worker observations locally. Inspect
  proposed changes before saving them.
- `publish` is a dry run by default. Use explicit authorization for forge writes
  such as `publish --apply`, `sync --update-epics` or `sync --update-drift-issue`.
  Authorization for the plan does not grant publication, merge or installation.

[Command reference](references/commands.md) · [Forge mapping](references/forges.md)

## Lifecycle

### 1. Program kickoff

Invoke `superpowers:brainstorming` with the lead to agree the goal, epics, issues,
dependencies and gates. Draft with `"agreed": false`, validate, and show the
rendered page. After agreement, record `agreed`, `agreed_by`, the new version
and a timeline entry. Ask the level question (model and effort per level, the
parallel epic cap) and record the answer as `orchestration.levels`. Share the
canonical path and preview with coordinators. No worker starts before this.
If publication is requested, show the dry run and an epic preview before
applying the authorized writes.
[Schema](references/roadmap.schema.json) · [Example](references/example-roadmap.json)

### 2. Each issue

Start work only when the issue is on the agreed roadmap and every dependency
is Done. Begin the task title and worker brief with the issue's short name and
link, such as `checked-citations acme/search#412`. The issue's epic lead is
level 2: it escalates consequential decisions to root and never asks the user
itself. Use `development-loop` for
design and implementation, resuming approved design and standing authority.
Keep its phases and gates at every delegation level. For UI work, use
`frontend-design` and record actual screen checks against the agreed acceptance
criteria; test results alone do not pass visual or screen gates.
Record D and U only from explicit lead approval in the JSON (`approved_by`,
`approved_on`, `passed`). A worker stopping or completing is a runtime event.
Use gate evidence to decide the issue's status.

### 3. Issue done

Orchestrators run `sync` at every update, read-only first. Root re-reads the
canonical JSON, applies supported changes and incoming deltas to that revision,
then validates, renders and checks the served page when reachable. Keep
independent progress and report missing forge or preview evidence as unknown.
Show what finished, which gates remain open, what is blocked, and what can
start next.

Check every required gate before setting Done. If a required gate remains open
on an issue affected by sync, keep that run read-only. Root saves only supported
changes, such as review evidence or a merge request link, in the latest JSON.
Keep the issue short of Done and dependent dispatch on hold. A project that
requires release for M needs release evidence before that gate can pass. Record
end-to-end acceptance and release separately from tests and review.

### 4. New work

Carry out work covered by an agreed issue. For a scope or dependency change,
show the proposed roadmap revision and get agreement before starting. Record
the agreed version.

### 5. Handoff

Start with the canonical path and preview, the latest drift report, active and
ready issues, blockers and open gates. Include source and evidence identities
such as issue link, reviewed revision, Run and task, and artifact paths. Keep
the original failures and regression evidence accessible.

## Write the timeline

Add an event when an outcome, decision, blocker, scope or gate changes. Give it
a short `title` that names the result and a brief `text` explaining what it
changes for the program and which gate is open. Put related repair, review or
test details in `children` when they explain the outcome. For example, title the
group "Export review passed" and say "The export can be staged. Release
verification is pending." A child can record the fix that addressed a failed
review and point to the recheck. Link bulky evidence and leave routine commit
chronology and unchanged benchmark results in those records.

Set explicit `author` on every new entry, including children and synthetic
summaries. Record who wrote each entry, independently of who did the work or
was mentioned. Preserve original text, failures, source markers, raw data and
unknowns when adding a summary. Keep old unattributed history neutral.
[Timeline fields](references/commands.md#timeline-fields)

## Enforcement and evaluation

See [enforcement.md](references/enforcement.md) for the merge request check,
scheduled drift issue and read-only hooks. Use [evals.md](references/evals.md)
to measure fresh-session behavior separately from command tests.
