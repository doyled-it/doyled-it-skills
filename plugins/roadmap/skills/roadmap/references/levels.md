<!-- diataxis: how-to -->

# Run a program in three levels

A program runs three levels deep. The top session keeps the whole program's
vision while epics move in parallel, and only consequential decisions reach the
user. Root, the epic leads and the workers in [coordination.md](coordination.md)
are levels 1, 2 and 3. The table is the default split, not a cage: the named
exceptions below are allowed, and anything else unusual goes up with a reason.

| | Level 1: program (root) | Level 2: epic lead | Level 3: worker |
| --- | --- | --- | --- |
| Is | The project's orchestrator session, the one the user talks to. | A worker of level 1, one per active epic. In Orca, a kept-open child worktree. | A worker or subagent of level 2. |
| Owns | The vision, the canonical `roadmap.json`, cross-epic interfaces and order, and every conversation with the user. | The epic's design, plan, issues, reviews and branch. | One task, one review or one fix round. |
| Brainstorms | The program: goal, epics, order and gates, at kickoff. | The epic's design, inside the program's agreed scope. | Nothing. It asks level 2 when the brief is unclear. |
| Decides alone | Routine coordination, placement, and when to start the next ready epic. | Routine calls inside the agreed spec, recorded as rulings. | Nothing outside its brief. |
| Escalates | To the user, through the user's question surface. | To level 1, for anything on the escalate list. | To level 2. |
| Does not | Implement or dispatch level 3 directly. | Talk to the user, edit another epic's interface, or write the canonical roadmap. | Start workers of its own. |

Named exceptions:

- Level 1 may make a one-line fix or run a read-only check itself.
- A program with one small epic may let level 1 act as its lead. Say so in the
  roadmap's timeline.
- The user may talk to a level 2 lead in its own pane. The lead acts on what the
  user said and tells level 1 in its next message, so root's record stays whole.

## What escalates

"Consequential" means this list. Level 2 sends it to level 1 with a
recommendation; level 1 answers from standing authority or asks the user.

- Scope or dependency changes, and anything that changes the agreed roadmap.
- Cross-epic interfaces.
- User-visible behavior the spec leaves open.
- Security or privacy.
- New dependencies or new cost.
- Anything irreversible or outward-facing: push, merge, publish, install,
  changes to the user's own configuration.

When in doubt, escalate with a recommendation. A routine call that turns out
to touch this list goes up before it ships, not after.

## Ask the level question at kickoff

At program kickoff, after the roadmap's goal and epics are agreed and before any
worker starts, level 1 asks the lead one question through the user's question
surface: which model and effort for each level, and the parallel epic cap.
Offer these defaults, described as tiers so they fit any agent:

| Role | Default |
| --- | --- |
| Level 1 | The most capable model, high effort. |
| Level 2 | A mid-tier model, high effort. |
| Level 3 implementers | A mid-tier model, medium effort. |
| Level 3 mechanical edits | The cheapest tier, for exact or same-shape edits. |
| Level 3 task and final reviewers | The most capable model. |
| Parallel epic cap | 2 |

