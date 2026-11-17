# Glossary

These are the only words a roadmap, its updates, and the issues it publishes use
for planning. A program lead who does not know the code should be able to read
any of them.

| Word | Meaning | Forge term |
| --- | --- | --- |
| Roadmap | The agreed plan, on one page. `roadmap.json` holds it; `render` draws it. | none |
| Epic | A stream of related work that runs in parallel with other epics. | GitLab group epic; GitHub parent issue; Forgejo parent issue |
| Issue | One deliverable, two weeks of work or less. Bigger work becomes a child epic (`"parent"`) with its own issues. | Issue |
| Depends on | This issue cannot start until those issues are Done. | "Blocked by" |
| Gate | A check that must pass before an issue is Done, kept as a checklist line in the issue. | Checklist line |
| Merge request | A reviewed change. | GitHub and Forgejo: pull request |
| Status | To do, In progress, In review, Blocked, Done. | Derived from forge state |
| Iteration | A two-week sprint. | Kept in the roadmap only |

## Gates

| Letter | Gate |
| --- | --- |
| D | Design agreed with the program lead before building |
| R | Independent review, every finding fixed and re-checked |
| G | Quality gate with a recorded visual inspection of the output |
| S | Screen gate: every screen at every width, light and dark, accessibility checks |
| M | Merged and released |
| U | Explicit approval from the program lead |

A project may define its own gate set in `roadmap.json` under `"gates"`, as long
as each gate is one capital letter with a plain description.

## Rules `validate` enforces

- **Never "milestone".** Say Gate (a check) or Issue (a deliverable). This is an
  error anywhere in the roadmap's text.
- **No codes.** Ids are short readable names: lowercase words joined by hyphens
  (`checked-citations`, not `A1` or `t1-1`). Titles and epic names must not use
  codes such as `T1.1`, `E2` or `TE4`. After publishing, the forge link is the
  second name. Common technical words that look like codes (`S3`, `HTTP2`,
  `UTF8`, `IPv6`, `P95`) are fine; list others the program uses in
  `"allowed_terms"`.
- **No synonyms.** "Sprint", "ticket", "workstream" and "swimlane" are warnings:
  use Iteration, Issue and Epic.
- **Two weeks at most.** `estimate_days` above 10 is an error: split the issue
  into a child epic.
- **Well-formed entries.** Every epic and issue is an object, ids and titles
  are text, `depends_on` is a list of issue ids, `estimate_days` is a number,
  and each gate is one capital letter. A wrong type is an error, not a crash.
- **Real dependencies only.** A dependency on an issue that does not exist, or a
  loop of dependencies, is an error.

- **Plain links only.** Every link (issue and epic `url`, `links`, gate
  `evidence`, merge request and pipeline links, `page_url`) must be an `http`
  or `https` link. The page, the epic preview and the generated sections make
  no other link live.
- **Text the forge can show safely.** Titles, names, ids and gate descriptions
  are one line with no control characters; no text may look like a
  generated-section marker (`<!-- roadmap:`).

`validate` also warns when an issue is Done with a gate not ticked, and when work
started before the issues it depends on were Done.
