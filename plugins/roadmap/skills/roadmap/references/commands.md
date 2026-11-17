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

## render

```bash
roadmap.py render roadmap.json [-o page.html]
```

Writes the one-page roadmap (default: `roadmap.html` next to the JSON). The page
has epic lanes with issue boxes (status and gates; filled gates have passed),
dependency arrows (dashed when they cross epics), a legend, a "right now" panel
(in progress or in review, blocked, ready to start, waiting on dependencies), an
issue table per epic (with merge requests, pipelines and gate evidence once sync
has recorded them), and the timeline. It works in light and dark mode and at
phone width, and every box is reachable by keyboard. Published issues, epics,
merge requests, pipelines and gate evidence all link to the forge.

Structural errors (missing fields, unknown epics, loops, dangling dependencies)
stop rendering. Glossary errors do not, so a draft can be shown before it is
fixed; they are printed as notes.

## epic-preview

```bash
roadmap.py epic-preview roadmap.json --epic <epic-id> [-o preview.html]
```

Writes a local page with the epic's generated section (rendered with mermaid.js)
beside the full roadmap page, plus the exact Markdown that would go between the
markers. The full page is written next to the preview as `<preview>-full.html`;
a file at either path that the command did not write is never replaced.
Nothing is written to the forge. The preview loads mermaid.js from jsdelivr,
pinned to version 11.4.1 and to the file's hash; it is the only third-party
request (the roadmap page itself makes none). Use it to show the program lead the
section before the first write to a real epic.

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

Refuses a roadmap that is not agreed, or that has validate errors. The report
groups the changes into epics, issues and links and ends with a count.

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
the Orca and forge options of `sync`. The scheduled pipelines run it; see
[enforcement.md](enforcement.md).

## sync

```bash
roadmap.py sync roadmap.json [--write] [--json] [--update-epics]
```

| Option | Meaning |
| --- | --- |
| `--write` | Save status, gate ticks and merge request links into `roadmap.json`. Never writes to the forge or Orca. |
| `--update-epics` | Rewrite the generated section in each published epic. The only forge write sync makes. Needs `--write`, an agreed roadmap and no validate errors. |
| `--json` | Print the report as JSON. |
| `--stale-days N` | No forge activity for N days is drift (default 14). |
| `--now DATE` | Measure staleness from this ISO date (default today). |
| `--orca-run RUN` | Orca run to read tasks from (default `orca.run` in the roadmap). |
| `--orca-json FILE` | Read Orca tasks from a file instead of the orca CLI. |
| `--no-orca` | Skip the Orca check. |
| `--forge`, `--repo`, `--recorded` | As for publish. |

sync refuses a roadmap with structural errors (a dangling dependency, a loop,
a missing field). When a forge read or write fails (a rate limit, a server
error), the report starts with "Incomplete" and lists the failures, nothing is
saved, and the command exits 1; an issue that does not exist is
`missing-on-forge` drift instead. With `--write`, merge requests no longer
linked to an issue are removed from its record. Only Orca tasks a worker is
running (`dispatched`, `running`) count as started; `ready`, `blocked` and
other queued tasks are waiting.

Drift kinds:

| Kind | Meaning | Who clears it |
| --- | --- | --- |
| `not-published` | A roadmap issue that is not Done, with nothing behind it on the forge. | the lead: publish |
| `missing-on-forge` | The roadmap names a forge issue that cannot be read. | the agent: fix the ref |
| `no-recent-activity` | No forge activity for `--stale-days` on an issue In progress or In review (To do and Blocked never go stale). | the team |
| `nothing-behind` | In progress or in review, with no merge request and no Orca task. | the agent |
| `done-but-open` | Done on the roadmap, open on the forge. | the agent |
| `lead-gate-ticked-on-forge` | A lead gate (D or U) is ticked on the forge but not recorded in `roadmap.json`; it was not ticked. | the lead |
| `marker-problem` | A description's generated-section markers are broken; nothing was read from or written to that section. Fix it by hand. | the agent |
| `quick-action` | GitLab only: an epic's hand-written text has a line GitLab would run as a command (`/close`); the roadmap section was not written. Remove the line or put it in a code block. | the agent |
| `unlisted-epic-issue` | An open issue in a roadmap epic that the roadmap does not list. | the lead |
| `unlinked-merge-request` | An open merge request that no roadmap issue accounts for. | the team |
| `unlinked-orca-task` | An active Orca task whose title does not start with a roadmap issue's short name or link. | the team |
| `started-early` | A running Orca task for an issue whose dependencies are not Done. | the team |

The agent hooks block a turn only on the agent's kinds, and only for issues
that turn changed (see [enforcement.md](enforcement.md)); the drift issue
counts every kind.

A merge request counts as accounted for when the forge links it to a roadmap
issue, when it mentions a roadmap issue's reference or short name, or when the
roadmap's issue text names it (`group/project!12`, its URL, `!12` for the
default project, or `web !12` for the project whose path ends in `web`).
