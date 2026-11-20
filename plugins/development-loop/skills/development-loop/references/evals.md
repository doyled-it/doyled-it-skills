# Evals for development-loop

Baseline-vs-with-skill scenarios, so changes to the loop can be tested rather than
guessed. Each gives a task, the baseline failure (an agent WITHOUT the skill), and
the pass bar WITH it. Run the task in a real repo; the expected behavior is the bar.

## Scenario 1: feature in an unfamiliar codebase

Task: "Add feature X to this codebase" (one the agent has not seen).

- **Baseline failure:** greps/reads ad hoc to orient, then jumps straight to
  editing; no brainstorm/design, no plan, tests after (or none).
- **Pass:** orients with codegraph first (syncs, queries callers/impact), then runs
  brainstorming/design before coding, writes a plan of small testable tasks, and
  implements test-first.

## Scenario 2: a bugfix

Task: "Fix this bug" (a reported wrong behavior).

- **Baseline failure:** patches the first plausible spot (treats the symptom)
  without tracing the cause; may add a test after the fact that proves nothing.
- **Pass:** uses codegraph to trace the actual cause (callers/callees), reproduces
  it with a failing test first, fixes minimally, keeps the test.

## Scenario 3: a change that spans repos

Task: "Add a user-selectable option" in a multi-repo system (backend + separate UI).

- **Baseline failure:** implements and tests the backend only, calls it done; the
  frontend client/types/UI and docs are never touched, so users never see it.
- **Pass:** starts from the hub repo, maps the cross-repo surface with
  cross-repo-completeness at design, makes each slice a task, and at finish audits
  the surface and completes the MR checklist (API -> client -> UI -> docs).

## Scenario 4: a genuinely trivial change

Task: "Fix this typo in a comment / bump a config value."

- **Baseline failure (over-process):** spins up the full loop (brainstorm, plan,
  subagents) for a one-line change.
- **Pass:** recognizes the "not for" case and just makes the change; no loop, and
  no index build in an unindexed repo.

## Scenario 5: the codegraph CLI is not installed

Task: any feature or bugfix, where the first `codegraph status .` / `codegraph sync .`
returns `command not found` (with and without a `.codegraph/` directory; with npm,
and with installation prohibited or npm absent).

- **Baseline failure (observed 3/3 before the install guidance existed):** falls
  back to grep, or hunts for the binary and stops, citing "the skills don't give an
  install command, so I won't guess one" or "I won't curl-install an unverified tool".
  The "skip it when there is no `.codegraph/`" line gets read as permission to grep.
- **Pass:** installs from the named source (`npm install -g @colbymchenry/codegraph`)
  when permitted, turns telemetry off, then initializes and syncs the relevant
  index before querying. If installation is prohibited or npm is unavailable,
  reports the limitation and uses permitted direct inspection. MCP registration
  is separate and targets only the intended runtime. The historical 3/3 observation
  above concerns the earlier guidance, not this revised installation policy.

## How to run

For each scenario, give a fresh agent the task once without the skill and once with
it. Read the output: does the with-skill run orient via codegraph, design before
coding, test-first, and (scenario 3) cover the cross-repo surface, while scenario 4
stays lightweight? A regression is a with-skill run that reproduces a baseline failure.

## Scenario 6: cold repo and explicit invocation

Task: add a bounded feature in a disposable cold Python repo under time pressure.

- **Baseline failure:** skip the missing index or merely name skills in prose.
- **Pass:** load `development-loop:development-loop` and
  `codegraph:using-codegraph` (bare names for fallback), status/init/sync/query
  actual symbols, then load the applicable Superpowers stages. Record loader
  events or SKILL.md reads, not just an echoed skill name.

## Scenario 7: restrictions and unsupported files

Task A: understand an unindexed repo with an explicit user no-index restriction.
Task B: understand shell/Markdown with generated-index writes permitted.

- **Baseline failure:** initialize despite the restriction or invent graph results
  for unsupported files.
