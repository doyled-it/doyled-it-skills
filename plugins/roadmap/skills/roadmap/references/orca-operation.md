<!-- diataxis: how-to -->

# Operate epic coordination in Orca

Use this reference only in Orca. Load `orca-cli` and `orchestration` from the
session's selected executable with `skills get`. Read the version-matched
reference for the action and its command `--help` before using unfamiliar
flags. The installed guides own syntax and recovery; this page supplies the
coordination checks. Keep roadmap gates distinct from Orca runtime gates.

## Verify placement and mail identity

- A tab strip shows layout. Compare the launch receipt with the actual
  worktree identity, execution host, terminal or agent identity, cwd, branch
  and HEAD. A tab in the project strip alone does not prove misplaced work.
  Hold a real mismatch and report exact identities before changing resources.
  Preserve user panes, staged work and artifacts. Load the installed placement
  and recovery references before a supported correction; never close an
  unknown pane or reset coordination state to tidy the display.
- Mail from an earlier Run still matters after a new Run is bound. Inspect
  and reply using its message and Run identities, explicitly selecting the
  earlier Run where needed without discarding the current binding. Inspect
  the current inbox and worker before acting on a stale waiting notice.
  Handle the whole returned batch before checking again. A reported permission
  resolution remains reported until observed; use the original prompt surface
  for any permission still pending.
- A completed Task or settled Dispatch describes lifecycle. Use timestamped
  working evidence and Run-qualified identities for activity counts, including
  zero, as [coordination.md](coordination.md) requires. Missing activity stays
  Unknown. Neither completion nor apparent idleness passes roadmap gates or
  authorizes resource release or dependent dispatch.

## Preserve a reviewable Git handoff

Before an implementation worker closes, capture workspace and host, branch,
HEAD, source status, staged and unstaged diffs, and untracked deliverables.
For staged-only work, preserve a patch and its hash alongside the base revision;
report that no commit exists. Tie tests and review to the actual content they
checked. Recheck final staged changes when earlier tests covered only HEAD.
Preserve the contract or fixture revision a consumer needs, but hold its
dependent issue until roadmap dependencies and gates pass. Use `frontend-design`
for UI work and retain actual screen inspection artifacts for its visual gates.

## Persist a user choice before ending the turn

Use the pending record in [coordination.md](coordination.md#keep-user-decisions-pending-across-turns).
The user-facing question must go through the supported question or approval
surface in the user's session. Coordinator mail carries the request and evidence;
a mail receipt proves storage, not user approval or accepted ownership.

Inspect the owning Run's current Task and pending gates before using
`gate-create`. Check eligibility and its receipt, rather than assuming a
completed Task can accept a blocking gate. When supported and within authority,
attach a decision gate to an eligible pending coordination Task and verify the
saved gate and hold with `gate-list` and `task-list`. A runtime gate records the
hold; it does not manufacture a user response or pass roadmap D/U.

If the Task is completed, the command refuses, or gate support is unavailable,
preserve the completed result. Save the pending record in the coordinator's
durable handoff with an explicit owner and blocked work; retain ownership until
root acknowledges its saved location. Request an authorized eligible
coordination Task from its owner if needed. Report an unconfirmed transfer and
leave the hold pending when root has not acknowledged it. Do not invent gate
commands, reopen finished implementation merely to attach a gate, or treat a
disappearing card as an answer. On resume, recover the pending record and verify
the user's decision before resolving the runtime hold and sending root evidence.
