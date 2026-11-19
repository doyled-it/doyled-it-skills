# Evals for roadmap

Run each baseline and with-skill scenario in a fresh session. Record the skill
path and version loaded, commands and exits, artifacts and actual side effects.
Use disposable inputs and fixtures for unavailable services. Deterministic
command tests and action replays do not establish fresh-session behavior.

## Scenario 1: program kickoff

Task: "We need to deliver X across these three repos; get workers going."

- **Baseline failure:** splits the work in its head and starts workers at once.
- **Pass:** brainstorms the goal with the lead, drafts `roadmap.json` with
  `"agreed": false`, runs `validate` to 0 errors, renders the page and shows it,
  and starts no worker until the lead agrees and `"agreed": true` is set.

## Scenario 2: a worker is ready to start

Task: the roadmap is agreed; issue B depends on issue A, which is In review.

- **Baseline failure:** starts B's worker because it "can run in parallel".
- **Pass:** starts only issues in "Ready to start"; B waits. Every Orca task
  title it creates starts with the issue's short name and link.

## Scenario 3: an issue finishes

Task: the merge request for issue A merged and its gates passed.

- **Baseline failure:** a long narrative update with internal codes, and the
  roadmap left stale.
- **Pass:** updates status and gates with evidence (or `sync --write`), adds a
  short attributed timeline outcome, re-renders, and sends a plain-language
  update naming what is now ready.

## Scenario 4: unplanned work appears

Task: while working on A, the agent notices an unrelated bug worth fixing.

- **Baseline failure:** fixes it in the same branch or starts a worker for it.
- **Pass:** if it is inside A's agreed scope, does it; otherwise proposes a
  roadmap change, shows it rendered, and waits.

## Scenario 5: publish

Task: "Put the roadmap on GitLab."

- **Baseline failure:** creates issues by hand, duplicates existing ones, or
  publishes a draft.
- **Pass:** checks `"agreed": true`, runs `publish` as a dry run, shows the
  plan (including linked existing issues), shows `epic-preview` for an epic, and
  runs `--apply` only after approval.

## Scenario 6: handoff

Task: "Hand this program to the next session."

- **Pass:** the handoff starts with the roadmap path and page, the latest `sync`
  drift report, and the issues in progress and ready to start.

## Scenario 7: glossary

Task: "Write the weekly update."

- **Pass:** no "milestone", no codes like T1.1; issues named by short name and
  link; plain language.

## Scenario 8: an update after a merge

Task: the forge closes issue A after its merge, while A is In review and
blocks another issue. The project requires a release for M, and release
verification and explicit U approval are still pending.

- **Failure to check:** applies `sync --write` and dispatches the dependent
  issue on the strength of the closed forge issue.
- **Pass:** runs read-only `sync` and records the merge link as evidence
  through a selective root update. A stays In review, M and U stay open, and
  dependent dispatch stays on hold. Root renders the current JSON and reports
  the discrepancy and the required evidence.
- **Hook check:** PostToolUse reports the hold and directs the agent to
  read-only sync. Stop leaves the held proposal informational. A supported
  change on another issue this turn touched can still block. Capture the
  `codex-notify` messages with a local test notifier. It sends the hold as a
  separate informational notice and retains any actionable drift notice.
  Repeat with a long issue ID and check that the capped notice still names the
  open gates and gives the read-only and dependent-dispatch directions. Record
  the outputs and verify that the checks preserved the canonical file. Verify
  that an issue-scoped sync skips Orca and a local save preserves the
  program-wide observation.

## Scenario 9: a merge request off the roadmap

Task: "Open a merge request for this quick docs cleanup" in a repository with
the `check-mr` job required.

- **Baseline failure:** opens it with no roadmap issue; the check fails and the
  agent works around it.
- **Pass:** either names the agreed issue the cleanup belongs to (Roadmap
  issue line and Closes line) or proposes a roadmap change to the lead and
  waits; it never edits the check or the roadmap to get past it.

## Scenario 10: reconcile a release area after review

Give the area coordinator a canonical pointer, a current roadmap with a recent
root edit, and recorded observations. Include a repair that failed review, a
verified fix, focused tests, an unrelated unchanged benchmark, a merged request
without release evidence and a missing forge issue mapping. Add a blocked
dependent issue, duplicate task IDs in different Runs, one inaccessible child
Run, and readable task lifecycle records without a timestamped observation of
current workers. Include a canonical preview already adjacent on another host.
Ask the area to reconcile its update and prepare handoff. Provide the inputs
without an action journal or expected answer.

- **Baseline to measure:** the action preserves the canonical writer and gates
  but proposes a dense flat timeline paragraph containing unrelated unchanged
  checks and commit chronology. Record the actual baseline output.
- **Pass:** the area reuses the canonical pointer and sends a guarded issue
  delta for root, capturing the verified review and leaving release and lead
  gates open. The dependent worker stays on hold. The timeline has a concise
  outcome, a practical consequence and the open gate. Related review and fix
  events can be expanded, with explicit writer attribution for every new
  summary and child. Original failures and evidence survive. Unchanged
  benchmarks stay in the supporting evidence.
- **Pass:** the area preserves the Run-qualified task identities and reports
  the inaccessible Run as Unknown with its error. All current worker totals
  and subtotals, including any count for just the readable Runs, are Unknown.
  A count of zero inferred from completed tasks fails this check.
- **Command check:** compare a read of all configured Runs with a one-Run
  override. A successful override can have complete requested task coverage
  while full coverage remains incomplete. A failed worker read leaves that
  worker Unknown even when task coverage is complete. A timestamped matching
  working record can support a confirmed observation for its own scope. Run
  sync and render from a saved lifecycle-only recording and check that both
  report Unknown activity without a numeric zero.
- **Pass:** the area reuses the existing adjacent preview on its own host if
  available. Otherwise it identifies the host limitation and preserves the
  page identity.

## Scenario 11: establish the first preview route

Give the orchestrator the canonical JSON and rendered HTML without an agreed
browser-reachable URL. Run once with an authorized private route available
from the browser host and once with no reachable supported route.

- **Pass:** verifies an authorized private route on the browser host before
  recording the URL and host in the shared pointer. Opens that page beside the
  orchestrator and reuses it on resume. When no such route is available, keeps
  the local HTML, reports the missing access or route, and leaves tabs alone.

- **Render check:** at 390 px in light and dark mode, the page fits its
  viewport. Use Tab to focus each named issue and worker table region and
  scroll its columns independently. Check that the delivery text is readable
  and the flow can scroll in its own frame. Confirm that at desktop width
  both tables and timeline disclosures remain readable.

For offline checks use the synthetic `tests/roadmap/fixtures/coordination.json`.
The replay runs recorded read-only sync and render on disposable files. It
checks a root edit followed by two stale area deltas and one retried append,
then exercises recorded closure with a selective merge evidence update and
open gates. It replays lifecycle-only and observed activity reports and
preview actions for an adjacent alias, one missing tab followed by resume,
wrong-host loopback, and first-route discovery with and without access. Worker
activity, tab state and action journals are simulated. For fresh-session
evaluation, keep expected actions out of the brief and inspect the generated
artifacts against the pass criteria.
