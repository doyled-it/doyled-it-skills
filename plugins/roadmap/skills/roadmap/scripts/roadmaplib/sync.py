"""sync: read the forge and Orca, update the roadmap's view, and report drift.

Read-only on the forge and Orca, with one opt-in exception: --update-epics
rewrites the generated roadmap section in each epic description (only the text
between its markers). It pulls each issue's status, its merge
requests and their pipelines, ticks gates that have evidence, and reports
drift: open issues in an epic that the roadmap does not list, merge requests
and Orca tasks with no roadmap issue, Orca tasks started before their issue's
dependencies were Done, and roadmap issues with nothing behind them or no
recent activity (active work only). With --write it saves the new status and gate ticks into
roadmap.json; it never writes to the forge or Orca.
"""

from __future__ import annotations

import copy
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone

from . import blocks, forge, model, orca, render, validate

BLOCKED_LABELS = {"blocked", "status::blocked", "status: blocked", "workflow::blocked"}
PROGRESS_LABELS = {"in progress", "doing", "status::in progress", "status::doing", "workflow::in progress",
                   "status: in progress"}


# Who clears each kind of drift. Every kind is something a person or an agent
# can act on, so the scheduled drift issue counts them all; work that simply has
# not started is not drift (no staleness for To do or Blocked, and nothing for a
# Done issue that publish skipped). The agent hooks block a turn only on
# "agent" kinds, for issues that turn changed.
DRIFT_OWNER = {
    "done-but-open": "agent",           # close the issue, or correct the status
    "missing-on-forge": "agent",        # fix the ref
    "marker-problem": "agent",          # repair the markers by hand
    "quick-action": "agent",            # remove the command line by hand
    "nothing-behind": "agent",          # open the merge request, or correct the status
    "not-published": "lead",            # publish the agreed roadmap
    "lead-gate-ticked-on-forge": "lead",  # record the approval in roadmap.json, or untick it
    "unlisted-epic-issue": "lead",      # add it to the roadmap, or move it out of the epic
    "unlinked-merge-request": "team",   # name its roadmap issue
    "unlinked-orca-task": "team",       # rename the task after its roadmap issue
    "started-early": "team",            # finish the dependencies first
    "no-recent-activity": "team",       # pick active work back up, or change its status
}
AGENT_DRIFT = frozenset(k for k, who in DRIFT_OWNER.items() if who == "agent")


class SyncRefused(Exception):
    """sync will not run: the roadmap has structural errors, or a forge write was asked of a draft."""


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
    errors: list[str] = field(default_factory=list)   # forge reads that failed: the report is incomplete
    write_errors: list[str] = field(default_factory=list)  # epic writes that failed after every read succeeded
    cleared: list[str] = field(default_factory=list)  # issues whose recorded merge requests are gone

    @property
    def changed(self) -> bool:
        return bool(self.status_changes or self.gate_ticks or self.merge_requests or self.cleared)

    def as_dict(self) -> dict:
        return {"status_changes": [asdict(c) for c in self.status_changes],
                "gate_ticks": [asdict(t) for t in self.gate_ticks],
                "merge_requests": self.merge_requests,
                "drift": [asdict(d) for d in self.drift],
                "notes": self.notes,
                "errors": self.errors,
                "write_errors": self.write_errors}

    def text(self) -> str:
        lines = ["Sync is read-only on the forge and Orca unless --update-epics is given. "
                 "Use --write to save status and gates into roadmap.json.", ""]
        if self.errors:
            lines += ["Incomplete: these forge calls failed, so the report below misses what they would have "
                      "shown. Nothing is saved; run sync again once the forge answers."]
            lines += [f"  {e}" for e in self.errors] + [""]
        if self.write_errors:
            lines += ["These epic writes failed. The report is complete and roadmap.json can be saved; the epics "
                      "named here show the old section until the next sync --update-epics."]
            lines += [f"  {e}" for e in self.write_errors] + [""]
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


def parse_now(value: str) -> datetime:
    """An ISO date (or date and time) for --now; raises ValueError when it is not one."""
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


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


