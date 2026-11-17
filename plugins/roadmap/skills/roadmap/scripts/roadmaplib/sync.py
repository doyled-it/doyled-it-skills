"""sync: read the forge and Orca, update the roadmap's view, and report drift.

Read-only on the forge and Orca, with one opt-in exception: --update-epics
rewrites the generated roadmap section in each epic description (only the text
between its markers). It pulls each issue's status, its merge
requests and their pipelines, ticks gates that have evidence, and reports
drift: open issues in an epic that the roadmap does not list, merge requests
and Orca tasks with no roadmap issue, Orca tasks started before their issue's
dependencies were Done, and roadmap issues with nothing behind them or no
recent activity. With --write it saves the new status and gate ticks into
roadmap.json; it never writes to the forge or Orca.
"""

from __future__ import annotations

import copy
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone

from . import blocks, model, orca

DEFAULT_GATE_RULES = {"M": "mr_merged"}
BLOCKED_LABELS = {"blocked", "status::blocked", "status: blocked", "workflow::blocked"}
PROGRESS_LABELS = {"in progress", "doing", "status::in progress", "status::doing", "workflow::in progress",
                   "status: in progress"}


@dataclass
class StatusChange:
    issue: str
    old: str
    new: str
    why: str


@dataclass
class GateTick:
    issue: str
    gate: str
    evidence: str
    why: str


@dataclass
class Drift:
    kind: str
    target: str
    message: str


@dataclass
class SyncReport:
    roadmap: dict
    status_changes: list[StatusChange] = field(default_factory=list)
    gate_ticks: list[GateTick] = field(default_factory=list)
    merge_requests: dict[str, list[dict]] = field(default_factory=dict)
    drift: list[Drift] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.status_changes or self.gate_ticks or self.merge_requests)

    def as_dict(self) -> dict:
        return {"status_changes": [asdict(c) for c in self.status_changes],
                "gate_ticks": [asdict(t) for t in self.gate_ticks],
                "merge_requests": self.merge_requests,
                "drift": [asdict(d) for d in self.drift],
                "notes": self.notes}

    def text(self) -> str:
        lines = ["Sync is read-only on the forge and Orca unless --update-epics is given. "
                 "Use --write to save status and gates into roadmap.json.", ""]
        lines.append("Status changes")
        lines += [f"  {c.issue}: {model.STATUSES[c.old]} -> {model.STATUSES[c.new]} ({c.why})"
                  for c in self.status_changes] or ["  none"]
        lines += ["", "Gates ticked"]
        lines += [f"  {t.issue} {t.gate}: {t.evidence} ({t.why})" for t in self.gate_ticks] or ["  none"]
        lines += ["", "Merge requests"]
        rows = []
        for iid, mrs in self.merge_requests.items():
            for mr in mrs:
                pipe = f", pipeline {mr['pipeline']}" if mr.get("pipeline") else ""
                draft = " (draft)" if mr.get("draft") else ""
                rows.append(f"  {iid}: {mr['ref']} {mr['state']}{draft}{pipe} {mr.get('url') or ''}".rstrip())
        lines += rows or ["  none"]
        lines += ["", "Drift"]
        lines += [f"  [{d.kind}] {d.target}: {d.message}" for d in self.drift] or ["  none"]
        if self.notes:
            lines += ["", "Notes"] + [f"  {n}" for n in self.notes]
        return "\n".join(lines)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _forge_status(fi: dict, mrs: list[dict], cfg: dict) -> tuple[str | None, str]:
    """Status the forge supports, with the reason, or None when it says nothing new."""
    labels = {lb.lower() for lb in fi.get("labels", [])}
    custom = {k: v.lower() for k, v in (cfg.get("status_labels") or {}).items()}
    if fi["state"] == "closed":
        return "done", "issue closed"
    if labels & (BLOCKED_LABELS | ({custom["blocked"]} if "blocked" in custom else set())):
        return "blocked", "blocked label"
    open_mrs = [m for m in mrs if m["state"] == "open"]
    if any(not m["draft"] for m in open_mrs):
        return "in_review", "open merge request " + next(m["ref"] for m in open_mrs if not m["draft"])
    if open_mrs:
        return "in_progress", "draft merge request " + open_mrs[0]["ref"]
    if labels & (PROGRESS_LABELS | ({custom["in_progress"]} if "in_progress" in custom else set())):
        return "in_progress", "in-progress label"
    return None, ""


