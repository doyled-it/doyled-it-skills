<!-- diataxis: reference -->

# The roadmap command

`scripts/roadmap.py`, standard library only, Python 3.11 or newer. It lives in
the skill's directory, not in the project: run it by its full path from the
project directory, `python3 <skill dir>/scripts/roadmap.py <command>
roadmap.json [options]` (SKILL.md says how to find the skill directory).

## validate

```bash
roadmap.py validate roadmap.json
```

Prints each finding as `error:` or `warning:` with where it is and why, then a
count. Exits 1 when there is any error. See [glossary.md](glossary.md) for the
rules. A field of the wrong type (an iteration name that is not text,
`allowed_terms` that is not a list of words, `orca` or `forge` that is not an
object) is a `bad-type` error, never a crash, and `publish`, `sync` and
`drift-issue` refuse to run, listing those errors, until it is fixed.

### Orchestration levels

`orchestration.levels` records the lead's answer to the kickoff level question
in [levels.md](levels.md). It is optional; once present, validate checks it.

| Field | Meaning |
| --- | --- |
| `program`, `epic` | Required. The choice for level 1 (the program orchestrator) and level 2 (each epic lead). |
| `worker` | Required. Level 3 choices by role: `implementer` and `reviewer` are required, `mechanical` and `final_reviewer` are usual, and other lowercase role names (such as `security_reviewer`) are named exceptions. |
| `parallel_epics` | Required. A whole number, 1 or more: how many epic leads run at once. The default answer is 2. |
| `answered_by`, `answered_on` | Optional nonblank text: who answered, and when. |

Each choice is an object with a nonblank `model` (the id or alias the agent
accepts) and optional nonblank `effort`, `agent` and `note`. A missing field is
`missing-field`, a misspelled key is `unknown-field`, and a wrong shape is
`bad-type`.

## render

```bash
roadmap.py render roadmap.json [-o page.html] [--author-icon-dir DIR]
```

Writes the one-page roadmap (default: `roadmap.html` next to the JSON). The page
has epic lanes with issue boxes (status and gates; filled gates have passed),
dependency arrows (dashed when they cross epics), a legend, a "right now" panel
(in progress or in review, blocked, ready to start, waiting on dependencies), an
issue table per epic (with merge requests, pipelines and gate evidence once sync
has recorded them), and the timeline. It works in light and dark mode and at
phone width, and every box is reachable by keyboard. Published issues, epics,
merge requests, pipelines and gate evidence all link to the forge.
Tab to a named table region to see its focus outline. Use the arrow keys to
scroll wide columns within that region.

With configured coordinators, the page shows ownership, parent and scope
details, and each owner's ready issues and open gates. Orca worker observations
have their own panel. If runs are configured and no snapshot is stored, that
panel shows Unknown.

Structural errors (missing fields, unknown epics, loops, dangling dependencies)
stop rendering. Glossary errors do not, so a draft can be shown before it is
fixed; they are printed as notes.

### Timeline fields

| Field | Meaning |
| --- | --- |
| `date`, `text` | Required strings. The date stays as recorded and the full text appears when expanded. Roots are stored oldest first and shown newest first. |
| `title` | Optional short text shown when collapsed. The renderer uses an excerpt when absent. |
| `author` | Optional writer identifier. The supported display labels are Claude (`claude`) and Codex (`codex`). On legacy records without the field, a literal leading `(Claude)` or `(Codex)` can supply attribution. Unknown writers display as Unattributed. The original text is preserved. |
| `children` | Related events of the same shape, displayed in recorded order. |
| `id`, `provenance` | Optional event identity and source metadata. |

`--author-icon-dir DIR` looks for `claude.svg` and `codex.svg` only in the supplied
directory. Relative paths resolve from the working directory. The renderer
validates the bytes it embeds. Each file must be UTF-8 XML with a namespaced SVG
root and no document type declaration. If the XML declaration names an
encoding, use UTF-8. Valid files become isolated data images. The 4 KiB file
limit keeps each repeated image small in long timelines. Missing, unreadable,
oversized or invalid files use the built-in marks. Labels stay visible. The
standalone page makes no automatic network requests.

## epic-preview

```bash
roadmap.py epic-preview roadmap.json --epic <epic-id> [-o preview.html] [--author-icon-dir DIR]
```

