# Enforcement: keeping work on the agreed roadmap

Three layers keep people and agents working from the agreed roadmap. The
forge layer works for everyone (people, Claude and Codex); the agent layer
catches drift before an agent finishes a turn; the rules tell agents what to
do. Install nothing into a project or into anyone's settings on your own: the
templates below are copied by the program lead or with their approval.

## Layer 1: the forge

### Merge request templates

Each template asks for a `Roadmap issue:` line and a `Closes #N` line.

| Forge | Template in this skill | Copy to |
| --- | --- | --- |
| GitLab | `templates/gitlab/merge_request_templates/Default.md` | `.gitlab/merge_request_templates/Default.md` |
| GitHub | `templates/github/pull_request_template.md` | `.github/pull_request_template.md` |
| Forgejo, Gitea, Codeberg | `templates/forgejo/pull_request_template.md` | `.forgejo/pull_request_template.md` (or `.gitea/`) |

### The roadmap command in CI

The CI jobs run the same standard-library command. Copy `scripts/roadmap.py`
and `scripts/roadmaplib/` from this skill to `tools/roadmap/` in the
repository (any Python 3.11+ image runs it; no packages are installed), and
keep `roadmap.json` at the repository root, or change the paths in the jobs.

### Merge request check

`roadmap.py check-mr roadmap.json --from-ci` fails a merge request that names
no issue on the agreed roadmap (see [commands.md](commands.md)). Ready-to-copy
jobs:

| Forge | Template | Copy to |
| --- | --- | --- |
| GitLab CI | `templates/gitlab/roadmap.gitlab-ci.yml` (job `roadmap-check`) | include it from `.gitlab-ci.yml` |
| GitHub Actions | `templates/github/workflows/roadmap-check.yml` | `.github/workflows/` |
| Forgejo Actions | `templates/forgejo/workflows/roadmap-check.yml` | `.forgejo/workflows/` |

To make it binding, require the job to pass before merging (GitLab: "Pipelines
must succeed"; GitHub and Forgejo: a required status check on the protected
branch). GitLab supplies the description to merge request pipelines as
`CI_MERGE_REQUEST_DESCRIPTION`; where an instance does not, the check sees only
the title, so put the issue's short name in the title. GitLab does not rerun the
pipeline when only the description changes, so after adding the missing
`Roadmap issue:` line, run the pipeline again (GitHub and Forgejo rerun on an
edit).

The way through for the roadmap itself: a merge request that changes only
`roadmap.json` (and `roadmap.html`) passes, even while the roadmap is a draft,
so the lead's agreed change and the scheduled job's synced roadmap can be
merged. The jobs read the changed files from git, which is why they fetch the
full history (`GIT_DEPTH: "0"`, `fetch-depth: 0`) and use an image with git.
Any other file in the same merge request needs a roadmap issue as usual, and a
renamed file counts as changed under both names.

The roadmap the check trusts is the one at the merge request's base commit.
When the forge gives no base commit, or git cannot find it, the check stops
with exit 2 rather than trust the merge request's own copy.
A merge request cannot add its own issue to `roadmap.json`, or agree a draft,
and name it in the same change: the issue must be on the agreed roadmap before
the work's merge request is opened.

### Scheduled sync and the drift issue

A scheduled pipeline runs `sync --no-orca --write --update-epics
--update-drift-issue` (the epics' generated sections and statuses, and the drift
issue, from one sync), then `render`. It keeps one issue titled "Roadmap drift" open and current while
there is drift, and closes it when drift is zero: the only thing the tool ever
closes. Every kind of drift counts, because each is something the lead, the
team or an agent can clear (the table of kinds in [commands.md](commands.md)
says who). The issue is found by its title, its marker block and its author:
only one opened by the token's own user is kept current or closed, and a copy
someone else opened is left alone. Text outside the marker block does not
matter: a note a person adds there is kept, and so is an intro worded by an
older release, and neither leads to a second issue. When the token's user has
several such issues (another workflow can open issues under the same bot
user), the oldest is kept current, even after a person adds a note to it, so a
later copy never displaces it. One note names every other open "Roadmap drift"
issue, whoever opened it, so one left behind by a token change or a broken
marker stays visible. `--apply` stops, and creates nothing, if the forge will
not say whose token it is. The one exception is the GitHub Actions workflow
token: GitHub answers its `GET /user` with 403 "Resource not accessible by
integration", and its issues are by `github-actions[bot]`; a rate limit, a
server error or no network stops the run like any other failure. Work that has
not started is not drift: a To do or Blocked issue never goes stale, and a Done issue that publish skipped is not "not
published", so an untouched backlog does not keep the issue open. The synced `roadmap.json` and page are job artifacts; the lead reviews
and commits them, since the pipeline never pushes.