def named_merge_requests(data: dict, projects: list[str], default: str | None) -> set[str]:
    """Merge requests the roadmap names in its issue text or links.

    Accepts a full reference (group/project!12), a forge URL, "!12" for the
    default project, and "web !12" when "web" is the last part of a known
    project path.
    """
    short = {p.rsplit("/", 1)[-1].lower(): p for p in projects}
    texts = []
    for it in data["issues"]:
        texts += [it.get("title", ""), it.get("detail", "")]
        texts += [lk.get("url", "") if isinstance(lk, dict) else str(lk) for lk in it.get("links", [])]
    found: set[str] = set()
    for text in texts:
        found |= {f"{m[1]}!{m[2]}" for m in re.finditer(r"([\w.-]+(?:/[\w.-]+)+)!(\d+)", text)}
        found |= {f"{m[1]}!{m[2]}" for m in re.finditer(r"https?://[^/\s]+/(\S+?)/-/merge_requests/(\d+)", text)}
        found |= {f"{m[1]}#{m[2]}" for m in re.finditer(r"https?://[^/\s]+/([\w.-]+/[\w.-]+)/pulls?/(\d+)", text)}
        for m in re.finditer(r"(?<![\w/!])(?:([\w.-]+)\s)?!(\d+)", text):
            project = short.get((m[1] or "").lower()) or default
            if project:
                found.add(f"{project}!{m[2]}")
    return found


RANK = {"to_do": 0, "blocked": 1, "in_progress": 2, "in_review": 3, "done": 4}