Writes a local page with the epic's generated section (rendered with mermaid.js)
beside the full roadmap page, plus the exact Markdown that would go between the
markers. The full page is written next to the preview as `<preview>-full.html`;
a file at either path that the command did not write is never replaced.
Nothing is written to the forge. The preview loads mermaid.js from jsdelivr,
pinned to version 11.4.1 and to the file's hash; it is the only third-party
request (the roadmap page itself makes none). Use it to show the program lead the
section before the first write to a real epic. The icon option applies to the
companion full roadmap.

## publish

```bash
roadmap.py publish roadmap.json            # dry run
roadmap.py publish roadmap.json --apply    # make the changes
```

| Option | Meaning |
| --- | --- |
| `--apply` | Write to the forge and save forge links back into `roadmap.json`. Without it nothing is written anywhere. |
| `--forge gitlab\|github\|forgejo` | Override the forge kind. |
| `--repo PATH` | Checkout whose `origin` remote picks the forge when `forge.kind` is not set. |
| `--recorded FILE` | Answer forge reads from recorded responses (tests and demos). |

Refuses a roadmap that is not agreed, or that has validate errors. On GitLab it
also refuses, in the dry run as well, an epic with no `ref` when `forge.group`
is not set: GitLab epics live in a group, so such an epic could not be created
(a project in a personal namespace has no group epics). The report
groups the changes into epics, issues and links and ends with a count. Linking
an existing item writes nothing to the forge, so an `--apply` run that only
links says "Applied: linked N existing items; no forge writes."

- An issue or epic without a `ref` is linked to an existing open forge item
  with the same title, and each forge item is linked to one roadmap item only.
  A closed issue with the same title is linked only to a Done roadmap issue: for
  unfinished work it is earlier work, so publish creates a new issue and names
  the closed one in the report (put it in `ref` if it really is this work).
  `validate` refuses two epics or issues with the same title or the same `ref`.
- A Done issue with no forge issue is skipped, not created: publish never
  closes anything, so a new open issue for finished work could never be closed.
- When a forge write fails part way, the report shows what was done and the
  error, the forge links of what was created are saved into `roadmap.json`, and
  the command exits 2. Run it again once the cause is fixed.

## check-mr

```bash
roadmap.py check-mr roadmap.json --from-ci                 # in a merge request pipeline
roadmap.py check-mr roadmap.json --title T --body-file F   # by hand
```

Exits 1 when the merge request names no issue on the agreed roadmap (or the
roadmap is a draft), 0 when it does, and 2 when it cannot read the merge
request. A merge request names an issue with its short name, its forge
reference (`#12` counts in the same project), or its URL; the templates put
these on a `Roadmap issue:` line and a `Closes #N` line. It warns, without
failing, when the issue's dependencies are not Done or the issue is already
Done. `--from-ci` reads GitLab CI (`CI_MERGE_REQUEST_TITLE`,
`CI_MERGE_REQUEST_DESCRIPTION`) or the pull request event of GitHub and
Forgejo Actions. No forge call is made. Setup:
[enforcement.md](enforcement.md).

A merge request that changes only the roadmap (`roadmap.json` and its rendered
`roadmap.html`) passes without naming an issue, even while the roadmap is a
draft: that is how the lead's agreed change, or the synced `roadmap.json` from
the scheduled job, gets merged. With `--from-ci` the changed files come from
git against the merge request's base commit (`CI_MERGE_REQUEST_DIFF_BASE_SHA`,
or the event's base commit), so the job needs the full history; by hand, list
them with `--changed PATH...`. A rename counts as a delete and an add, so
renaming code to `roadmap.html` is not a roadmap change. When git cannot list
the changed files, only the title and description are checked.

With `--from-ci` the agreed roadmap is read from that base commit, not from the
merge request: a merge request that adds an issue to `roadmap.json`, or sets
`"agreed": true`, and changes other files is judged against the roadmap as it
was before it. A base with no `roadmap.json` fails such a merge request, and a
base commit git cannot find (a shallow clone) exits 2. So does a pipeline in
which the forge gives no base commit at all: the only roadmap left would be the
merge request's own copy, which the check never trusts.

## drift-issue

```bash
roadmap.py drift-issue roadmap.json            # dry run
roadmap.py drift-issue roadmap.json --apply    # create, update or close it
```