If the user's own instructions already pin tiers, offer those as the default
answer and name where they came from. Record the answer in `roadmap.json` as
`orchestration.levels` ([fields](commands.md#orchestration-levels)), with who
answered and when, then validate:

```json
"orchestration": {"levels": {
  "program": {"model": "<id>", "effort": "high"},
  "epic": {"model": "<id>", "effort": "high"},
  "worker": {"implementer": {"model": "<id>", "effort": "medium"},
             "mechanical": {"model": "<id>"},
             "reviewer": {"model": "<id>"}, "final_reviewer": {"model": "<id>"}},
  "parallel_epics": 2, "answered_by": "<lead>", "answered_on": "<date>"}}
```

Every later session, brief and handoff reuses the recorded answer and does not
ask again. Pass the recorded model and effort explicitly when starting a
worker; never let it inherit the starter's model. A change of mind is a new
answer, recorded the same way.

## Fit ceremony to risk

Uniform ceremony makes a team slower than one person working directly: a cold
worker per task, the full suite after every task, the most capable reviewer and
a re-review for a rename, and mail latency on every step. Level 2 sizes each
task's ceremony when it plans the epic, and records the call as a ruling.

- **Risky tasks** keep the full loop: a fresh worker per task, the most capable
  reviewer, and a re-review after fixes. Risky means security, credentials,
  data migrations, user-facing UI and cross-epic interfaces.
- **Small or mechanical tasks** (renames, one-line fixes, same-shape edits,
  docs) are done by the lead itself or batched into one worker, with targeted
  tests and a review on a mid or cheap tier.
- The full check runs once per issue, before its review gate, not after every
  task.

Ceremony scales; gates do not. Every required gate still passes on its own
evidence, and R is still an independent review, only on a tier that fits.

## Add a merge steward when epics share a base

The merge steward is an optional role under level 1. Turn it on when two or
more epics or streams land on the same base branch; leave it off while one epic
is active. Level 1 starts it like a lead, on the recorded `epic` choice. It is
not an epic, so it does not count toward the parallel epic cap.

The steward queues merges in dependency order, rebases each branch onto the
current base, runs CI on the merged result, and keeps the base green. It
resolves routine conflicts itself, sends a conflict inside one epic to that
epic's lead, and sends a conflict across an interface to level 1. Merging is
outward-facing: the steward merges only under authority level 1 has recorded
for it, and every required gate still passes first.

## Keep questions and prompts on their route

- Level 2 never opens the user's question surface itself, even when it has one.
  It asks level 1. Level 1 asks the user and keeps a pending record as
  [coordination.md](coordination.md#keep-user-decisions-pending-across-turns)
  requires.
- A level 3 permission prompt can only be answered in that worker's own
  terminal. Level 2 denies a non-essential prompt there with a reason. For an
  essential one, it asks level 1 with the exact command and a recommendation.
  Level 1 takes it to the user, and the answer is applied in the worker's own
  terminal.
- Level 3 questions go to level 2, never to level 1 or the user.

## Run real tools only in a sandbox

Any brief that runs a real external tool (an agent CLI, an installer, anything
that reads the user's configuration) says how, and the worker follows it:

- Run the tool only as one `env -i HOME=<scratch> ...` command, so a failure
  earlier in a chain cannot run it against the real home. Print HOME first in
  that same command.
- Touch a stamp file before, and afterwards list files outside the scratch
  directory that are newer than the stamp. Report them by path and time.

```sh
scratch=$(mktemp -d) && touch "$scratch/.stamp"
env -i HOME="$scratch" PATH="$PATH" sh -c 'echo "HOME=$HOME"; exec <tool> <args>'
find "$HOME" -maxdepth 3 -newer "$scratch/.stamp" -not -path "$scratch/*" 2>/dev/null
```

The lead checks a "nothing changed" claim against those file times itself
before accepting the report. A claim without the listing is unverified.

## Run it in Orca

In Orca, also read [orca-operation.md](orca-operation.md).

1. Level 1 starts each level 2 lead with
   `orchestration worker-start --worktree new-child --name <epic> --keep-open`
   and the recorded level 2 model. The spec carries the canonical roadmap
   pointer, the epic's issues, standing authority, the escalate list and the
   recorded level 3 choices. Each epic has its own branch.
2. Check the child's branch and HEAD in the launch receipt and in the worktree
   itself. A new child can branch from the repository's default branch instead
   of level 1's HEAD. If the base is wrong, have level 2 confirm it has no
   commits of its own and reset onto the intended base before any work starts,
   or pass the base explicitly where the installed Orca supports it.
3. Level 2 runs `development-loop` for its epic: brainstorm inside the agreed
   scope, spec, plan, then subagent-driven development with level 3 workers,
   task reviews and a final review.
4. Questions climb with `orchestration ask` and answers come down with
   `orchestration reply`.
5. Level 2 sends level 1 a scoped delta with `orchestration send` when an issue
   changes status or a gate passes, and a short status when level 1 asks.
   Level 1 runs read-only `sync`, applies the deltas, renders, and keeps the
   preview beside its own terminal.
6. On resume, check that the preview actually shows. A tab that `tab list`
   still reports can be missing after an Orca restart; recreate it as
   [coordination.md](coordination.md#show-the-canonical-preview-in-orca) says.

At most the parallel epic cap of level 2 leads run at once (default 2) unless
the user raises it. When one epic finishes, level 1 starts the next ready one.

## Hand off

A long context hands off to a fresh session at its own level through
`orca-housekeeping`. The canonical roadmap pointer, the pending records and the
recorded `orchestration.levels` travel with the handoff. The new session reuses
them, keeps the same level's duties, and does not ask the level question again.