- **Pass:** A uses direct inspection without init/sync and reports unavailable graph
  evidence. B initializes, syncs, queries, observes an empty/partial index, then
  directly inspects unsupported files. All-write prohibitions override both init
  and sync. Source-read-only work does not edit product files to add ignores.

## Scenario 8: approved scope and prohibited delegation

Task: implement an already approved bounded fix with "Do not spawn agents."
Add pressure to skip tests because the apparent fix is only one line.

- **Baseline failure:** repeat design approval, spawn agents anyway, or patch first.
- **Pass:** resume the approved stage, load `superpowers:executing-plans` and
  `superpowers:test-driven-development`, reproduce a failing test, fix it, and
  perform a separate self-review. Disclose the lack of independent review. Load
  `superpowers:verification-before-completion` and
  `superpowers:finishing-a-development-branch`; leave local commits if no push
  was authorized.

## Scenario 9: complete invocation chain

Task: add a non-trivial capability with no design yet and delegation available.

Pass: the trace records actual loading of `superpowers:brainstorming`,
`superpowers:writing-plans`, `superpowers:test-driven-development`,
`superpowers:subagent-driven-development`, `superpowers:requesting-code-review`,
`superpowers:receiving-code-review` when findings arrive,
`superpowers:verification-before-completion`, and
`superpowers:finishing-a-development-branch`. Use
`superpowers:systematic-debugging` for bugs or unexpected failures. Multi-repo work
also loads `cross-repo-completeness:cross-repo-completeness` at design and finish
and prepares each relevant index. Report unavailable tools honestly.

## Scenario: work that is part of a program

Task: "Start a worker on the citations change" in a program with an agreed
roadmap, where that change depends on an issue that is still In review.

- **Baseline failure:** starts the worker at once, with a title that does not
  name a roadmap issue, and reports progress in internal codes.
- **Pass:** runs step 0: invokes `roadmap`, finds the issue on the agreed
  roadmap, sees its dependency is not Done, and waits (or proposes a roadmap
  change). When the issue later finishes, it updates and re-renders the roadmap
  and sends a short update (step 6).

## Scenario 10: ceremony fits the risk

Task: an approved plan with five tasks: two renames, a doc fix, a credentials
handling change, and a new settings screen. Delegation is available.

- **Baseline failure:** starts a fresh worker for every task, runs the full
  suite after each one, and sends the renames to the most capable reviewer with
  a re-review.
- **Pass:** does the renames and doc fix itself or batches them into one worker
  with targeted tests and a cheaper review; keeps a fresh worker, the most
  capable reviewer and a re-review for the credentials change and the screen;
  runs the full check once per issue before its review gate. No required review
  or gate is skipped.

## Scenario 11: a program runs in levels

Task: "Run this program across its three epics" with an agreed roadmap and no
recorded `orchestration.levels`.

- **Baseline failure:** dispatches every task from the top session on its own
  model, or opens the user's question surface from an epic lead.
- **Pass:** runs step 0, invokes `roadmap` and follows its levels reference:
  asks the kickoff level question through the user's question surface, records
  the answer, starts one epic lead per active epic within the parallel cap, and
  routes the leads' consequential decisions through root.

## Scenario 12: a worker says nothing changed

Task: a worker ran an agent CLI smoke test and reports "nothing changed" outside
its scratch directory. A chained command failed before its throwaway HOME was
set, and two files under the real home now have newer modification times.

- **Baseline failure:** accepts the report and moves on.
- **Pass:** checks file times outside the scratch directory against the run's
  start, finds the two files, rejects the claim and reports them. The brief for
  the rerun requires one `env -i HOME=<scratch> ...` command that prints HOME
  first, followed by the mtime listing at any depth.
- **Variant, the scratch setup fails:** `mktemp -d` fails before the run. Pass:
  the setup stops before the tool starts, and the lead treats any report from
  that run as unverified.
