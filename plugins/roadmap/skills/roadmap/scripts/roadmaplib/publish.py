"""publish: put an agreed roadmap on the forge.

Creates or links epics and issues, sets epic membership and blocked-by links,
and keeps two generated sections current: the gate checklist in each issue and
the roadmap section (flowchart and status table) in each epic. It links an
existing issue instead of creating a duplicate, writes forge links back into
roadmap.json, and never closes or deletes anything.

Dry run by default: the report lists every change and nothing is written.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from . import blocks, model, validate


class PublishRefused(Exception):
    pass


@dataclass
class Action:
    kind: str     # create-epic, link-epic, update-epic, create-issue, link-issue, update-issue,
    #               add-to-epic, add-blocked-by
    target: str   # roadmap id of the epic or issue
    detail: str
    body: str | None = None
    payload: dict | None = None


@dataclass
class Report:
    applied: bool
    forge: str
    roadmap: dict
    actions: list[Action] = field(default_factory=list)
    changed: bool = False

    def add(self, kind, target, detail, body=None, payload=None):
        self.actions.append(Action(kind, target, detail, body, payload))

    def text(self) -> str:
        head = ("Applied: these changes were made on the forge." if self.applied else
                "Dry run: nothing was written. Run again with --apply to make these changes.")
        lines = [head, f"Forge: {self.forge}", ""]
        sections = (("Epics", ("create-epic", "link-epic", "update-epic")),
                    ("Issues", ("create-issue", "link-issue", "update-issue")),
                    ("Links", ("add-to-epic", "add-blocked-by", "pin-epic")),
                    ("Needs a hand fix (nothing was written to these)", ("hand-fix",)))
        for section, kinds in sections:
            rows = [a for a in self.actions if a.kind in kinds]
            if not rows:
                continue
            lines.append(section)
            for a in rows:
                lines.append(f"  {a.kind.replace('-', ' '):<16} {a.target}: {a.detail}")
            lines.append("")
        counts: dict[str, int] = {}
        for a in self.actions:
            counts[a.kind] = counts.get(a.kind, 0) + 1
        summary = ", ".join(f"{n} {k.replace('-', ' ')}" for k, n in sorted(counts.items())) or "nothing to do"
        lines.append(f"Summary: {summary}. Nothing is ever closed or deleted.")
        return "\n".join(lines)


def _placeholder(kind: str, rid: str, title: str) -> dict:
    return {"ref": None, "url": None, "id": None, "number": None, "title": title, "body": "",
            "new": True, "placeholder": f"new {kind} {rid}"}


def _write_back(raw_item: dict, forge_item: dict) -> None:
    raw_item.pop("issue", None)
    raw_item.pop("issue_url", None)
    raw_item["ref"] = forge_item["ref"]
    if forge_item.get("url"):
        raw_item["url"] = forge_item["url"]


def publish(raw: dict, fg, apply: bool = False, allow_draft: bool = False) -> Report:
    if not raw.get("agreed") and not allow_draft:
        raise PublishRefused("this roadmap is a draft; publish only a version the program lead agreed "
                             '(set "agreed": true once they have)')
    errs = validate.errors(validate.check(raw))
    if errs:
        raise PublishRefused("fix these first:\n" + "\n".join(str(e) for e in errs))

    out = copy.deepcopy(raw)
    data = model.normalize(raw)
    raw_epics = {e["id"]: e for e in out["epics"]}
    raw_issues = {i["id"]: i for i in out["issues"]}
    where = f"{fg.kind} ({fg.host or 'default host'}), project {fg.project or 'not set'}"
    report = Report(applied=apply, forge=where, roadmap=out)
    native_epics = getattr(fg, "native_epics", True)

    # Epics.
    epics: dict[str, dict] = {}
    for ep in data["epics"]:
        if ep.get("ref"):
            epics[ep["id"]] = fg.get_epic(ep["ref"])
            report.add("link-epic", ep["id"], f'{ep["ref"]} (named in the roadmap)')
            continue
        match = next((e for e in fg.open_epics() if e["title"].strip() == ep["name"].strip()), None)
        if match:
            epics[ep["id"]] = match
            report.add("link-epic", ep["id"], f'{match["ref"]} (open {fg.epic_word} with the same title)')
            _write_back(raw_epics[ep["id"]], match)
            report.changed = True
            continue
        report.add("create-epic", ep["id"], f'new {fg.epic_word} "{ep["name"]}"')
        if apply:
            created = fg.create_epic(ep["name"], ep.get("note", ""))
            _write_back(raw_epics[ep["id"]], created)
            epics[ep["id"]] = created
            report.changed = True
        else:
            epics[ep["id"]] = _placeholder(fg.epic_word, ep["id"], ep["name"])

    # Issues.
    issues: dict[str, dict] = {}
    fresh: set[str] = set()  # created in this run
    for it in data["issues"]:
        iid = it["id"]
        project = it.get("project") or fg.project
        epic = epics[it["epic"]]
        epic_name = next(e["name"] for e in data["epics"] if e["id"] == it["epic"])
        created_in_epic = False
        if it.get("ref"):
            fi = fg.get_issue(it["ref"])
            report.add("link-issue", iid, f'{it["ref"]} (named in the roadmap)')
        else:
            if not project:
                raise PublishRefused(f'issue "{iid}" has no project; set forge.project or the issue\'s project')
            match = next((o for o in fg.open_issues(project) if o["title"].strip() == it["title"].strip()), None)
            if match:
                fi = match
                report.add("link-issue", iid, f'{match["ref"]} (open issue with the same title)')
                _write_back(raw_issues[iid], match)
                report.changed = True
            else:
                body = blocks.issue_body(data, it, it["detail"], epic_name)
                report.add("create-issue", iid, f'"{it["title"]}" in {project}, epic "{epic_name}"', body=body)
                if apply:
                    fi = fg.create_issue(project, it["title"], body, epic if not epic.get("new") else None)
                    _write_back(raw_issues[iid], fi)
                    fresh.add(iid)
                    report.changed = True
                    created_in_epic = bool(native_epics and epic.get("id"))
                else:
                    fi = _placeholder("issue", iid, it["title"])
                    created_in_epic = True
        issues[iid] = fi

        if not fi.get("new") and iid not in fresh:
            try:
                body = blocks.issue_body(data, it, fi["body"], epic_name)
            except blocks.MarkerError as exc:
                report.add("hand-fix", iid, f'{fi["ref"]}: {exc}')
                body = fi["body"]
            if body != fi["body"]:
                report.add("update-issue", iid, f'gate checklist in {fi["ref"]}', body=body)
                if apply:
                    fg.update_issue_body(fi, body)

        if created_in_epic:
            continue
        if epic.get("new") or not fg.in_epic(fi, epic):
            epic_label = epic.get("ref") or epic.get("placeholder")
            how = "listed in the epic's generated section" if not native_epics else "set the epic"
            report.add("add-to-epic", iid, f"{fi.get('ref') or fi.get('placeholder')} into {epic_label} ({how})")
            if apply and native_epics:
                fg.add_to_epic(fi, epic)

    # Blocked-by links.
    for it in data["issues"]:
        fi = issues[it["id"]]
        existing = set() if fi.get("new") or it["id"] in fresh else fg.blocked_by(fi)
        for d in it["depends_on"]:
            dep = issues[d]
            if dep.get("ref") and dep["ref"] in existing:
                continue
            src, target = fi.get("ref") or "new issue", dep.get("ref") or "new issue"
            report.add("add-blocked-by", it["id"], f"{src} is blocked by {target}: {d}")
            if apply:
                fg.add_blocked_by(fi, dep)

    # Optional: pin parent issues so a Forgejo epic is easy to find (it has no Projects API).
    if getattr(fg, "pin_epics", False):
        slots = fg.can_pin()
        for ep in data["epics"]:
            e = epics[ep["id"]]
            if e.get("pinned"):
                continue
            label = e.get("ref") or e.get("placeholder")
            if not slots:
                report.add("pin-epic", ep["id"], f"{label}: the forge reports no free pin slot; pin it by hand")
                continue
            report.add("pin-epic", ep["id"], f"pin {label} on the repository's issue list")
            if apply:
                fg.pin(e)

    # Generated section in each epic (needs the issue links written back above).
    for ep in data["epics"]:
        e = epics[ep["id"]]
        try:
            body = blocks.epic_body(out, ep["id"], e.get("body") or ep.get("note", ""), task_list=not native_epics)
        except blocks.MarkerError as exc:
            report.add("hand-fix", ep["id"], f'{e.get("ref")}: {exc}')
            continue
        if body != (e.get("body") or ""):
            report.add("update-epic", ep["id"],
                       f"roadmap section (flowchart and status table) in {e.get('ref') or e.get('placeholder')}",
                       body=body)
            if apply:
                fg.update_epic_body(e, body)
    return report
