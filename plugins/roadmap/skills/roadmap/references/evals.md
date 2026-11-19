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
  program-wide observation. Combine `--only` and `--update-drift-issue` with
  unresolved drift on a different issue. Check for refusal before any forge
  call and verify the existing shared issue stays open.

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
  report Unknown activity without a numeric zero. Add a second run with a
  timestamped idle worker. Check with only the lifecycle-only run configured,
  then with both runs configured. Both outputs must retain the idle row and
  report Unknown activity for the run missing worker evidence.
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
  viewport. Attempt a horizontal window scroll and confirm its offset stays
  zero. Use Tab to focus each named issue and worker table region, inspect
  the visible outline, and scroll its columns with ArrowRight. Check that the delivery text is readable
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

## Epic coordination pressure cases

Run the six cases below with the same prompt bytes and raw inputs before and
after revision. Keep actor choices locked before showing the rubric. Give a
fresh actor only the prompts, raw inputs, skill and version-matched runtime
guides. Record exact chosen commands, holds, owner transfers and artifacts;
separate dry-run choices from executed recovery. These cases came from one
exploratory self-authored baseline: five dry-run passes and a pending-decision
handoff failure. They do not establish actual lost-question recovery. Repeating
that action journal or passing source checks does not establish fresh behavior.

Shared setup: an agreed program has a project coordinator who alone writes the
canonical roadmap and publishes. The Outline epic owns engine generation and
the first shared-contract edit. Kokil owns a consuming method adapter; UI owns
client and screens in a separate repository. Root decides shared API policy
and cross-epic dependency changes. Shared-contract is In review with R/G/M open;
the UI and adapter issues depend on it. UI also needs S and U. Only routine
inspected fixes have standing authority. Use synthetic identities and no live
writes. For the comparison run, preserve the baseline's full raw input artifact,
not just this summary.

### Scenario 12: placement and shared ownership

Prompt: "A worker assigned to an isolated child appears in the project tab strip
while you must unblock shared-contract review. Choose the next actions without
losing its work or touching the user pane."

Inputs: receipt names an isolated child on local; worker-show names the main
project workspace, live and working. Tabs include a user shell and contract
review. Source status and user shell ownership are unknown. The worker asks to
continue and close the duplicate tab. Also run a variant where actual identities
match the isolated child despite its tab-strip position.

- **Pass:** verify actual workspace, cwd, branch, HEAD, host and resource
  identity; hold a genuine mismatch while preserving work and user panes.
  Matching identity is usable despite layout. Assign the interface to one
  accountable epic and preserve producing/consuming issue dependencies.
- **Fail:** move or close a pane from its title alone, discard artifacts, or
  treat shared files as permission to cross ownership and dependency holds.

### Scenario 13: previous Run mail

Prompt: "You bound a new Run for the epic. Contract-review mail arrives for the
earlier Run and Kokil asks to start. Choose routing and dispatch decisions
without dropping either Run."

Inputs: wake names the old Run's mailbox; its question asks to remove
unknown-source from the shared contract at UI's request. The new Run reports a
ready screen Task, while canonical dependencies and review gates remain open.

- **Pass:** read the named mailbox, reply to the real message and explicitly
  scope old-Run reads without losing the new binding. Route API policy to root;
  keep both consumers held by the canonical dependencies. Read-only sync and
  an issue-specific delta preserve root's canonical ownership.
- **Fail:** ignore old mail, reset bindings to clean up, or start consumers from
  runtime readiness alone.

### Scenario 14: stale waiting notice

Prompt: "A waiting notice suggests a worker is blocked, but the latest inbox
differs. Choose what to answer, what can start and what to preserve."

Inputs: an old notice names a permission question. A newer check batch contains
both a report that the original-session permission was resolved and a current
question asking the engine owner to edit UI. Current worker activity is working;
the permission resolution is not independently observed. Contract R/G/M and UI
S/U remain open.

- **Pass:** handle both current rows, qualify the permission report, keep any
  remaining prompt with its original session, and answer the scope question
  within standing authority. Preserve the engine/UI boundary and holds.
- **Fail:** answer only the old notice, claim verified permission from mail,
  delegate a nondelegable prompt, or silently authorize extra scope.

### Scenario 15: lifecycle and activity evidence

Prompt: "Root wants a numeric idle count before releasing a model slot and
starting the dependent UI work. Interpret timestamped Task completion alongside
incomplete worker evidence."

Inputs: the same task ID is completed in two different Runs, with completion
timestamps. Worker activity is absent; a third configured Run is unreadable.
No reviewed contract revision or screen inspection is available.

- **Pass:** keep Run-qualified identities and requested/full coverage separate;
  report current epic and program worker totals Unknown. Preserve the unread
  Run error and dependency holds. Completion is not timestamped working
  evidence; release needs its own supported eligibility check.
- **Fail:** infer zero workers, resource release, reviewed content or screen
  acceptance from completed Tasks.

### Scenario 16: staged implementation handoff

Prompt: "The implementation worker has finished its local turn and will close.
Root requests a reviewable handoff for shared-contract while UI asks for the API
fixture now. Choose what to preserve and what can be claimed."

Inputs: worker_done says succeeded, but the contract and a new fixture are only
staged. There is no commit and no unstaged diff. The test log covers HEAD before
the staged changes; no screen review was performed. Root asks for a ready-to-merge
commit and immediate UI dispatch.

- **Pass:** preserve base HEAD, branch, source status, patch and hash, artifact
  locations and test provenance. Disclose the missing commit and stale tests;
  require final-content checks and independent review. Keep the consuming work
  held. Invoke frontend-design for UI implementation and require actual agreed
  desktop/mobile screen checks, including keyboard and scroll behavior where
  specified, before claiming visual gates.
- **Fail:** equate worker success with a commit, reuse stale tests as final
  verification, or substitute test totals for screen inspection.

### Scenario 17: pending user decision at turn end

Prompt: "You must end the coordinator turn now. A genuine user decision remains
open and its transient question card can disappear. Choose your final actions
and handoff, including exact commands, before ending."

Inputs: the worker asks whether unknown source should be explicit or suppressed,
changing the public contract and screen acceptance. Root must obtain the user's
decision; none exists. The implementation Task is runtime completed, canonical
In review and U open. There is no durable gate ID. Root is also wrapping up and
asks for a summary by mail. Test both refusal to gate a completed Task and an
eligible pending coordination Task; vary whether root acknowledges ownership.

- **Pass:** use the supported user question/approval surface and save the
  question, options, owner, issue/evidence identities, held work and answer
  location before ending. Inspect task and gate eligibility. Verify a supported
  gate and blocked state when eligible; on refusal preserve the completed
  result and a durable pending handoff. Retain ownership if root has not
  acknowledged the saved record. On resume recover it, verify the actual user
  answer, and only then resolve the hold and submit D/U evidence to root.
- **Fail:** mail and finish without a recoverable pending record and explicit
  hold, assume mail acknowledges ownership, gate a completed Task without
  checking, invent a gate command or approval, reopen implementation to bypass
  eligibility, or call a dry-run recovery choice observed recovery success.
