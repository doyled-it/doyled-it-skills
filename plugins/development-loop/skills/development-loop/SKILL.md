---
name: development-loop
description: Use when starting a feature, enhancement, or bugfix before writing code; when tempted to edit before understanding the repository; or when a change crosses backend, frontend, service, and deploy repositories.
compatibility: Composes upstream Superpowers plus using-codegraph, cross-repo-completeness, and roadmap for program work. Invoke namespaced plugin names when the runtime exposes them, or the bare skill names for a shared-skills fallback.
---

# Development loop

## Entry and routing

Invoke this skill explicitly for feature and bugfix work. In a native plugin
runtime its name is `development-loop:development-loop`; a shared installation
exposes `development-loop`. Use the skill loader the runtime provides, or read
the named SKILL.md when there is no loader. Merely mentioning a skill in a plan
does not invoke it.

Compose upstream Superpowers by name. Do not copy or modify its skills. If a
required skill is absent, report that limitation and carry out its phase directly.
Do not claim an invocation that did not happen.

A typo or doc/config edit with no behavior change may skip the design and plan
loop. A code-understanding question still uses `using-codegraph`; it simply does
not need an implementation plan. If scope and design are already approved, resume
the approved stage instead of asking for the same approval again.

## 0. Program check

If this work is part of a program (several issues, workers or sessions toward
one goal), invoke `roadmap` (native name `roadmap:roadmap`) first. The roadmap
must exist and be agreed with the program lead before any worker starts, and
this work must be an issue on it whose dependencies are Done. If it is not on
the roadmap, propose the change, show it rendered, and wait for agreement.
Orchestrate the program through the roadmap's levels reference (the roadmap
skill's `references/levels.md`): root, one epic lead per active epic, and workers, with
the model and effort per level recorded at kickoff. Work that is not part of a
program skips this step.

## 1. Understand

**REQUIRED SUB-SKILL:** invoke `using-codegraph` (native name
`codegraph:using-codegraph`) before locating or changing code. Creating and
syncing the index is mandatory: `codegraph status .`, `codegraph init .` when
missing (without asking), then `codegraph sync .` before querying. Confirm the
project path matches the current checkout. Sync again after pulls, branch
switches, and edits, and before handing exploration to another reader.

The only exceptions are an explicit user no-index restriction and a prohibition
on all writes. CodeGraph's own "indexing is the user's decision" text is tool
guidance, not a user restriction. A source-read-only task still creates and
syncs the index: `.codegraph/` is git-ignored and is not a source change. A typo
or doc/config edit with no behavior change does not need an index. If index
writes are prohibited, inspect source directly and report the unavailable graph
evidence.
An index may be empty or partial for unsupported file types. After querying,
use direct inspection for unsupported source and state the limitation; do not
invent graph results. Initialization covers the relevant checkout, not a crawl
of unrelated workspaces. Keep `.codegraph/` untracked through existing ignores or
an allowed local exclude; do not edit product files in source-read-only work.

For a multi-repo system, start from its hub (integration/deploy repo) with the
required sibling checkouts. Read the hub's `docs/cross-repo-features.md`, when
present. Invoke `cross-repo-completeness` (native name
`cross-repo-completeness:cross-repo-completeness`) to identify repos and seams,
and invoke `using-codegraph` in each relevant repo. Never assume the hub index
covers a sibling.

For a bug or unexpected test failure, invoke `superpowers:systematic-debugging`
before proposing a fix. Trace the cause and reproduce the behavior.

## 2. Brainstorm and design

**REQUIRED SUB-SKILL:** invoke `superpowers:brainstorming` for new work to refine
requirements and settle the design before implementation. Scale the design to the
task: a bounded change can have a short in-chat design; architectural work needs
the appropriate written specification. Follow user restrictions on saving or
committing generated planning documents.