Runs a read-only sync and keeps one issue titled "Roadmap drift" in
`forge.project` in step with its drift list: created once when there is drift,
updated in place (only the text between its own markers, and not for a new
date alone), and closed when drift is zero. It is the only issue the tool ever
closes: the close re-reads the issue and requires that title, the marker
block and the token's own user as author, and the write guard accepts only a
bare close. An issue a person titled "Roadmap drift" without the marker is
never touched. Text outside the marker block is kept as it is and does not
change which issue is the drift issue. When the token's user has several, the
oldest is kept current, and one note names every other open issue titled
"Roadmap drift", whoever opened it. When a forge call fails,
the report is incomplete and the drift issue is left as it is (exit 1). Takes
the Orca and forge options of `sync`. Incomplete Orca task coverage leaves
the drift issue as it is. The scheduled pipelines run it with
`--no-orca`, so their drift issue never lists the kinds that need Orca; see
[enforcement.md](enforcement.md).

## sync

```bash
roadmap.py sync roadmap.json [--write] [--json] [--update-epics] [--update-drift-issue]
```

| Option | Meaning |
| --- | --- |
| `--write` | Save reviewed status, gate ticks, merge request links and any changed Orca observation into the local `roadmap.json`. Root saves after review. |
| `--update-drift-issue` | Opt into creating, updating or closing the one "Roadmap drift" issue from this report, as in `drift-issue --apply`. Requires a program-wide sync. Combining it with `--only` exits 2 before any forge reads or writes. |
| `--update-epics` | Opt into rewriting the generated section in each published epic on the forge. Needs `--write`, an agreed roadmap and no validate errors. |
| `--json` | Print the report as JSON. |
| `--stale-days N` | No forge activity for N days is drift (default 14). |
| `--now DATE` | Measure staleness from this ISO date (default today). |
| `--orca-run RUN` | Read only this live run. By default, read the union of coordinator runs and the legacy `orca.run`. |
| `--orca-json FILE` | Read recorded Orca tasks and optional worker evidence offline. Takes precedence over `--orca-run`. |
| `--no-orca` | Skip Orca even if a file or run was supplied. Preserves a stored observation. |
| `--only IDS` | Check the comma-separated issue IDs. Skips epics, the scan for unlinked open merge requests, and Orca. Preserves the program-wide observation when saving. |
| `--forge`, `--repo`, `--recorded` | As for publish. |

Sync refuses a roadmap with structural errors (a dangling dependency, a loop,
a missing field). A failed forge read makes the report incomplete, prevents
saving, and exits 1. A missing issue is reported as `missing-on-forge` drift.
An epic write failure is reported separately and also exits 1. In that case
`--write` can still save the local updates. With `--write`, merge requests no
longer linked to an issue are removed from its record.

A closed forge issue can yield `Done`, and a qualifying merged request can
yield an M tick. When a required gate is open, including unverified release or
lead approval, root keeps this sync read-only and saves only supported updates
in the canonical JSON. Dependent dispatch stays on hold until the issue is Done
with all required gates met.

### Orca ownership and coverage

`orchestration.coordinators` maps local keys to optional `name`, `scope`, `run`,
`role` (`meta`, `area`, or `worker`) and `parent` fields. A parent names another
coordinator and parent chains must be acyclic. Epic and issue `orchestrators`
lists can each name one or more keys. Coordinators may share a run. Task
provenance uses the run and task ID where known. Legacy unqualified recordings
retain bare task IDs.

In `sync --json`, `orca_requested_complete` covers the requested task reads
and `orca_complete` covers all configured runs. Both are null when Orca is
skipped. A successful one-run override can have requested coverage while
full coverage is incomplete. Missing, failed or ambiguous reads can leave
coverage incomplete while other positive evidence still appears. A recorded
wrapper's run scope still governs its enclosed task evidence. Incomplete
full coverage suppresses `nothing-behind` and `no-recent-activity` and holds
all updates to the shared drift issue. Explicitly skipping Orca keeps the
forge-only drift check available.

### Worker observations