def sync(raw: dict, fg, orca_tasks=None, stale_days: int = 14, now: str | None = None,
         update_epics: bool = False) -> SyncReport:
    out = copy.deepcopy(raw)
    data = model.normalize(raw)
    items = model.issues_by_id(data)
    raw_items = {i["id"]: i for i in out["issues"]}
    report = SyncReport(roadmap=out)
    cfg = data.get("forge") or {}
    rules = dict(DEFAULT_GATE_RULES, **(cfg.get("gate_rules") or {}))
    today = (datetime.fromisoformat(now).replace(tzinfo=timezone.utc) if now
             else datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc))
    stale_before = today - timedelta(days=stale_days)

    tasks = orca_tasks if isinstance(orca_tasks, list) else None
    if isinstance(orca_tasks, str):
        report.notes.append(orca_tasks)
    elif orca_tasks is None:
        report.notes.append("Orca not checked.")
    task_issue = {}
    if tasks is not None:
        for t in orca.active(tasks):
            task_issue[t["id"]] = orca.match(t, items)

    known_mrs: set[str] = set()
    roadmap_refs = {it["ref"]: iid for iid, it in items.items() if it.get("ref")}

    for iid, it in items.items():
        if not it.get("ref"):
            report.drift.append(Drift("not-published", iid, "has nothing behind it on the forge yet; "
                                      "publish the agreed roadmap or link the existing issue"))
            continue
        try:
            fi = fg.get_issue(it["ref"])
        except Exception as exc:  # a missing or unreadable issue is drift, not a crash
            report.drift.append(Drift("missing-on-forge", iid, f'{it["ref"]} could not be read: {exc}'))
            continue
        mrs = fg.related_mrs(fi)
        known_mrs |= {m["ref"] for m in mrs}
        if mrs:
            report.merge_requests[iid] = [{k: m.get(k) for k in ("ref", "url", "state", "draft", "pipeline",
                                                                   "pipeline_url")} for m in mrs]
            raw_items[iid]["merge_requests"] = report.merge_requests[iid]

        # Status.
        new, why = _forge_status(fi, mrs, cfg)
        old = it["status"]
        if new and new != old:
            forward = RANK[new] > RANK[old] or new == "blocked" or old == "blocked"
            if old == "done" and new != "done":
                report.drift.append(Drift("done-but-open", iid, f'Done on the roadmap but {fi["ref"]} is open'))
            elif forward:
                report.status_changes.append(StatusChange(iid, old, new, why))
                raw_items[iid]["status"] = new
                it = dict(it, status=new)

        # Gates.
        ticks = blocks.ticked_gates(fi["body"])
        merged = [m for m in mrs if m["state"] == "merged"]
        new_gates = []
        for g in it["gates"]:
            g = dict(g)
            if not g["passed"]:
                evidence, reason = None, ""
                if g["gate"] in ticks:
                    evidence, reason = ticks[g["gate"]] or fi["url"], "ticked on the forge"
                elif rules.get(g["gate"]) == "mr_merged" and merged:
                    evidence, reason = merged[0]["url"], f"merge request {merged[0]['ref']} merged"
                elif rules.get(g["gate"]) == "mr_approved_green":
                    ok = [m for m in mrs if m["state"] in ("open", "merged") and m.get("pipeline") == "success"]
                    if ok:
                        evidence, reason = ok[0].get("pipeline_url") or ok[0]["url"], "pipeline green"
                if evidence:
                    g.update(passed=True, evidence=evidence)
                    report.gate_ticks.append(GateTick(iid, g["gate"], evidence, reason))
            new_gates.append(g)
        if new_gates != it["gates"]:
            raw_items[iid]["gates"] = new_gates

        # Activity.
        if it["status"] != "done":
            times = [_parse_time(fi.get("updated_at"))] + [_parse_time(m.get("updated_at")) for m in mrs]
            latest = max((t for t in times if t), default=None)
            if latest and latest < stale_before:
                report.drift.append(Drift("no-recent-activity", iid,
                                          f"no forge activity since {latest.date().isoformat()} "
                                          f"(more than {stale_days} days)"))
        if it["status"] in model.ACTIVE and not mrs and tasks is not None and iid not in task_issue.values():
            report.drift.append(Drift("nothing-behind", iid,
                                      f"{model.STATUSES[it['status']]} but no merge request and no Orca task"))

    # Epics: open issues the roadmap does not list, and the generated section.
    native = getattr(fg, "native_epics", True)
    for ep in data["epics"]:
        if not ep.get("ref"):
            continue
        epic = None
        try:
            epic = fg.get_epic(ep["ref"])
        except Exception as exc:
            report.notes.append(f'epic {ep["ref"]} could not be read: {exc}')
        try:
            members = fg.epic_issues(epic or {"ref": ep["ref"], "number": int(re.split(r"[#&]", ep["ref"])[-1])})
        except Exception as exc:
            report.notes.append(f'issues in epic {ep["ref"]} could not be read: {exc}')
            members = []
        for fi in members:
            if fi["state"] == "open" and fi["ref"] not in roadmap_refs:
                report.drift.append(Drift("unlisted-epic-issue", fi["ref"],
                                          f'open in epic "{ep["name"]}" but not on the roadmap: {fi["title"]}'))
        if epic is None:
            continue
        body = blocks.epic_body(out, ep["id"], epic.get("body") or "", task_list=not native)
        if body == (epic.get("body") or ""):
            continue
        if update_epics:
            fg.update_epic_body(epic, body)
            report.notes.append(f'updated the roadmap section in epic {ep["ref"]} ({ep["id"]})')
        else:
            report.notes.append(f'the roadmap section in epic {ep["ref"]} ({ep["id"]}) is out of date; '
                                "run sync --update-epics to rewrite only that section")

    # Open merge requests with no roadmap issue.
    projects = []
    for p in [cfg.get("project"), *(cfg.get("projects") or []),
              *(model.issues_by_id(data)[i].get("project") for i in items)]:
        if p and p not in projects:
            projects.append(p)
    for it in items.values():
        p = (it.get("ref") or "").rsplit("#", 1)[0]
        if p and p not in projects:
            projects.append(p)
    ids = sorted(items, key=len, reverse=True)
    named = named_merge_requests(data, projects, cfg.get("project"))
    for project in projects:
        try:
            mrs = fg.open_mrs(project)
        except Exception as exc:
            report.notes.append(f"merge requests in {project} could not be read: {exc}")
            continue
        for mr in mrs:
            if mr["ref"] in known_mrs or mr["ref"] in named:
                continue
            if fg.mr_mentions(mr) & set(roadmap_refs):
                continue
            text = f"{mr['title']}\n{mr['body']}".lower()
            if any(re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", text) for i in ids):
                continue
            report.drift.append(Drift("unlinked-merge-request", mr["ref"],
                                      f'open merge request with no roadmap issue: "{mr["title"]}"'))

    # Orca tasks.
    if tasks is not None:
        for t in orca.active(tasks):
            iid = task_issue.get(t["id"])
            if not iid:
                report.drift.append(Drift("unlinked-orca-task", t["id"],
                                          f'Orca task "{t["title"]}" does not start with a roadmap issue name'))
                continue
            waiting = [d for d in items[iid]["depends_on"] if raw_items[d]["status"] != "done"]
            if waiting:
                report.drift.append(Drift("started-early", iid,
                                          f'Orca task {t["id"]} started before these were Done: {", ".join(waiting)}'))
    return report
