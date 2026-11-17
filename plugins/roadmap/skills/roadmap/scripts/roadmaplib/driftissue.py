"""drift-issue: keep one "Roadmap drift" issue on the forge in step with sync's drift report.

Created once when there is drift, updated in place (only the text between its
own markers), and closed when drift is zero. Only an open issue with that title
and marker block, opened by the token's own user, with no text outside the
block but the tool's intro, counts: anyone (or another workflow under the same
token's user) can copy the title and the markers around text of their own. It is the only issue the tool ever closes, and the close
re-reads the issue and checks its title, marker block and author first. When the sync report is incomplete (a forge call failed), nothing is
written: an incomplete report must not close the issue or rewrite it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import blocks, forge

TITLE = forge.DRIFT_TITLE
INTRO = forge.DRIFT_INTRO
skeleton = forge.drift_body


@dataclass
class Action:
    kind: str     # create-drift-issue, update-drift-issue, close-drift-issue
    detail: str


@dataclass
class Result:
    applied: bool
    actions: list[Action] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def text(self) -> str:
        head = "Applied." if self.applied else "Dry run: nothing was written. Run again with --apply."
        lines = [head] + [f"  {a.kind.replace('-', ' ')}: {a.detail}" for a in self.actions]
        if not self.actions:
            lines.append("  nothing to change")
        lines += [f"note: {n}" for n in self.notes]
        return "\n".join(lines)


def counted(report) -> list:
    """The drift the issue tracks: every kind someone can clear (sync.DRIFT_OWNER)."""
    from . import sync

    return [d for d in report.drift if d.kind in sync.DRIFT_OWNER]


def section(report, today: str) -> str:
    lines = [f"Drift found by `roadmap sync` on {blocks.md_inline(today)}:", ""]
    lines += [f"- **{d.kind}** {blocks.md_inline(d.target)}: {blocks.md_inline(d.message)}" for d in counted(report)]
    return "\n".join(lines)


def _mine(issues: list[dict], me: str | None) -> list[dict]:
    """Open drift issues the token's user opened. Anyone can copy the title and markers."""
    return [i for i in issues if forge.is_drift_issue(i, me)]


def _me(fg) -> str | None:
    try:
        return fg.current_user()
    except forge.ForgeError:
        return None


def run(raw: dict, fg, report, apply: bool = False, today: str = "") -> Result:
    result = Result(applied=apply)
    if report.errors:
        result.notes.append("the sync report is incomplete, so the drift issue was left as it is")
        return result
    project = fg.project
    if not project:
        raise forge.ForgeError('set forge "project" in roadmap.json: the drift issue lives there')
    me = _me(fg)
    if me is None:
        if apply:
            raise forge.ForgeError("could not read which user the token belongs to (GET user), so the drift issue "
                                   "cannot be told apart from a copy someone else opened; check the token")
        result.notes.append("could not read which user the token belongs to, so no existing drift issue is "
                            "trusted; with --apply this stops")
    issues = fg.all_issues(project)
    open_ones = _mine(issues, me)
    for other in issues:
        if forge.drift_lookalike(other) and other not in open_ones and me and other.get("author") == me:
            result.notes.append(f'{other["ref"]} has the "{TITLE}" title and markers but text this tool did not '
                                "write, so it is left alone; close it by hand if it is an old copy")
    if len(open_ones) > 1:
        result.notes.append(f'{len(open_ones)} open "{TITLE}" issues carry the marker; only '
                            f'{open_ones[0]["ref"]} is kept current')
    current = open_ones[0] if open_ones else None
    drift = counted(report)
    if not drift:
        if current:
            result.actions.append(Action("close-drift-issue", f"{current['ref']}: no drift left"))
            if apply:
                fg.close_drift_issue(current, me)
        return result
    content = section(report, today)
    if current is None:
        body = skeleton(content)
        result.actions.append(Action("create-drift-issue", f'"{TITLE}" in {project}, {len(drift)} items'))
        if apply:
            fg.create_issue(project, TITLE, body, None)
        return result
    old = current.get("body") or ""
    body = blocks.replace_block(old, blocks.DRIFT_START, blocks.DRIFT_END, content)
    hold = forge.command_hold(fg, body)
    if hold and _without_date(body) != _without_date(old):
        result.notes.append(f"{current['ref']} was not updated: {hold}")
    elif _without_date(body) != _without_date(old):
        result.actions.append(Action("update-drift-issue", f"{current['ref']}, {len(drift)} items"))
        if apply:
            fg.update_issue_body(current, body)
    return result


def _without_date(body: str) -> str:
    """The body with the run date left out, so a new date alone is not a change."""
    content = blocks.block_content(body, blocks.DRIFT_START, blocks.DRIFT_END) or ""
    return content.split("\n", 1)[-1]