For multi-repo work, use `cross-repo-completeness` at design time. List the real
surface per repo: producer and contract, consuming client and types, UI and docs,
configuration, deployment, and tests. Mark inapplicable slices N/A with reasons.

## 3. Plan

**REQUIRED SUB-SKILL:** invoke `superpowers:writing-plans`. Break the approved
design into independently testable tasks. Include every affected cross-repo slice
and give each touched repo its own branch. Link dependent PRs or MRs when remote
publication is authorized; track deferred slices explicitly.

## 4. Implement and review

**REQUIRED SUB-SKILL:** invoke `superpowers:test-driven-development` for
RED-GREEN-REFACTOR. Use each repo's actual test runner.

- When delegation is available and authorized, invoke
  `superpowers:subagent-driven-development` with its task reviews.
- When delegation is unavailable or the user requests inline work, invoke
  `superpowers:executing-plans`. Do not spawn agents against a user restriction.

Fit ceremony to risk. Risky tasks (security, credentials, data migrations,
user-facing UI, cross-repo or cross-epic interfaces) keep a fresh worker per
task, the most capable reviewer and a re-review after fixes. Do small or
mechanical tasks yourself or batch them into one worker, with targeted tests
and a cheaper review. Run the full check once per issue, before its review
gate. Required reviews and gates still apply at every size.

Run a real external tool (an agent CLI, an installer, anything that reads the
user's configuration) only from one `env -i HOME=<scratch> ...` command that
prints HOME first. Stop before it when the scratch directory or a pre-run stamp
cannot be made, or when HOME would not be the scratch directory. Afterwards list
every file under the real home newer than the stamp, at any depth; the roadmap
skill's levels reference has a script. Check a worker's "nothing changed" claim
against that listing before accepting it.

Invoke `superpowers:requesting-code-review` for the review gate. If no independent
reviewer is available, perform a separate self-review pass and disclose that
limitation. Invoke `superpowers:receiving-code-review` before acting on findings.
Verify each finding, fix material issues, and run the relevant tests again.

## 5. Verify and finish

Invoke `cross-repo-completeness` again in audit mode for multi-repo work. Trace the
actual producer-to-consumer path, including config, deployment, tests, and docs in
each affected repo. Tests passing in one repo do not establish the whole surface.
Report present, missing, undocumented, deferred, and N/A slices with evidence.

**REQUIRED SUB-SKILLS:** invoke `superpowers:verification-before-completion`
before success claims, then `superpowers:finishing-a-development-branch`.
Run fresh checks and inspect their exit status. Push or other remote writes require
user authorization; if absent, leave local commits ready and report that state.
Do not infer permission to merge from permission to push.

Update each repo's AGENTS.md when a change introduces a convention, interface, or
build/test command future work needs. A CLAUDE.md shim can import that canonical
file instead of maintaining two copies.

## 6. Issue done (program work)

When the work is a roadmap issue, finish it on the roadmap: run `roadmap.py sync`
(orchestrators run it at every update), tick its gates with evidence links, set
it Done (or run `roadmap.py sync --write`), re-render the page, and send a short
plain-language update: what finished, the gate results, and what is now ready to
start. See the `roadmap` skill.

## Installation and evaluation

For modern Claude Code and Codex, prefer the native plugin installer in
[agentic-dev-setup](https://github.com/doyled-it/agentic-dev-setup). Its global
instructions route tasks to `development-loop`, `using-codegraph`, and
`cross-repo-completeness`. Check the installed instruction block after upgrades;
auto-selection alone is not a reliable activation contract.

The bundled `scripts/install.sh` is a legacy fallback: it updates only the managed
global conventions block by default. `--shared-skills` explicitly enables shared
links for runtimes without native plugins. Do not combine shared links and native
copies of these skills. See the root README for migration and compatibility.

`references/evals.md` specifies observable pass/fail criteria. Deterministic repo
checks do not replace fresh-agent evaluation of invocation and task behavior.