# A closing reference in a merge request: "Closes #12", "fixes group/project#12",
# "Resolves https://host/.../issues/12", several joined by commas or "and".
REF_ITEM = r"(?:(?:[\w.-]+(?:/[\w.-]+)*)?#\d+|https?://[^\s,;]+)"
# The words each forge itself treats as closing. GitLab also accepts the -ing
# forms and "implement"; GitHub, Forgejo and Gitea do not.
CLOSING_WORDS = {
    "gitlab": r"close[sd]?|closing|fix(?:e[sd]|ing)?|resolve[sd]?|resolving|implement(?:s|ed|ing)?",
    "github": r"close[sd]?|fix(?:e[sd])?|resolve[sd]?",
}


def _closing(kind: str) -> re.Pattern:
    words = CLOSING_WORDS["gitlab" if kind == "gitlab" else "github"]
    return re.compile(rf"\b(?:{words}):?\s+({REF_ITEM}(?:\s*(?:,|\band\b)\s*{REF_ITEM})*)", re.IGNORECASE)


GATE_RULES = ("mr_merged", "mr_green", "checklist")


def closes(mr: dict, fi: dict, kind: str = "gitlab") -> bool:
    """The merge request's title or description closes this forge issue, by the forge's own closing words."""
    text = f"{mr.get('title', '')}\n{mr.get('body', '')}"
    for m in _closing(kind).finditer(text):
        for ref in re.findall(REF_ITEM, m.group(1)):
            if ref.lower().startswith("http"):
                if fi.get("url") and ref.rstrip("/.") == fi["url"]:
                    return True
            elif ref.startswith("#"):
                if f"{mr.get('project')}#{ref[1:]}" == fi["ref"]:
                    return True
            elif ref == fi["ref"]:
                return True
    return False


def roadmap_projects(data: dict, cfg: dict) -> list[str]:
    """The roadmap's own projects: forge.project, forge.projects, and every issue's project."""
    projects: list[str] = []
    for p in [cfg.get("project"), *(cfg.get("projects") or []),
              *(it.get("project") for it in data["issues"]),
              *((it.get("ref") or "").rsplit("#", 1)[0] for it in data["issues"])]:
        if p and p not in projects:
            projects.append(p)
    return projects


RANK = {"to_do": 0, "blocked": 1, "in_progress": 2, "in_review": 3, "done": 4}


