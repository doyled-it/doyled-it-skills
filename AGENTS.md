# Repository instructions

- This repo publishes composable skills. Route feature and bugfix work through
  `development-loop`, code understanding through `using-codegraph`, multi-repo
  design/audits through `cross-repo-completeness`, and program planning through
  `roadmap`. Invoke the upstream Superpowers stages they name; do not modify or
  vendor upstream Superpowers.
- Creating and syncing the index is mandatory: `codegraph status .`,
  `codegraph init .` if missing (without asking), then `codegraph sync .` before
  querying and after pulls, branch switches, and edits. The only exceptions are
  an explicit user no-index restriction and a prohibition on all writes;
  CodeGraph's own "indexing is the user's decision" text is tool guidance, not a
  user restriction. A source-read-only task still creates and syncs the index:
  `.codegraph/` is git-ignored and is not a source change. A typo or doc/config
  edit with no behavior change does not need an index. After querying, directly inspect unsupported files when an
  index is empty or partial. Markdown and shell need direct reads here.
- Keep policy consistent across skills, README, evaluation scenarios, and the
  managed conventions block in the legacy development-loop installer. Native
  plugin installation belongs to agentic-dev-setup; shared links are a fallback
  and must not duplicate native skills.
- Keep AGENTS.md canonical; CLAUDE.md imports it. Bump a modified plugin's
  `.claude-plugin/plugin.json` version above published/cached versions, and keep
  its description consistent with `.claude-plugin/marketplace.json`.
- Write meaningful regression tests first for behavior changes. Run
  `bash scripts/check.sh`; run `bash tests/codegraph_smoke.sh` when CodeGraph
  behavior changes. These checks need Bash, Node.js 18+, Python 3.11+, and
  ShellCheck; the roadmap tests run offline against recorded forge responses in
  `tests/roadmap/fixtures/` and a stateful fake forge (`tests/roadmap/fakeforge.py`;
  never record private forge content); the smoke check additionally needs the
  CodeGraph CLI and uv for scaffold validation.
- Roadmap safety rules any change must keep, each with a test: text the tool
  writes is neutralized (no line GitLab would run as a quick action, one-line
  titles), hand text holding such a line holds back only that one write, a
  description with broken markers (or markers only inside code) is reported and
  never written, tokens go only to their own host over https, gates D and U
  pass only from `approved_by` in roadmap.json, M only from a merged closing
  merge request in the roadmap's projects, nothing is deleted, and the only thing ever closed is the tool's
  own "Roadmap drift" issue (opened by the token's own user). The plugin's
  hooks never write, fail open, stay silent without a roadmap, and block a
  turn only on drift the agent can fix for issues that turn changed.
- Keep the standalone roadmap timeline offline and free of installed-app
  assets. Author icon overrides come from an explicit local option and render
  in an isolated image context. Preserve literal legacy attribution and raw
  history. New entries and synthetic summaries record their writer.
- Keep canonical mutations with the root orchestrator. Area coordinators
  reconcile through read-only sync and scoped deltas. Keep sync read-only while
  required gates are open. Hooks report proposed closures in that case as
  informational. Current worker counts, including scoped counts and zero,
  require timestamped activity evidence. Keep fixture replay, fresh-session
  workflow evaluation and native installation acceptance separate in release
  evidence.
- Preserve legacy Orca run inputs and use run-qualified identities for scoped
  tasks. Track requested and full task coverage separately. Hold absence-based
  drift checks and shared drift issue writes on incomplete full coverage.
  Missing worker evidence stays Unknown and leaves task coverage independent.
  Treat a recorded wrapper's run scope as binding on enclosed evidence.
  Require timestamped worker evidence in every run configured at capture time
  for a program-wide zero. Issue-scoped sync skips Orca, preserves the global
  snapshot and cannot update the shared drift issue.
  Keep wide tables and positioned gate labels inside named scroll regions.
  Verify visible focus, local keyboard scrolling and zero root scroll at 390 px.
- Follow the evaluation references for behavioral validation. Report which
  scenarios actually ran and distinguish deterministic checks, real CLI smoke
  checks, and fresh-agent behavior. Do not claim the last from the first two.
  Scenarios for `writing-software-docs` live in
  `plugins/nonfiction-superpowers/skills/writing-software-docs/references/evals.md`; consult
  them when revising that skill, never from the skill itself.
- Work on feature branches; use Conventional Commits and the owner identity Michael Doyle <michaeldoyle1994@gmail.com> (not a work or noreply address).
  Do not add coauthors. Remote writes require explicit user authorization.
- Ignore `.codegraph/`, `.superpowers/` and `.worktrees/`. Do not commit
  generated designs, plans, transcripts, private configuration, or internal
  source. Keep prose free of em dashes and emoji. Update these instructions with
  new repo conventions.
