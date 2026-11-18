# Forges: how the roadmap maps onto GitLab, GitHub and Forgejo

`publish` and `sync` pick the forge from `--forge` when given, then `forge.kind`
in `roadmap.json`, then the checkout's `origin` remote: a `github` host means GitHub; a
`codeberg`, `forgejo` or `gitea` host means Forgejo; anything else means GitLab.
A self-hosted Forgejo with a neutral host name needs `"kind": "forgejo"`.

## The mapping

| Roadmap word | GitLab | GitHub | Forgejo, Gitea, Codeberg |
| --- | --- | --- | --- |
| Epic | Group epic in `forge.group` (`group&12`) | Parent issue (`owner/repo#12`) | Parent issue (`owner/repo#12`), optionally pinned; Projects have no API yet (see below) |
| Issue in an epic | The issue's epic is set | Sub-issue of the parent | Listed in the parent's generated task list |
| Issue | Project issue (`group/project#34`) | Issue | Issue |
| Depends on | Linked item, "is blocked by" | Issue dependency, "blocked by" | Issue dependency |
| Gate | Checklist line in the issue's generated section | Same | Same |
| Merge request | Merge request (`group/project!56`) | Pull request (`owner/repo#56`) | Pull request (`owner/repo#56`) |
| Pipeline | Merge request head pipeline | Combined commit status of the head | Combined commit status of the head |
| Status | Derived, see below | Derived | Derived |
| Iteration | Kept in the roadmap only | Kept in the roadmap only | Kept in the roadmap only |

Labels and milestones are never created or used on any forge. Status comes from
the forge's own state (open or closed, merge requests) plus an optional blocked
label the team already uses.

### Forgejo and Codeberg: why an epic is a parent issue, not a Project

Codeberg runs Forgejo, and Forgejo has Projects (kanban boards with columns at
repository and organization level). The preferred mapping would be Epic =
Project, Status = the issue's column, with the generated section in the project
description. **It cannot be automated today.** Checked on 2026-11-17 against
Codeberg's live API description (`https://codeberg.org/swagger.v1.json`, Forgejo
`17.0.0-100-2254cb0+gitea-1.22.0`, read-only requests only):

- There is no endpoint to list, create or edit a project, so the project
  description cannot be written.
- There is no endpoint to list, create or rename columns.
- There is no endpoint to add an issue to a project or to move it between
  columns, and the `Issue` object has no project or column field.
- The only project-related API surface is the repository switch `has_projects`
  (turns the Projects tab on or off) and read-only `project_id` and
  `old_project_id` fields on issue timeline events, which record moves made by
  hand in the web interface.

So for Forgejo, Gitea and Codeberg an epic is a **parent issue**: an ordinary
issue named after the epic whose generated section holds the flowchart, the
status table and a task list of the epic's issues. That task list is the
membership: `publish` writes it from the roadmap, and every write replaces it,
so a line someone adds to it by hand does not last. To put a new issue in a
Forgejo epic, mention the parent issue from it (for example "Part of #10"):
`sync` reads the parent's timeline as well as its task list and reports open
issues found either way that the roadmap does not list, until the roadmap
lists them. Status is derived from issue state and
pull requests, as on the other forges. With `"pin_epics": true` in `forge`,
`publish` also pins each parent issue on the repository's issue list
(`POST repos/:o/:r/issues/:n/pin`, after `GET repos/:o/:r/new_pin_allowed`
confirms a free slot), so the epics are easy to find without labels. Pinning
never unpins anything; when no slot is free the report says so.

If a later Forgejo release adds project and column endpoints, switch the
mapping: create one project per epic, write the generated section to its
description, put each issue on the board, and derive Status from its column.
Re-check the swagger file before relying on this note.

## How sync derives status

| Forge evidence | Status |
| --- | --- |
| Issue closed | Done |
| A blocked label (`blocked`, `status::blocked`, or `forge.status_labels.blocked`) | Blocked |
| An open, non-draft merge request | In review |
| An open draft merge request, or an in-progress label | In progress |
| Nothing new | Unchanged |

Status only moves forward from forge evidence (Blocked can move either way). If
the roadmap says Done but the forge issue is open, sync reports drift instead of
changing it.

## How sync ticks gates

Gates tick only from things that can be checked, never from a checkbox someone
added elsewhere in a description:

- **Lead gates** (D and U by default, or the roadmap's `lead_gates`) pass only
  when `roadmap.json` records the approval on the gate: `"passed": true`,
  `"approved_by"` and `"approved_on"`. `validate` refuses a passed lead gate
  without `approved_by`. A lead gate ticked on the forge is reported as
  `lead-gate-ticked-on-forge` drift and is not ticked.
- **Gates with a merge request rule** in `forge.gate_rules` tick only from
  that merge request, never from a checkbox. `mr_merged` (the default for M)
  ticks when a merged merge request in the roadmap's own projects closes the
  issue (`Closes #12`, `Fixes group/project#12`, or the issue's URL after a
  closing word the forge itself accepts: close, fix and resolve in their
  usual forms everywhere, and on GitLab also the -ing forms and "implements")
  or is named in the roadmap issue's own text (`!12`). On GitLab an issue's
  page has two forms, `/-/issues/12` and `/-/work_items/12` (the form its API
  returns from GitLab 17 on); either one counts, here and on the
  `Roadmap issue:` line. `mr_green` ticks when such a merge request has a green
  pipeline. A ticked `- [x] M: ...` line with no merged merge request ticks
  nothing. A rule cannot name a lead gate. (`mr_approved_green` was renamed
  `mr_green`: it never checked approvals.)
- **Other gates** (no rule, or the rule `checklist`) tick when their line in
  the generated checklist (inside the issue's markers, in the shape
  `- [x] R: ...`) is ticked. The first http or https link on that line is the
  evidence, otherwise the issue itself. Publish carries the same ticks, and only
  these, into the checklist it writes.

Merge requests in other projects that mention an issue are ignored for status
and gates, so a stranger's repository cannot move an issue or tick a gate. The
roadmap's own projects are `forge.project`, `forge.projects`, and each issue's
`project` and reference.

A tick is never removed by `publish` or `sync`.

## Generated sections

Two sections are written between hidden HTML comment markers; text outside them
is never changed. A marker counts only when it stands alone on its line and
outside code: marker text quoted in inline code, a fenced code block (three
backticks or tildes) or an indented code block is an example, never a marker.
When a description has a start marker without an end marker, two blocks, an end
marker before the start, a marker edited by hand, or a code block that never
closes (a new section would land inside it), nothing is written to it: `publish` lists it under "Needs a hand
fix" and `sync` reports `marker-problem` drift. Fix the markers on the forge,
then run the command again.

- **Issue** (`<!-- roadmap:start -->` to `<!-- roadmap:end -->`): the issue's
  short name, epic and dependencies, and the gate checklist.
- **Epic** (`<!-- roadmap:epic:start -->` to `<!-- roadmap:epic:end -->`): a
  link to the full roadmap page (`page_url`, or a note that the lead keeps it),
  the epic's note (written once: a new epic is created with this section, so the
  note is not also put above it), a Mermaid flowchart of the epic's issues with
  arrows to and from issues in other epics (dashed), status shown as color and
  as words, gate letters in each box, and a status table. On Forgejo it also
  holds the task list described above.

Links use the page URL the forge returns for each item, as given: on GitLab
19 that is `/-/work_items/N` for an issue and `/groups/<group>/-/epics/N` for
an epic.

GitLab, GitHub and Forgejo all render Mermaid in issue descriptions. Run
`epic-preview` to see the section locally before the first write.

## Access and credentials

- **GitLab:** `glab api` with the login `glab auth` already holds for that
  host. Epics need a GitLab tier with group epics. glab sends a token from the
  environment (`GITLAB_TOKEN`, `GITLAB_ACCESS_TOKEN` or `OAUTH_TOKEN`) to any
  host it is asked for, so when one is set the tool calls only the host named
  beside it: `GITLAB_HOST` (with or without `https://`), else `CI_SERVER_HOST`
  in GitLab CI, else `gitlab.com`. A different `forge.host` in `roadmap.json` is
  refused, not called. `GITLAB_HOST` with `http://`, or a glab login set to
  `api_protocol http`, is refused: https only.
- **GitHub:** `gh api` with the login `gh auth` already holds. Sub-issues and
  issue dependencies must be enabled for the repository. `GH_TOKEN` goes only to
  github.com; an enterprise token (`GH_ENTERPRISE_TOKEN` or
  `GITHUB_ENTERPRISE_TOKEN`) is used only for the host in `GH_HOST`.