def sync(raw: dict, fg, orca_tasks=None, stale_days: int = 14, now: str | None = None,
         update_epics: bool = False, only: set[str] | None = None) -> SyncReport:
    """Read the forge and Orca and report status, gate evidence and drift.

    only limits the run to those roadmap issues and skips the epic, open merge
    request and Orca checks: a fast check of the work at hand (the agent hooks
    use it). It cannot be combined with update_epics.
    """
    if only is not None and update_epics:
        raise SyncRefused("--only checks a few issues; it cannot rewrite epics")
    findings = validate.errors(validate.check(raw))
    structural = [f for f in findings if f.code in render.BLOCKING]
    if structural:
        raise SyncRefused("fix these first:\n" + "\n".join(str(f) for f in structural))
    unknown = sorted((only or set()) - {i.get("id") for i in raw.get("issues", []) if isinstance(i, dict)})
    if unknown:
        raise SyncRefused(f"not issues on the roadmap: {', '.join(unknown)}")
    if update_epics and not raw.get("agreed"):
        raise SyncRefused("--update-epics writes to the forge, and this roadmap is a draft; "
                          'set "agreed": true once the program lead agrees it')
    if update_epics and findings:
        raise SyncRefused("--update-epics writes to the forge; fix these first:\n"
                          + "\n".join(str(f) for f in findings))
    out = copy.deepcopy(raw)
    data = model.normalize(raw)
    items = model.issues_by_id(data)
    raw_items = {i["id"]: i for i in out["issues"]}
    report = SyncReport(roadmap=out)
    cfg = data.get("forge") or {}
    rules = model.gate_rules(data)
    unchecked = model.unchecked_gates(data)
    today = (parse_now(now) if now
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
    started = {t["id"] for t in orca.started(tasks)} if tasks is not None else set()

    projects = roadmap_projects(data, cfg)
    lead = model.lead_gates(data)
    known_mrs: set[str] = set()
    roadmap_refs = {it["ref"]: iid for iid, it in items.items() if it.get("ref")}

    for iid, it in items.items():
        if only is not None and iid not in only:
            continue
        if not it.get("ref"):
            if it["status"] != "done":   # publish skips finished work with no forge issue on purpose
                report.drift.append(Drift("not-published", iid, "has nothing behind it on the forge yet; "
                                          "publish the agreed roadmap or link the existing issue"))
            continue
        try:
            fi = fg.get_issue(it["ref"])
        except forge.NotFound as exc:
            report.drift.append(Drift("missing-on-forge", iid, f'{it["ref"]} does not exist or cannot be seen: {exc}'))
            continue
        except forge.ForgeError as exc:   # a rate limit or server error is not a missing issue
            report.errors.append(f'{iid}: reading {it["ref"]} failed: {exc}')
            continue
        try:
            related = fg.related_mrs(fi)
        except forge.ForgeError as exc:
            report.errors.append(f'{iid}: reading the merge requests of {it["ref"]} failed: {exc}')
            continue
        # Only merge requests in the roadmap's own projects count: anyone can
        # mention an issue from a repository of their own.
        mrs = [m for m in related if m.get("project") in projects]
        if len(mrs) < len(related):
            report.notes.append(f'{iid}: ignored {len(related) - len(mrs)} merge request(s) outside the roadmap\'s '
                                f'projects that mention {fi["ref"]}')
        named = named_merge_requests({"issues": [it]}, projects, cfg.get("project"))
        linked = [m for m in mrs if m["ref"] in named or closes(m, fi, getattr(fg, "kind", "gitlab"))]
        known_mrs |= {m["ref"] for m in mrs}
        if mrs:
            report.merge_requests[iid] = [{k: m.get(k) for k in ("ref", "url", "state", "draft", "pipeline",
                                                                   "pipeline_url")} for m in mrs]
            raw_items[iid]["merge_requests"] = report.merge_requests[iid]
        elif raw_items[iid].pop("merge_requests", None) is not None:
            report.cleared.append(iid)

        # Status.
        new, why = _forge_status(fi, mrs, cfg)
        old = it["status"]
        if old == "done" and fi["state"] == "open":
            report.drift.append(Drift("done-but-open", iid, f'Done on the roadmap but {fi["ref"]} is open'))
        elif new and new != old:
            forward = RANK[new] > RANK[old] or new == "blocked" or old == "blocked"
            if forward:
                report.status_changes.append(StatusChange(iid, old, new, why))
                raw_items[iid]["status"] = new
                it = dict(it, status=new)

        # Gates.
        try:
            blocks.find_block(fi["body"], blocks.ISSUE_START, blocks.ISSUE_END)
        except blocks.MarkerError as exc:
            report.drift.append(Drift("marker-problem", fi["ref"], f"{exc}. Its gate checklist was not read"))
        ticks = blocks.ticked_gates(fi["body"])
        merged = [m for m in linked if m["state"] == "merged"]
        on_forge = sorted(g["gate"] for g in it["gates"]
                          if not g["passed"] and g["gate"] in lead and g["gate"] in ticks)
        if on_forge:
            report.drift.append(Drift("lead-gate-ticked-on-forge", iid,
                                      f'{" ".join(on_forge)} ticked on {fi["ref"]}; the lead\'s approval counts only '
                                      'when recorded in roadmap.json ("approved_by"), so it was not ticked'))
        new_gates = []
        for g in it["gates"]:
            g = dict(g)
            if not g["passed"] and g["gate"] not in lead:
                evidence, reason = None, ""
                if g["gate"] in ticks and g["gate"] not in unchecked:
                    evidence, reason = ticks[g["gate"]] or fi["url"], "ticked in the generated checklist"
                elif rules.get(g["gate"]) == "mr_merged" and merged:
                    evidence, reason = merged[0]["url"], f"merge request {merged[0]['ref']} merged and closes the issue"
                elif rules.get(g["gate"]) == "mr_green":
                    ok = [m for m in linked if m["state"] in ("open", "merged") and m.get("pipeline") == "success"]
                    if ok:
                        evidence, reason = ok[0].get("pipeline_url") or ok[0]["url"], "pipeline green"
                if evidence:
                    g.update(passed=True, evidence=evidence)
                    report.gate_ticks.append(GateTick(iid, g["gate"], evidence, reason))
            new_gates.append(g)
        if new_gates != it["gates"]:
            raw_items[iid]["gates"] = new_gates

        # Activity: only work that has started can go stale.
        if it["status"] in model.ACTIVE:
            times = [_parse_time(fi.get("updated_at"))] + [_parse_time(m.get("updated_at")) for m in mrs]
            latest = max((t for t in times if t), default=None)
            if latest and latest < stale_before:
                report.drift.append(Drift("no-recent-activity", iid,
                                          f"no forge activity since {latest.date().isoformat()} "
                                          f"(more than {stale_days} days)"))
        if it["status"] in model.ACTIVE and not mrs and tasks is not None and iid not in task_issue.values():
            report.drift.append(Drift("nothing-behind", iid,
                                      f"{model.STATUSES[it['status']]} but no merge request and no Orca task"))

    if only is not None:
        return report

    # Epics: open issues the roadmap does not list, and the generated section.
    # Sections are written last, once every read has succeeded.
    native = getattr(fg, "native_epics", True)
    epic_writes: list[tuple[dict, dict, str]] = []
    for ep in data["epics"]:
        if not ep.get("ref"):
            continue
        epic = None
        try:
            epic = fg.get_epic(ep["ref"])
        except forge.NotFound as exc:
            report.notes.append(f'epic {ep["ref"]} could not be read: {exc}')
        except forge.ForgeError as exc:
            report.errors.append(f'{ep["id"]}: reading epic {ep["ref"]} failed: {exc}')
        try:
            members = fg.epic_issues(epic or {"ref": ep["ref"], "number": int(re.split(r"[#&]", ep["ref"])[-1])})
        except forge.NotFound as exc:
            report.notes.append(f'issues in epic {ep["ref"]} could not be read: {exc}')
            members = []
        except forge.ForgeError as exc:
            report.errors.append(f'{ep["id"]}: reading the issues of epic {ep["ref"]} failed: {exc}')
            members = []
        for fi in members:
            if fi["state"] == "open" and fi["ref"] not in roadmap_refs:
                report.drift.append(Drift("unlisted-epic-issue", fi["ref"],
                                          f'open in epic "{ep["name"]}" but not on the roadmap: {fi["title"]}'))
        if epic is None:
            continue
        try:
            body = blocks.epic_body(out, ep["id"], epic.get("body") or "", task_list=not native)
        except blocks.MarkerError as exc:
            report.drift.append(Drift("marker-problem", ep["ref"], f"{exc}. Its roadmap section was not "
                                      "checked or written"))
            continue
        if body == (epic.get("body") or ""):
            continue
        hold = forge.command_hold(fg, body)
        if hold:
            report.drift.append(Drift("quick-action", ep["ref"], f"{hold}. Its roadmap section was not written"))
            continue
        if update_epics:
            epic_writes.append((ep, epic, body))
        else:
            report.notes.append(f'the roadmap section in epic {ep["ref"]} ({ep["id"]}) is out of date; '
                                "run sync --update-epics to rewrite only that section")

    # Open merge requests with no roadmap issue.
    ids = sorted(items, key=len, reverse=True)
    named = named_merge_requests(data, projects, cfg.get("project"))
    for project in projects:
        try:
            mrs = fg.open_mrs(project)
        except forge.ForgeError as exc:
            report.errors.append(f"reading the open merge requests of {project} failed: {exc}")
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
            if t["id"] not in started:
                continue   # queued or waiting in Orca: not started yet
            waiting = [d for d in items[iid]["depends_on"] if raw_items[d]["status"] != "done"]
            if waiting:
                report.drift.append(Drift("started-early", iid,
                                          f'Orca task {t["id"]} started before these were Done: {", ".join(waiting)}'))

    # Epic sections, only when the report is complete.
    for ep, epic, body in epic_writes:
        if report.errors:
            report.notes.append(f'did not update epic {ep["ref"]} ({ep["id"]}): the report is incomplete')
            continue
        try:
            fg.update_epic_body(epic, body)
        except forge.ForgeError as exc:
            report.write_errors.append(f'{ep["id"]}: writing the roadmap section of epic {ep["ref"]} failed: {exc}')
            continue
        report.notes.append(f'updated the roadmap section in epic {ep["ref"]} ({ep["id"]})')
    return report
