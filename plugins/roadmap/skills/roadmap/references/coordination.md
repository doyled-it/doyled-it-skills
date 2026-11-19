<!-- diataxis: how-to -->

# Coordinate owners and previews

## Resolve scope and ownership

1. Resolve the canonical path and preview through the program pointer or
   inherited session context. Carry the same identity through child worktrees
   and host-specific paths. If the pointer is ambiguous, resolve it with root
   before writing or dispatching. Keep one canonical JSON and render from it.
2. Agree the scope of root (meta), area coordinators and workers, including any
   shared epic or issue ownership. Put routine inspected fixes and reviews with
   the closest owner. Route user decisions that exceed standing authority
   through root. Follow the sandbox. Permission or trust prompts that the
   platform refuses to delegate stay with the person in the original session.
3. Honor the user's and project's workspace preference for coordinators and
   workers. Before work starts, verify the launch receipt against the actual
   workspace and execution host. If they disagree, report the placement mismatch
   and hold that assignment until it is resolved.
4. Preserve agreed ownership in `orchestration.coordinators` and each epic or
   issue's `orchestrators` list. Use coordinator `parent` links for reporting
   relationships and `run` for task provenance. See the
   [ownership fields](commands.md#orca-ownership-and-coverage).

## Reconcile area updates

1. Read the latest accessible canonical revision and run read-only `sync`.
   Preserve its drift and errors. Associate forge records using genuine issue
   links. Record merge request links as evidence and leave absent issue
   mappings unknown. One command invocation covers one selected forge and can
   span the projects configured for it. Record gaps when another forge or a
   child host is unavailable. [Forge mapping](forges.md)
2. Send root an issue-specific delta with the base revision, issue ID and link,
   expected and proposed status or gate values, and evidence and timeline
   additions. Include unknowns and any conflict. Area coordinators use read-only
   sync. Root alone writes the canonical file or runs `sync --write` on it.
3. At root, re-read before applying deltas. Check only the addressed fields
   against their expected values. Preserve intervening edits to other fields
   and append new events to the current history. Check event IDs or evidence
   identity before retrying an append. Hold conflicting fields for reconciliation.

Use the [worker observations](commands.md#worker-observations) in read-only
`sync --json` for evidence of who was working. For each current worker total
or subtotal, record the scope and observation time. Count only confirmed
working workers. Report **Unknown** in structured output and prose for each
scope that lacks timestamped activity evidence. A numeric zero requires
timestamped coverage of that scope. Task lifecycle records describe task state
even when they carry timestamps. If an unread child Run makes coverage
incomplete, give the reason and keep the encompassing count Unknown. A scoped
run selection may have complete task coverage for that selection while the
roadmap's full coverage remains incomplete. Identify
tasks by Run and task ID and include parent and owner provenance where known.
Identify coordination activity by its observed purpose. Preserve historical and
unmapped tasks as recorded.

## Show the canonical preview in Orca

At root or area startup, resume, handoff or creation of a new area, use the
program's existing preview preference. In Orca, default to showing the
canonical page beside the orchestrator's own terminal, once per context.

1. Use the executable selected for this session to run `skills get orca-cli`
   and load `references/browser.md` as that guide directs. Use this
   version-matched guidance for command support and routing.
   Inspect the actual worktree, host and tabs with the supported context tools
   and `tab list --json`. Resolve the existing preview URL and known aliases
   on the browser host. A loopback URL refers to the host that opens it.
2. If the rendered page has no agreed browser-reachable URL, look for the
   project's supported private preview route. Use it when authorized and
   verified from the browser host. Have root record the verified URL and
   browser host in the shared pointer. If no route can be established, report
   the specific missing route or access and continue with the local render.
3. Reuse a verified adjacent canonical page by its page ID. If its content
   needs refreshing after render, use the supported reload on that ID.
   If the page already exists elsewhere in the context, check whether the
   installed tools can bring it alongside the terminal while preserving
   focus. Report a layout limit if they cannot.
   When the preview is absent, use the documented
   `tab create --url <verified-url> --split right --json` in the orchestrator's
   context. The supported split keeps terminal focus and reuses an adjacent
   browser pane when one exists. Use typed Orca commands and observed page IDs.
4. Verify the resulting URL, title and adjacency as the installed tools allow.
   If the host, workspace, layout or display cannot be verified, report the
   exact limit and continue independent work. Keep the preview private and
   credentials out of the page, URLs and output.

For delivery and handoff, report configuration, installation, discovery, skill
load and successful use separately. Record fresh-session and per-account host
checks as Unknown until observed. Acceptance of installer source is evidence
for that source and leaves native installation and use to their own checks.