- **Forgejo:** HTTPS REST API (`/api/v1`). Public reads need no token. A token
  is bound to its host, which is never taken from `roadmap.json` (a shared
  roadmap could name any host): `CODEBERG_TOKEN` is sent only to
  `codeberg.org`; `FORGEJO_TOKEN` (or `GITEA_TOKEN`) is sent only to the host
  named in `FORGEJO_HOST` (or `GITEA_HOST`) beside it. Requests use https only,
  a redirect to another host, port or to http is refused, and pages are read
  until `X-Total-Count` is reached (or an empty page), since a server may cap a
  page below the requested size. The token is read at call time and never
  stored, printed or logged.
- `forge.host` must be a bare host name (`gitlab.example.com`); `validate`
  rejects a scheme, path or user in it.

Every write passes a guard that refuses any delete, any close, and any title
that is not one line. The single exception is `drift-issue`, which may close
the tool's own "Roadmap drift" issue when drift is zero: that call re-reads the
issue, checks its title, its marker block and that the token's own user
opened it (anyone can copy a title and markers), and the guard accepts only a
bare close with no other change. On Forgejo, an issue that mentions a parent issue
counts as an epic member only when it is in the parent's repository.

### Forge commands in written text

GitLab runs a line such as `/close`, `/move` or `/label ~done` in an issue or
epic description as a quick action, also when the description is written
through the API. It runs only lines that start with the `/` (no indent) and sit
outside a fenced code block (three backticks), an HTML block and a `>>>` quote,
and only when the word after the `/` is one of GitLab's own command names
(`blocks.GITLAB_COMMANDS`, taken from GitLab's quick actions list). Prose such
as "/etc is full", a path such as `/usr/local/bin` and a title such as
"/api/v2 endpoints" are never commands. Everything the tool writes is neutralized first: a line shaped like a
command is written as `\/close`, which shows as `/close` and runs nothing.
Titles and names are written on one line, and the text they carry into a
generated section is escaped, so it cannot add a link, a hidden comment, a
marker or a task list line. `validate` rejects control characters in titles and
names and marker text anywhere.

Hand-written text outside the markers is kept byte for byte, so it is never
escaped. When it holds a line GitLab would run, publish lists that issue or epic
under "Needs a hand fix" and sync reports `quick-action` drift: nothing is
written to that one description (the dry run shows the same), every other write
goes ahead, and the run does not fail. Remove the line or put it in a code
block. As a last check the GitLab guard refuses any description with such a
line. GitHub and Forgejo have no command syntax in issue descriptions (GitHub's
slash commands work only in its web editor; closing keywords act only from
commits and pull requests), so their guard checks titles only, while the
written text is neutralized the same way on every forge.

## What each command calls

| Purpose | GitLab | GitHub | Forgejo |
| --- | --- | --- | --- |
| Read an issue | `GET projects/:id/issues/:iid` | `GET repos/:o/:r/issues/:n` | `GET repos/:o/:r/issues/:n` |
| Find same-title issues (open and closed) | `GET projects/:id/issues?state=all` | `GET repos/:o/:r/issues?state=all` | `GET repos/:o/:r/issues?state=all&type=issues` |
| Create an issue | `POST projects/:id/issues` (with `epic_id`) | `POST repos/:o/:r/issues` | `POST repos/:o/:r/issues` |
| Update the generated section | `PUT projects/:id/issues/:iid` | `PATCH repos/:o/:r/issues/:n` | `PATCH repos/:o/:r/issues/:n` |
| Epic membership | `PUT ...issues/:iid` with `epic_id` | `POST .../issues/:parent/sub_issues` | task list in the parent's section |
| Blocked-by links | `GET/POST .../issues/:iid/links` (`is_blocked_by`) | `GET/POST .../issues/:n/dependencies/blocked_by` | `GET/POST .../issues/:n/dependencies` |
| Epics | `GET/POST/PUT groups/:id/epics[/:iid]` | parent issue endpoints | parent issue endpoints |
| Merge requests of an issue | `GET .../issues/:iid/related_merge_requests` | issue timeline cross-references | issue timeline references |
| Pipeline | merge request `head_pipeline` | `GET .../commits/:sha/status` | `GET .../commits/:sha/status` |
| Open merge requests (drift) | `GET projects/:id/merge_requests?state=opened` | `GET repos/:o/:r/pulls?state=open` | `GET repos/:o/:r/pulls?state=open` |
| Pin a parent issue (optional) | not used | not used | `GET repos/:o/:r/new_pin_allowed`, `POST .../issues/:n/pin` |
