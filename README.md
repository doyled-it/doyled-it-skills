# doyled-it skills

A Claude Code marketplace of personal skills. The skills follow the Agent Skills open standard
(agentskills.io), so the same `SKILL.md` runs in Claude Code, Codex, and opencode.

## Writing

### nonfiction-superpowers

A superpowers-style system for writing nonfiction: a phased workflow with gates, built as a
sequence of composable skills. It is to prose what superpowers is to code.

For prose, start with **writing-nonfiction** (the orchestrator). For software documentation
(docs pages, READMEs, guides, reference, changelogs, release notes), start with
**writing-software-docs** instead. The nonfiction workflow runs the phases:

1. **Brainstorm** the premise, angle, and audience (uses `superpowers:brainstorming`).
2. **Design**: pin the form and a style sheet, then outline (`writing-a-researched-piece`,
   `structuring-web-nonfiction`).
3. **Research**: grounded and cited, nothing from memory.
4. **Draft** to the structure and the prose rules (`structuring-web-nonfiction`,
   `writing-human-prose`).
5. **Review**: an independent adversarial pass by fresh eyes (`reviewing-nonfiction`).
6. **Edit**: the mandatory proofread pass and the clean checks (`writing-human-prose`).

The skills in the plugin:

- **writing-nonfiction**: the orchestrator and entry point.
- **writing-a-researched-piece**: pin the form and style, outline, research, draft, review.
- **structuring-web-nonfiction**: the shape of a web piece: lede, nut graf, inverted pyramid,
  scannability (NN/g), honest data and charts (Knaflic, Cairo, Tufte), and a rule-set per form
  (essay, science, data, argument, archive, guide). Grounded in named sources.
- **writing-human-prose**: sentence craft (Orwell, Zinsser, Strunk & White, McPhee, Clark,
  Gutkind), the AI-tells blacklist, and the mandatory proofread pass.
- **reviewing-nonfiction**: the independent, adversarial review (fact-check, structure, data,
  craft, tells).
- **writing-software-docs**: technical documentation organized by reader need with the
  Diataxis framework (tutorial, how-to, reference, explanation): a placement plan first, one
  type per page, cross-links instead of repetition, and unconfirmed facts listed
  with visible markers where a needed step or cell has a gap. Its drafts are reviewed with
  `reviewing-nonfiction` in software-docs mode.

For an interactive data-story site, run `writing-nonfiction` for the research and prose and
`superpowers` for the implementation under one plan (see the "Combining with code" section in the
writing-nonfiction skill).

## Development

Four composable skills for writing code. **development-loop** is the orchestrator; it uses the
next two and the upstream superpowers skills, and **roadmap** for program work.

### development-loop

A disciplined loop for any feature or bugfix, single-repo or multi-repo: understand (codegraph) ->
brainstorm and design -> plan -> implement with TDD -> finish and verify the whole surface. It
does not fork the superpowers skills, it sequences them (so their updates flow through) and adds
two always-on habits plain prompting drops: ground understanding in codegraph, and verify a
change's full cross-repo surface. Invoke **development-loop** explicitly; it routes code
understanding to **using-codegraph**, multi-repo design and finish to
**cross-repo-completeness**, and the implementation stages to upstream Superpowers.
It includes inline execution when delegation is unavailable or prohibited.

### codegraph

Creating and syncing the CodeGraph index is mandatory: run `codegraph status .`,
`codegraph init .` if missing (without asking), then `codegraph sync .` before querying.
The only exceptions are an explicit user no-index restriction and a prohibition on all
writes; CodeGraph's own "indexing is the user's decision" text is tool guidance, not a
user restriction. A source-read-only task still creates and syncs the index: `.codegraph/`
is git-ignored and is not a source change. A typo or doc/config edit with no behavior
change does not need an index. Prepare each relevant sibling repo and worktree separately, verify the
project binding, and re-sync after pulls, branch switches, and edits. An index can be
empty or partial for unsupported file types; after querying, use direct inspection of
unsupported source and report the coverage limit. Never invent graph results.
Invoke **using-codegraph** for this sequence, including code-understanding questions.

### cross-repo-completeness

Map and verify a change's full surface across a multi-repo system, so it does not ship wired in
one repo and missing in the others (the API contract, client + types, UI, config, deploy, and
docs per repo). Two modes: **setup** (scaffold a project's seam map + per-repo pointers + MR
checklist, partly scripted) and **audit** (read each repo for a named change, walk the
end-to-end seam, report present/missing/undocumented slices). Pairs with the **codegraph** skill
as its per-repo engine.

