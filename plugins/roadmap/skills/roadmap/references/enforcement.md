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
A merge request cannot add its own issue to `roadmap.json`, or agree a draft,
and name it in the same change: the issue must be on the agreed roadmap before
the work's merge request is opened.

### Scheduled sync and the drift issue

A scheduled pipeline runs `sync --no-orca --write --update-epics` (the epics'
generated sections and statuses), then `drift-issue --no-orca --apply`, then
`render`. It keeps one issue titled "Roadmap drift" open and current while
there is drift, and closes it when drift is zero: the only thing the tool ever
closes. Every kind of drift counts, because each is something the lead, the
team or an agent can clear (the table of kinds in [commands.md](commands.md)
says who). Only an issue opened by the token's own user, holding nothing
outside its marker block but the tool's own intro, is kept current or closed.
A copy with the same title and markers, opened by someone else or holding other
text (another workflow can open issues under the same bot user), is left alone
and named in a note. `--apply` stops, and creates nothing, if the forge will
not say whose token it is. The one exception is the GitHub Actions workflow
token: GitHub answers its `GET /user` with 403 "Resource not accessible by
integration", and its issues are by `github-actions[bot]`; a rate limit, a
server error or no network stops the run like any other failure. Work that has
not started is not drift: a To do or Blocked issue never goes stale, and a Done issue that publish skipped is not "not
published", so an untouched backlog does not keep the issue open. The synced `roadmap.json` and page are job artifacts; the lead reviews
and commits them, since the pipeline never pushes.

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
  `gh issue close`, `tea` and `fj` equivalents), it runs a read-only
  `sync --only` for the roadmap issues the command names (or, when it names
  none, the issues In progress or In review) and tells the agent what changed.
- **Stop**: at the end of a turn it finds the roadmap issues the session's
  transcript names and runs `sync --only` for them. It blocks the turn only for
  an issue the session changed (one named in a git commit, push or merge, or a
  merge request or issue command it ran) and only for drift the agent can fix:
  roadmap.json behind the forge (a status or gate the forge now shows),
  `done-but-open`, `missing-on-forge` and `marker-problem`. Drift on an issue
  the session only named (by reading roadmap.json, running `validate`, or
  asking about it), and drift that needs the lead or the team
  (`lead-gate-ticked-on-forge`, `no-recent-activity`), is shown as a one-line
  note and never blocks. (`--only` skips Orca, epics and open merge requests,
  so `nothing-behind`, `started-early`, `unlisted-epic-issue` and
  `unlinked-merge-request` come only from a full `sync` or the drift issue.)

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
`codex-notify` mode that runs the Stop check and shows any drift as a desktop
notification (`osascript` on macOS, `notify-send` on Linux, or the command in
`ROADMAP_HOOK_NOTIFIER`). To use it, the lead adds this line to
`~/.codex/config.toml` (Codex appends its JSON payload as the last argument):

```toml
notify = ["python3", "<roadmap plugin directory>/hooks/roadmap_hook.py", "codex-notify"]
```

## Layer 3: the rules

The skill's lifecycle and the development-loop skill carry the rules: no worker
before the roadmap is agreed, work only from it, and orchestrators run `sync`
at every update (read-only, then `--write` and `render` when it shows changes),
so every short update matches the forge.
