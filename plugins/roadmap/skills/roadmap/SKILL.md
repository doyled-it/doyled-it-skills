---
name: roadmap
description: Use when orchestrating a program of work across several issues, workers or sessions (Claude or Codex), before starting any worker; when kicking off a program, finishing an issue, sending a program update, taking on new work, or handing a program to the next session; or when asked to draft, render, publish or sync a roadmap.
compatibility: Reads the Agent Skills standard (Claude Code, Codex, opencode). The roadmap command needs Python 3.11 or newer (standard library only); publish and sync use glab for GitLab, gh for GitHub, and the REST API for Forgejo, Gitea and Codeberg. Sync reads Orca tasks through the orca CLI when it is present.
---

# Roadmap

## Overview

An orchestrator keeps one roadmap agreed with the program lead and works only
from it. It diverges only with the lead's approval, or for a genuinely good
reason stated in the next update. Updates are short and come when an issue is
done or a gate result arrives.

**Core principle: the roadmap is agreed before any worker starts, and every
piece of work traces back to one issue on it.** The failures this prevents are
workers started on unplanned work, plans that drift silently, and updates that
nobody can map back to a plan.

## Glossary (use these words exactly)

| Word | Meaning |
| --- | --- |
| Roadmap | The agreed plan, on one page. |
| Epic | A stream of related work that runs in parallel with other epics. On GitLab a group epic; on GitHub a parent issue with sub-issues; on Forgejo a parent issue whose generated section lists its issues. |
| Issue | One deliverable, two weeks of work or less. Anything bigger becomes a child epic with its own issues. |
| Depends on | This issue cannot start until those are Done. The forge calls it "blocked by". |
| Gate | A check that must pass before an issue is Done. A checklist line in the issue. |
| Merge request | A reviewed change. GitHub and Forgejo call it a pull request. |
| Status | To do, In progress, In review, Blocked, Done. |
| Iteration | A fixed two-week period of work. |

Default gates (a project may define its own set in `roadmap.json`): **D**
design agreed, **R** independent review, **G** quality gate with a recorded
visual inspection, **S** screen gate, **M** merged and released, **U** explicit
approval from the program lead.

Never say "milestone". Never use codes such as A1, T1.1 or E2 for work: give
each epic and issue a short readable name (`checked-citations`), and once it is
published, its real forge link. `roadmap validate` enforces both. Details:
[references/glossary.md](references/glossary.md).

## Where things live

- **`roadmap.json` is the source of truth** for the agreed plan
  ([schema](references/roadmap.schema.json), [example](references/example-roadmap.json)).
- **The forge** (GitLab, GitHub, Forgejo) is where the team tracks the work.
- **Orca** is where the work runs.

There is no two-way sync. `publish` pushes an agreed version out; `sync` reads
the forge and Orca back and reports what changed and what drifted. The full
roadmap page stays on the program lead's machine, and every issue, epic, merge
request and gate evidence item on it links to the forge.

## The command

One standard-library Python 3.11+ CLI, `scripts/roadmap.py`, in this skill's
own directory (next to this SKILL.md), not in the project. Run it by its full
path from the project directory: the path is the base directory this skill was
loaded from (Claude Code prints it when the skill loads; Codex shows the
SKILL.md path). If neither is shown, find it with
`find ~/.claude ~/.codex ~/.agents -path '*roadmap/scripts/roadmap.py' 2>/dev/null`.
The examples below write it as `scripts/roadmap.py`.

```bash
python3 scripts/roadmap.py validate roadmap.json          # schema, cycles, dangling dependencies, glossary
python3 scripts/roadmap.py render roadmap.json            # writes roadmap.html next to it
python3 scripts/roadmap.py epic-preview roadmap.json --epic <id>   # local preview of an epic's section
python3 scripts/roadmap.py publish roadmap.json           # dry run: lists every change, writes nothing
python3 scripts/roadmap.py publish roadmap.json --apply   # only for an agreed version
python3 scripts/roadmap.py sync roadmap.json              # read-only report: status, merge requests, drift
python3 scripts/roadmap.py sync roadmap.json --write      # also save status and gate ticks into roadmap.json
```

- `publish` refuses a draft (`"agreed": false`) and a roadmap with errors. It
  links issues and epics the roadmap names, and links an open issue or epic with
  the same title instead of creating a duplicate. It sets epic membership,
  blocked-by links and the gate checklist, writes forge links back into
  `roadmap.json`, and never closes or deletes anything.
