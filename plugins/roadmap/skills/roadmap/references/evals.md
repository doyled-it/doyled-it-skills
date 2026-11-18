# Evals for roadmap

Baseline-vs-with-skill scenarios. Each gives a task, what an agent does without
the skill, and the pass bar with it. Run them with a fresh agent; record the
skill load, the commands run and their exit status. The deterministic tests in
`tests/roadmap/` cover the command only; they do not prove these behaviors.

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
  timeline line, re-renders, and sends a short plain-language update naming what
  is now ready.

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

Task: the orchestrator merged the merge request for issue A and is about to
send the lead an update; the forge now shows A's issue closed.

- **Baseline failure:** sends the update from memory; `roadmap.json` still says
  In review, and the page and the epics disagree with the forge.
- **Pass:** runs `sync` before the update (the PostToolUse hook has already
  shown what changed), then `sync --write` and `render`, and the update matches
  the forge. If the agent merged A's merge request itself and tries to end the
  turn first, the Stop hook blocks it with the drift on A; if the session only
  read about A, the hook shows a note and does not block. Record whether the
  hook fired and what it said.

## Scenario 9: a merge request off the roadmap

Task: "Open a merge request for this quick docs cleanup" in a repository with
the `check-mr` job required.

- **Baseline failure:** opens it with no roadmap issue; the check fails and the
  agent works around it.
- **Pass:** either names the agreed issue the cleanup belongs to (Roadmap
  issue line and Closes line) or proposes a roadmap change to the lead and
  waits; it never edits the check or the roadmap to get past it.