The pipeline cannot read Orca: Orca runs on the lead's machine, not on the
forge's runners. So the three kinds that need Orca's task list,
`nothing-behind`, `started-early` and `unlinked-orca-task`, never appear in
the drift issue the pipeline keeps. They are reported only by a `sync` (or a
`drift-issue` run) without `--no-orca` on the machine where Orca runs, which
is the `sync` the orchestrator runs at every update. The pipeline does not
guess them instead: an empty task list would call every In progress issue
with no merge request yet `nothing-behind`. A drift issue written by such a
local `drift-issue` run lists them only until the next scheduled run, which
rewrites it without them (and closes it if they were all that was left).

| Forge | Template | Needs |
| --- | --- | --- |
| GitLab CI | `templates/gitlab/roadmap.gitlab-ci.yml` (job `roadmap-sync`) | a pipeline schedule with `ROADMAP_SYNC=1`; a masked project access token with `api` scope in `ROADMAP_BOT_TOKEN` |
| GitHub Actions | `templates/github/workflows/roadmap-sync.yml` | nothing extra: `GITHUB_TOKEN` with `issues: write` |
| Forgejo Actions | `templates/forgejo/workflows/roadmap-sync.yml` | an access token in the `ROADMAP_TOKEN` secret and the forge's host in the `ROADMAP_FORGE_HOST` variable (the token is sent only to that host) |

Before the first scheduled run, run `drift-issue` without `--apply` by hand
and show the lead what it would write.

## Layer 2: the agent

### Claude Code

The roadmap plugin registers two hooks (`hooks/hooks.json`, script
`hooks/roadmap_hook.py`); installing the plugin turns them on.

- **PostToolUse** (Bash): after a command that merges a merge request or
  closes an issue (`glab mr merge`, `gh pr merge`, `glab issue close`,
  `gh issue close`, `tea` and `fj` equivalents, run as commands, not quoted
  text), it runs a read-only
  `sync --only` for the roadmap issues the command names (or, when it names
  none, the issues In progress or In review), at most five of them with the
  rest named in a note, and tells the agent what changed.
- **Stop**: at the end of a turn it finds the roadmap issues this turn changed
  (named in a git commit, push, merge or tag, or a merge request or issue
  command it ran) and runs `sync --only` for at most five of them; the rest
  are named in a note. A turn that changed no roadmap issue makes no forge
  call, so reading roadmap.json, running `validate` or asking about an issue
  costs nothing. A command counts only when git or the forge CLI is the
  command itself, not text inside `echo`, `grep` or quotes. It blocks the turn
  only for actionable drift on those issues, such as a supported status or
  gate update, `done-but-open`, `missing-on-forge` or `marker-problem`.
  Drift that needs the lead or the team (`lead-gate-ticked-on-forge`,
  `no-recent-activity`) is informational. (`--only` skips Orca, epics and open
  merge requests, so `unlisted-epic-issue` and `unlinked-merge-request` come only from a full
  `sync` or the drift issue, and `nothing-behind`, `started-early` and
  `unlinked-orca-task` only from a full `sync` that reads Orca; see
  "Scheduled sync and the drift issue".)

When the forge proposes Done with required gates still open in the canonical
JSON, PostToolUse reports the hold. The proposal and any accompanying gate
ticks are informational for Stop. The message calls for read-only sync,
selective evidence updates through root, and holding dependent dispatch. An
actionable finding on changed work can still block the turn.

Both look for `ROADMAP_FILE`, else `roadmap.json` in the working directory or
at the git root, and do nothing and say nothing without one (a `roadmap.json`
without `epics` and `issues` lists belongs to another tool and is ignored).
Only with a roadmap present do they warn that Python is older than 3.11. They never write, never block
twice in a row, skip Orca, and stop after `ROADMAP_HOOK_TIMEOUT` seconds
(default 20). When the forge is slow or unreachable, or anything else fails,
they fail open: a one-line warning and no block.

### Codex

Codex's `notify` program runs after each turn and cannot block it or reach the
agent, so for Codex the forge layer is the enforcement. The same script has a
`codex-notify` mode that runs the same check for the issues the turn's messages
name (at most five). It sends actionable drift and a separate informational
notice for each closure held by an open required gate. Hold directions and
open gates precede the issue ID because notices are capped at 300 characters.
The desktop notifier is
`osascript` on macOS, `notify-send` on Linux, or the command in
`ROADMAP_HOOK_NOTIFIER`. To use it, the lead adds this line to
`~/.codex/config.toml` (Codex appends its JSON payload as the last argument):

```toml
notify = ["python3", "<roadmap plugin directory>/hooks/roadmap_hook.py", "codex-notify"]
```

## Layer 3: the rules

The skill's lifecycle and the development-loop skill carry the program rules.
Start workers only from the agreed roadmap. At each update, run read-only
`sync`. Root reconciles supported changes in the canonical JSON, renders it,
and reports any forge discrepancy and remaining gates.