- `sync` is read-only on the forge and Orca. Its only forge writes are the two
  opt-in flags: `--update-epics` rewrites only the generated section in each
  epic description, and `--update-drift-issue` keeps the one "Roadmap drift"
  issue current.
- Each epic description carries a generated section between hidden markers: a
  link to the full roadmap page, a Mermaid flowchart of the epic's issues with
  arrows to and from other epics, and a status table. Hand-written text outside
  the markers is never touched. Show the program lead `epic-preview` before the
  first write to a real epic.

Forge choice, the per-forge mapping and every flag:
[references/forges.md](references/forges.md) and
[references/commands.md](references/commands.md).

## Lifecycle

### 1. Program kickoff

1. **REQUIRED SUB-SKILL:** invoke `superpowers:brainstorming` on the program's
   goal with the program lead. Settle the epics, the issues, their dependencies
   and the gate each issue needs.
2. Draft `roadmap.json` with `"agreed": false`. Run `validate` until it reports
   0 errors.
3. Run `render` and show the lead the page (and `epic-preview` for an epic when
   publishing is planned).
4. Get explicit agreement. Only then set `"agreed": true`, `"agreed_by"`, bump
   `"version"`, and add a timeline entry. **No worker starts before this.**
5. If the team tracks work on a forge, run `publish` (dry run), show the plan,
   then `publish --apply` once the lead approves the writes.

### 2. Each issue

- Start an issue only when every issue it depends on is Done. The "Ready to
  start" panel on the page lists exactly those.
- An issue with a **D** gate goes through the development loop: invoke
  `development-loop` (native name `development-loop:development-loop`) for
  brainstorm, design, plan and build. Pass D only after the lead agrees the
  design, by recording it in `roadmap.json` (`"passed": true`, `"approved_by"`,
  `"approved_on"`). D and U never pass from a forge checkbox.
- Orca: begin every task title and worker brief with the issue's short name and
  link, for example `checked-citations acme/search#412: ...`. `sync`
  flags any active Orca task that does not, and any task started before its
  issue's dependencies were Done.

### 3. Issue done

Orchestrators run `sync` at every update: read-only first, then `--write` and
`render` when it shows changes, so the update matches the forge.

1. Every gate passed, with evidence (a link) for each.
2. Update `roadmap.json` (status, gates, a one-line timeline entry), or run
   `sync --write` to pull status and gate ticks from the forge.
3. Run `render` again.
4. Send a short update: what finished, the gate results, what is ready to start
   next, and any divergence with its reason.

### 4. New work

- Inside an agreed issue's scope: just do it.
- Anything else: propose a roadmap change (new issue, changed dependency, new
  epic), show it rendered, and wait for agreement before starting. Bump the
  version once agreed.

### 5. Handoff

The roadmap is the first thing the next session reads. Hand over the path to
`roadmap.json` and the rendered page, run `sync` and include its drift report,
and name the issues in progress and ready to start.

## Short updates

Run `sync` before each one. Plain language a program lead who does not know the
code can follow. Name work
by what it does and give its short name and link once. Example:

> `checked-citations` (acme/search#412) is Done: review passed (R), merged and
> released (M). `branch-citations` is now ready to start. No divergence.

## Enforcement

The forge checks every merge request names an issue on the agreed roadmap
(`check-mr` in CI, with merge request templates) and a scheduled pipeline keeps
one "Roadmap drift" issue current. In Claude Code, the plugin's hooks run a
read-only sync after a merge or close and block the end of a turn that leaves
drift the agent can fix on work the session changed; other drift is shown, not
blocked. Setup, and what Codex supports:
[references/enforcement.md](references/enforcement.md).

## Red flags

| Thought | Reality |
| --- | --- |
| "The plan is obvious; I'll start the workers and write it down later." | No worker starts before the roadmap is agreed. |
| "This small extra fix doesn't need to be on the roadmap." | Inside an agreed issue: fine. Otherwise propose it and wait. |
| "I'll call it T3.2 for now." | Short readable names only; validate rejects codes. |
| "Sync can just update the forge too." | sync is read-only; only `publish --apply`, `sync --update-epics` and `sync --update-drift-issue` write, and only with approval. |
| "I'll close the stale issues while publishing." | Nothing is ever deleted, and the only thing ever closed is the tool's own "Roadmap drift" issue once drift is zero. |

## Evaluation

[references/evals.md](references/evals.md) lists baseline-vs-with-skill
scenarios. Deterministic tests (`tests/roadmap/`) cover the command; they do not
prove that a fresh agent follows the lifecycle.