### roadmap

<!-- diataxis: explanation -->

For program work (several issues, workers or sessions toward one goal): keep one roadmap agreed
with the program lead and work only from it. `roadmap.json` is the source of truth; the forge
tracks the work for the team and Orca runs it. One standard-library Python 3.11+ command
(`scripts/roadmap.py`) validates the roadmap (schema, dependency loops, dangling dependencies,
and the glossary: never "milestone", no codes like T1.1), renders it as one page (epic lanes,
issue boxes with status and gates, dependency arrows, a "right now" panel, issue tables and the
timeline, in light and dark mode), publishes an agreed version to GitLab, GitHub or Forgejo
(Codeberg) as a dry run by default, and syncs read-only to report drift: open issues the roadmap
does not list, merge requests and Orca tasks with no roadmap issue, and issues with nothing
behind them. Each epic description gets a generated section with a Mermaid flowchart and a
status table; `epic-preview` shows it locally first. Enforcement comes in three layers: merge
request templates, a `check-mr` CI job and a scheduled pipeline that keeps one "Roadmap drift"
issue current (the only thing the tool ever closes); Claude Code hooks that run a read-only sync
after a merge and block a turn that leaves drift the agent can fix on work it changed (Codex gets
a notifier); and the rule that orchestrators run sync at every update. **development-loop** calls it at step 0
(program check) and step 6 (issue done). The forge mapping, including why Forgejo epics are
parent issues rather than Projects, is in the skill's `references/forges.md`.

The roadmap skill guides authors to group related events under short outcome
titles. The standalone renderer displays the supplied titles, nested events and
writer labels. It works offline with built-in geometric marks, and
`--author-icon-dir` opts into local SVG overlays. A roadmap can record shared
ownership and coordinator hierarchy. Sync reads configured Orca runs and
reports task coverage and timestamped worker activity. The skill covers
root-only canonical writes, area deltas and preview reuse in Orca. See the
[command reference](plugins/roadmap/skills/roadmap/references/commands.md) and
[coordination guide](plugins/roadmap/skills/roadmap/references/coordination.md).

A program runs in three levels: the root session the user talks to, one epic
lead per active epic, and the workers each lead starts. The
[levels guide](plugins/roadmap/skills/roadmap/references/levels.md) says what
each level owns, decides alone and escalates, how it runs in Orca, and which
decisions reach the user. At kickoff, root asks for the model and effort per
level and the parallel epic cap, and records the answer in `roadmap.json` as
`orchestration.levels` for every later session. The command and hooks run
through `scripts/python.sh`: uv when it is installed, otherwise `python3` only
when it is 3.11 or newer (macOS ships 3.9).

Source checks, fresh-session workflow evaluation and native installation
acceptance each need their own evidence. Fresh-session and per-account host
acceptance for this workflow remain pending.

## Fabrication

### printable-parts

