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
rules.

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

- An issue or epic without a `ref` is linked to an existing forge item with the
  same title (open first, then closed), and each forge item is linked to one
  roadmap item only. `validate` refuses two epics or issues with the same title
  or the same `ref`.
- A Done issue with no forge issue is skipped, not created: publish never
  closes anything, so a new open issue for finished work could never be closed.
- When a forge write fails part way, the report shows what was done and the
  error, the forge links of what was created are saved into `roadmap.json`, and
  the command exits 2. Run it again once the cause is fixed.

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

| Kind | Meaning |
| --- | --- |
| `not-published` | A roadmap issue with nothing behind it on the forge. |
| `missing-on-forge` | The roadmap names a forge issue that cannot be read. |
| `no-recent-activity` | No forge activity on an unfinished issue for `--stale-days`. |
| `nothing-behind` | In progress or in review, with no merge request and no Orca task. |
| `done-but-open` | Done on the roadmap, open on the forge. |
| `lead-gate-ticked-on-forge` | A lead gate (D or U) is ticked on the forge but not recorded in `roadmap.json`; it was not ticked. |
| `marker-problem` | A description's generated-section markers are broken; nothing was read from or written to that section. Fix it by hand. |
| `unlisted-epic-issue` | An open issue in a roadmap epic that the roadmap does not list. |
| `unlinked-merge-request` | An open merge request that no roadmap issue accounts for. |
| `unlinked-orca-task` | An active Orca task whose title does not start with a roadmap issue's short name or link. |
| `started-early` | A running Orca task for an issue whose dependencies are not Done. |

A merge request counts as accounted for when the forge links it to a roadmap
issue, when it mentions a roadmap issue's reference or short name, or when the
roadmap's issue text names it (`group/project!12`, its URL, `!12` for the
default project, or `web !12` for the project whose path ends in `web`).