Live sync reads tasks with `orca orchestration task-list --run RUN --json`.
For started tasks carrying a `dispatchId`, it reads
`orca orchestration worker-show --dispatch ID --json` using the same executable.
Each dispatch is read at most once, with up to 5 seconds per read and a shared
15-second budget. A successful matching worker read receives a UTC timestamp.
Task lifecycle determines `started-early` drift. A working count requires
explicit `working` activity on a timestamped, nonterminal worker record.

`--orca-json` accepts a legacy task array, a task response, or a `runs` map
(at the root or in a successful `result`). Each run key maps to a task array
or task response. A flat recording can cover at most one configured run.
An optional `workers` map sits beside `runs` or the task list. Each key is a
dispatch ID. This example adds `observed_at` to the worker-show response.

```json
{
  "runs": {
    "run_search": [{"id": "task_rank", "status": "running", "dispatchId": "dispatch_rank"}]
  },
  "observed_at": "2026-11-19T19:15:40Z",
  "workers": {
    "dispatch_rank": {
      "observed_at": "2026-11-19T19:15:41Z",
      "ok": true,
      "result": {
        "runId": "run_search", "taskId": "task_rank", "dispatchId": "dispatch_rank",
        "state": "ready", "activity": "working"
      }
    }
  }
}
```

The report's `orca_observation` holds `source` (`live` or `recorded`),
capture-start `observed_at` (timestamp or null), `coverage_complete` (full
task coverage), `configured_runs` (the roadmap's run IDs at capture time),
and `workers`. Each worker has `run`, `task`, `dispatch`,
`activity`, `observed_at` and `owners` (coordinator keys mapped to parent
keys or null). Activity is `working`, `waiting`, `idle`, `queued`,
`stopped` or `unknown`. Missing or invalid worker evidence leaves activity
Unknown without changing task coverage. Run, dispatch and timestamp can
be null on Unknown rows. Capture and worker timestamps include a timezone.
With `--write`, the snapshot is stored at `orca_observation` in the roadmap.
Render displays that saved evidence at its recorded times. The confirmed
working count covers only timestamped working observations. A zero requires a
capture timestamp, full task coverage, at least one configured run and a known
timestamped worker observation from each configured run, with no Unknown worker
rows. Other runs retain their observations. Older snapshots without
`configured_runs` still display their timestamped evidence. Their program-wide
zero remains Unknown. See
[coordination.md](coordination.md#reconcile-area-updates) for reporting totals.

Drift kinds:

| Kind | Meaning | Who clears it |
| --- | --- | --- |
| `not-published` | A roadmap issue that is not Done, with nothing behind it on the forge. | the lead: publish |
| `missing-on-forge` | The roadmap names a forge issue that cannot be read. | the agent: fix the ref |
| `no-recent-activity` | No forge activity for `--stale-days` on an issue In progress or In review (To do and Blocked never go stale). | the team |
| `nothing-behind` | In progress or in review, with no merge request and no Orca task (needs Orca: not reported with `--no-orca`, so never by the scheduled pipelines). | the agent |
| `done-but-open` | Done on the roadmap, open on the forge. | the agent |
| `lead-gate-ticked-on-forge` | A lead gate (D or U) is ticked on the forge but not recorded in `roadmap.json`; it was not ticked. | the lead |
| `marker-problem` | A description's generated-section markers are broken; nothing was read from or written to that section. Fix it by hand. | the agent |
| `quick-action` | GitLab only: an epic's hand-written text has a line GitLab would run as a command (`/close`); the roadmap section was not written. Remove the line or put it in a code block. | the agent |
| `unlisted-epic-issue` | An open issue in a roadmap epic that the roadmap does not list. | the lead |
| `unlinked-merge-request` | An open merge request that no roadmap issue accounts for. | the team |
| `unlinked-orca-task` | An active Orca task whose title does not start with a roadmap issue's short name or link (needs Orca: not reported with `--no-orca`). | the team |
| `started-early` | A running Orca task for an issue whose dependencies are not Done (needs Orca: not reported with `--no-orca`). | the team |

The agent hooks block a turn only on the agent's kinds, and only for issues
that turn changed (see [enforcement.md](enforcement.md)); the drift issue
counts every kind.

A merge request counts as accounted for when the forge links it to a roadmap
issue, when it mentions a roadmap issue's reference or short name, or when the
roadmap's issue text names it (`group/project!12`, its URL, `!12` for the
default project, or `web !12` for the project whose path ends in `web`).