Functional checks for 3D-printed parts, layered on
[text-to-cad](https://github.com/earthtojake/text-to-cad) and composed by skill name,
never vendored. The text-to-cad DFM check validates walls, overhangs, and supports;
it deliberately does not check function. That gap shipped real defects: an inverted
countersink so a screw head could not seat, and a clip slot cut to 22 mm when its
parameters asked for 27. Both passed a file-format test and a DFM check.

**printable-parts** makes every functional feature a number checked on the exported
mesh itself. Start with the **printable-parts** skill; it composes text-to-cad's
`cad` and `print3d` skills in order. Its workflow:

0. A prior-art search (MakerWorld, Printables, Thingiverse) before modeling, with the
   decision (use as is, remix, or design new) recorded with links and licenses.
1. A measurable intent list per part, written before modeling and kept beside the model.
   Whenever the part touches a device, a reference model of that device (a five-tier
   source order) and an assembly fit check come before modeling too.
2. Model with the `cad` skill.
3. Export, then check every intent on the exported STL or 3MF (not just the model
   code), plus the cad printing DFM check. A failed intent loops back to modeling.
4. A stale-file guard: the expected dimensions come from the parameters, the measured
   ones from the mesh, so a parameter changed without a re-export fails in CI.
5. Snapshots plus a cross-section through every hole, slot, and pocket, for a person
   with no CAD software.
6. A test-fit coupon: a small, fast print of just the critical fit.
7. A print sheet: orientation, filament, Bambu Lab profile, what to measure off the plate.
8. A reviewer re-runs the checks and opens the cross-sections.

Deterministic work lives in bundled standard-library scripts (`stl_measure.py`,
`check_part.py`) that run in any repo's CI with `uv run` or `python3`.

The ordering is enforced in three layers: the skill as the soft entry point, a Claude
Code PreToolUse hook (`guard-printable-mesh.js`) that gates mesh export on an intent
file whose prior-art and reference-hardware records are complete, and slicing or
sending on a passing check record whose hash matches the mesh, and
the checks in the host repo's CI. The hook is Claude Code only; the hard per-command
gate is unavailable on Codex, opencode, and other runtimes, which get the soft layer
and the CI layer. The hook fails open on any error, never wedging an unrelated session.

## Tabletop

### dungeon-master-loop

A superpowers-style loop for running D&D 5e (2024) as a Dungeon Master. World-building
and session prep are two disciplines that feed each other: the world sets the initial
conditions, prep turns the current world state into a session that is fun to run, and what
happens at the table feeds back into the world. Most DM advice covers one step in
isolation. This plugin makes the loop explicit and passes named artifacts between the
steps, the way development-loop composes its phases.

Start with the **dungeon-master-loop** skill. It is the orchestrator: it defines the
artifact contract (setting canon, the Front, faction clocks, secrets and clues, hooks, the
party roster, the session plan, encounters, statblocks, the mini inventory, the print
manifest, and the session recap) and routes to nine sub-skills in a gated, two-pass order:

- **worldbuilding-initial-conditions**: set the world, the central pressure (the Front),
  the landing position, the cast, factions, and a pantheon, so play unfolds without a
  scripted plot. Carries a cited story-model reference (railroad versus sandbox).
- **session-zero**: safety tools and the bonds and wants that seed the world.
- **party-composition**: capture the roster and derive the encounter baseline, tactical
  gaps, and spotlight needs that everything downstream reads.
- **session-prep**: the Lazy Dungeon Master eight steps, plus non-combat (social,
  exploration, puzzle) challenge design, into a runnable session plan.
- **encounter-design**: planned fights tuned to party size and makeup with the 2024 XP
  budget, made interesting with objective, terrain, tactics, and pacing.
- **improvised-combat**: a fast path for a fight with no prep, reusing the combat core and
  preferring minis you own.
- **custom-monsters**: homebrew and reskinned statblocks for 5e 2024, with edition-labeled
  build math (the 2024 DMG has no create-a-monster table).
- **printable-minis-and-terrain**: tie prep to 3D printing on a Bambu Lab X2D, with a
  multi-session print lookahead, an owned-mini inventory, and proxy rules.
- **advancing-the-world**: after the session, capture the recap, write prep and table
  inventions into canon, tick clocks, roll secrets forward, and grow the Front.

The rules and research are system-agnostic methodology. A thin vault-binding reference maps
every artifact 1:1 to an example Obsidian vault layout. The suite ships as one plugin, so
install it project-scoped to keep the D&D skills out of unrelated sessions:

```bash
# run inside your D&D workspace (an Obsidian vault, a notes folder, or any repo)
claude plugin install dungeon-master-loop@doyled-it-skills --scope project
```

## Install with native plugins

For modern Claude Code and Codex, prefer
[agentic-dev-setup](https://github.com/doyled-it/agentic-dev-setup). It installs this
marketplace, upstream Superpowers, CodeGraph, and canonical global instructions. Use
its core install by default; its extended plugin set is optional. It does not crawl
unrelated workspaces. The agent closes index gaps in relevant repos during actual work.

For manual Claude Code installation, add both marketplaces and install the plugins:

```
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers@superpowers-marketplace
/plugin marketplace add doyled-it/claude-skills
/plugin install development-loop@doyled-it-skills
/plugin install codegraph@doyled-it-skills
/plugin install cross-repo-completeness@doyled-it-skills
/plugin install roadmap@doyled-it-skills
/plugin install nonfiction-superpowers@doyled-it-skills
/plugin install printable-parts@doyled-it-skills
```

The **dungeon-master-loop** plugin installs project-scoped instead (see Tabletop above),
so its ten D&D skills load only in your game workspace, not in every session.

Installing plugins exposes skills. Explicitly load the matching skill; mentioning a
name in a plan is not an invocation. Native names are
`development-loop:development-loop`, `codegraph:using-codegraph`,
`cross-repo-completeness:cross-repo-completeness`, and `roadmap:roadmap`. Shared fallback installs expose
the bare skill names. Use the runtime's skill loader, or read the SKILL.md when no
loader exists. Report unavailable skills and carry out the phase directly.

The development loop names each Superpowers stage: `superpowers:brainstorming`,
`superpowers:writing-plans`, `superpowers:test-driven-development`, and
`superpowers:subagent-driven-development` (or `superpowers:executing-plans` inline).
It also routes diagnosis, requesting/receiving review, verification before completion,
and branch finishing. Remote writes still require user authorization.

### Legacy shared-skills fallback

For a runtime without native plugin support that discovers `~/.agents/skills`, the
legacy fallback creates shared links. It refuses installation when `claude` or
`codex` on PATH supports native plugins because shared skills could appear beside
native copies. Use one installation method for each skill across runtimes that
share discovery paths. Do not hide a runtime from detection to bypass this guard.

```bash
bash scripts/install-skills.sh             # fallback links into ~/.agents/skills
bash scripts/install-skills.sh --copy      # fallback for filesystems without links
```

This does not install upstream Superpowers; install it using the fallback runtime's
supported method. Existing manual directories and foreign symlinks are preserved.
Copies are not refreshed on re-run. Links point to this checkout and require it to
stay in place. Old absolute `~/.claude/skills` links owned by this checkout are
removed when fallback installation runs; directories and foreign links are kept.

The development-loop legacy entry point updates only its managed conventions block
by default. It no longer installs native plugins, shared links, or the CodeGraph
CLI automatically, and it does not upgrade CodeGraph or register every detected
agent. Use the native setup for CLI installation and targeted registration.
For a shared-only runtime, install `@colbymchenry/codegraph` with npm and follow
`using-codegraph` for telemetry and registration. The former wrapper's
`--skip-codegraph` and `--keep-codegraph-telemetry` flags are retired; the native
setup has its own `--skip-codegraph` option and disables telemetry by default.

```bash
bash plugins/development-loop/skills/development-loop/scripts/install.sh
bash plugins/development-loop/skills/development-loop/scripts/install.sh --print-only
bash plugins/development-loop/skills/development-loop/scripts/install.sh --global-file "$HOME/.codex/AGENTS.md"
bash plugins/development-loop/skills/development-loop/scripts/install.sh --shared-skills
```

`--shared-skills` explicitly opts into the guarded fallback. Updates preserve text
outside the managed block and replace both historical manager labels. Malformed
markers fail without changing the file. `--print-only` has no installation side
effects. The legacy block is distinct from the setup repo's canonical instruction
block: review and remove the old managed block when migrating to that setup.

Before switching to native plugins, inspect `~/.agents/skills` and
`~/.claude/skills`. Remove only links/copies you recognize as these skills after
checking their targets or contents. Never delete manual skills or foreign links.
The native setup does not automatically clean historical fallback installations.
Refresh marketplaces and the three changed plugins after publication, then restart
the runtime to load their new versions. This branch is not installed by a remote
marketplace command until it is published; test a local plugin path for local edits.

## Validation

Run `bash scripts/check.sh` with Bash, Node.js 18+, uv or Python 3.11+, and ShellCheck
installed. It checks policy conflicts, plugin metadata, installer behavior in
disposable homes, the roadmap command against recorded forge responses, syntax,
and shell lint. No actual plugin installation or account configuration
is performed by those tests.

Run `bash tests/codegraph_smoke.sh` with CodeGraph and uv installed for real CLI
fixtures: cold and stale indexes, a hub with sibling indexes, an unsupported-only
repo, and scaffold idempotence. All generated files stay in an ignored temporary
directory in this repo. The fixture checks verify commands and artifacts; they do
not prove that a fresh agent selects or invokes a skill correctly.

Behavioral evaluation instructions are in each development skill's
`references/evals.md`. Record loader events or SKILL.md reads, commands, exit
status, actual symbol evidence, and user restrictions. Do not count a skill name
echoed in prose as a successful invocation or fabricate a fresh-agent run.

## Layout

```
.claude-plugin/marketplace.json
plugins/<plugin>/.claude-plugin/plugin.json
plugins/<plugin>/skills/<skill>/SKILL.md
scripts/install-skills.sh
```

## License

This repository is licensed under the GNU Affero General Public License v3.0 with the Commons
Clause condition prepended (see the `LICENSE` file). It is non-commercial, copyleft, and
source-available: you may read, run, modify, and share it, and any derivative you distribute must
stay under the same terms, but you may not sell it or offer it as a paid hosted service. The
Commons Clause makes it deliberately not OSI open source, because an OSI license cannot forbid
commercial use. Each plugin's `plugin.json` sets `"license": "SEE LICENSE IN LICENSE"` to point at
these terms.
