"""drift-issue: keep one "Roadmap drift" issue on the forge in step with sync's drift report.

Created once when there is drift, updated in place (only the text between its
own markers), and closed when drift is zero. It is the only issue the tool ever
closes, and the close re-reads the issue and checks its title and marker block
first. When the sync report is incomplete (a forge call failed), nothing is
written: an incomplete report must not close the issue or rewrite it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import blocks, forge

TITLE = forge.DRIFT_TITLE
INTRO = ("This issue is kept by the roadmap tool's scheduled sync. It lists where the forge, Orca and the "
         "agreed roadmap disagree, and closes itself when they agree again. Edit the roadmap, not this section.")


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


def section(report, today: str) -> str:
    lines = [f"Drift found by `roadmap sync` on {blocks.md_inline(today)}:", ""]
    lines += [f"- **{d.kind}** {blocks.md_inline(d.target)}: {blocks.md_inline(d.message)}" for d in report.drift]
    return "\n".join(lines)


def _mine(issues: list[dict]) -> list[dict]:
    return [i for i in issues if i["state"] == "open" and blocks.one_line(i["title"]) == TITLE
            and blocks.block_content(i.get("body") or "", blocks.DRIFT_START, blocks.DRIFT_END) is not None]


def run(raw: dict, fg, report, apply: bool = False, today: str = "") -> Result:
    result = Result(applied=apply)
    if report.errors:
        result.notes.append("the sync report is incomplete, so the drift issue was left as it is")
        return result
    project = fg.project
    if not project:
        raise forge.ForgeError('set forge "project" in roadmap.json: the drift issue lives there')
    open_ones = _mine(fg.all_issues(project))
    if len(open_ones) > 1:
        result.notes.append(f'{len(open_ones)} open "{TITLE}" issues carry the marker; only '
                            f'{open_ones[0]["ref"]} is kept current')
    current = open_ones[0] if open_ones else None
    if not report.drift:
        if current:
            result.actions.append(Action("close-drift-issue", f"{current['ref']}: no drift left"))
            if apply:
                fg.close_drift_issue(current)
        return result
    content = section(report, today)
    if current is None:
        body = blocks.replace_block(blocks.md_block(INTRO), blocks.DRIFT_START, blocks.DRIFT_END, content)
        result.actions.append(Action("create-drift-issue", f'"{TITLE}" in {project}, {len(report.drift)} items'))
        if apply:
            fg.create_issue(project, TITLE, body, None)
        return result
    old = current.get("body") or ""
    body = blocks.replace_block(old, blocks.DRIFT_START, blocks.DRIFT_END, content)
    hold = forge.command_hold(fg, body)
    if hold and _without_date(body) != _without_date(old):
        result.notes.append(f"{current['ref']} was not updated: {hold}")
    elif _without_date(body) != _without_date(old):
        result.actions.append(Action("update-drift-issue", f"{current['ref']}, {len(report.drift)} items"))
        if apply:
            fg.update_issue_body(current, body)
    return result


def _without_date(body: str) -> str:
    """The body with the run date left out, so a new date alone is not a change."""
    content = blocks.block_content(body, blocks.DRIFT_START, blocks.DRIFT_END) or ""
    return content.split("\n", 1)[-1]
