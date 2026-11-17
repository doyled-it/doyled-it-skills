"""validate: schema, dependency cycles, dangling dependencies, and glossary checks.

Errors mean the roadmap cannot be rendered or published as it stands.
Warnings are things a reader should look at before the next update.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import model

READABLE_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
# Codes such as A1, T1.1, E1.4 or TE2 used instead of a readable name.
CODE = re.compile(r"\b[A-Z]{1,3}\d+(?:\.\d+)*[a-z]?\b")
CODE_ID = re.compile(r"^[a-z]{1,3}\d+(?:[.-]\d+)*$")
MILESTONE = re.compile(r"\bmilestones?\b", re.IGNORECASE)
# Words the glossary replaces, and what to say instead.
SYNONYMS = {
    r"\bsprints?\b": "Iteration",
    r"\btickets?\b": "Issue",
    r"\bwork ?streams?\b": "Epic",
    r"\bswim ?lanes?\b": "Epic",
}
URL = re.compile(r"https?://\S+")
REF = re.compile(r"^[\w.-]+(?:/[\w.-]+)*[#&]\d+$")
FORGES = ("gitlab", "github")


@dataclass(frozen=True)
class Finding:
    level: str  # "error" or "warning"
    code: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level}: {self.where}: {self.message} [{self.code}]"


def check(raw: dict) -> list[Finding]:
    """Run every check and return the findings, errors first."""
    out: list[Finding] = []

    def err(code, where, msg):
        out.append(Finding("error", code, where, msg))

    def warn(code, where, msg):
        out.append(Finding("warning", code, where, msg))

    for key in model.REQUIRED_TOP:
        if key not in raw:
            err("missing-field", "roadmap", f'missing required field "{key}"')
    if "agreed" in raw and not isinstance(raw["agreed"], bool):
        err("bad-type", "agreed", '"agreed" must be true or false')
    for key in ("epics", "issues"):
        if key in raw and not isinstance(raw[key], list):
            err("bad-type", key, f'"{key}" must be a list')
            return out
    if "gates" in raw and not isinstance(raw["gates"], dict):
        err("bad-type", "gates", '"gates" must map each gate letter to what it checks')
        return out

    data = model.normalize(raw)
    forge = data.get("forge")
    if forge is not None:
        if not isinstance(forge, dict) or forge.get("kind") not in FORGES:
            err("bad-forge", "forge", 'forge "kind" must be "gitlab" or "github"')

    gates = data["gates"]
    iterations = {i.get("name") for i in data.get("iterations", []) if isinstance(i, dict)}

    # Epics.
    epic_ids: set[str] = set()
    for n, ep in enumerate(data["epics"]):
        where = f"epics[{ep.get('id', n)}]"
        for key in model.REQUIRED_EPIC:
            if not ep.get(key):
                err("missing-field", where, f'missing required field "{key}"')
        eid = ep.get("id")
        if eid in epic_ids:
            err("duplicate-id", where, f'epic id "{eid}" is used twice')
        if eid:
            epic_ids.add(eid)
            if not READABLE_ID.match(eid) or CODE_ID.match(eid):
                err("unreadable-id", where,
                    f'"{eid}" is not a short readable name (lowercase words joined by hyphens)')
        if ep.get("name") and CODE.search(ep["name"]):
            err("glossary-code", f"{where}.name",
                f'"{ep["name"]}" uses a code; give the epic a plain name')
        if ep.get("ref") and not REF.match(ep["ref"]):
            err("bad-ref", f"{where}.ref", f'"{ep["ref"]}" is not a forge reference like group/project&12')
    by_epic = {ep.get("id"): ep for ep in data["epics"]}
    for ep in data["epics"]:
        parent = ep.get("parent")
        if parent and parent not in epic_ids:
            err("unknown-parent", f"epics[{ep.get('id')}].parent", f'parent epic "{parent}" does not exist')
    for ep in data["epics"]:
        seen, cur = [], ep
        while cur and cur.get("parent"):
            if cur["id"] in seen:
                err("cycle", f"epics[{ep['id']}]", "epic parents loop: " + " -> ".join(seen + [cur["id"]]))
                break
            seen.append(cur["id"])
            cur = by_epic.get(cur["parent"])

    # Issues.
    ids: set[str] = set()
    for n, it in enumerate(data["issues"]):
        iid = it.get("id", f"#{n}")
        where = f"issues[{iid}]"
        for key in model.REQUIRED_ISSUE:
            if not it.get(key):
                err("missing-field", where, f'missing required field "{key}"')
        if iid in ids:
            err("duplicate-id", where, f'issue id "{iid}" is used twice')
        ids.add(iid)
        if iid in epic_ids:
            err("duplicate-id", where, f'"{iid}" names both an epic and an issue')
        if isinstance(iid, str) and (not READABLE_ID.match(iid) or CODE_ID.match(iid)):
            err("unreadable-id", where,
                f'"{iid}" is not a short readable name (lowercase words joined by hyphens)')
        if it.get("title") and CODE.search(it["title"]):
            err("glossary-code", f"{where}.title",
                f'"{it["title"]}" uses a code; say what the issue delivers')
        if it.get("epic") and it["epic"] not in epic_ids:
            err("unknown-epic", f"{where}.epic", f'epic "{it["epic"]}" does not exist')
        if it.get("status") and it["status"] not in model.STATUSES:
            err("bad-status", f"{where}.status",
                f'"{it["status"]}" is not a status; use one of {", ".join(model.STATUSES)}')
        for g in it["gates"]:
            if g["gate"] not in gates:
                err("unknown-gate", f"{where}.gates", f'gate "{g["gate"]}" is not defined in "gates"')
        days = it.get("estimate_days")
        if isinstance(days, (int, float)) and days > model.MAX_ISSUE_DAYS:
            err("too-big", where,
                f"{days} days is more than two weeks; make it a child epic with its own issues")
        if it.get("iteration") and iterations and it["iteration"] not in iterations:
            err("unknown-iteration", f"{where}.iteration", f'iteration "{it["iteration"]}" is not defined')
        if it.get("ref") and not REF.match(it["ref"]):
            err("bad-ref", f"{where}.ref", f'"{it["ref"]}" is not a forge reference like group/project#12')

    items = {i["id"]: i for i in data["issues"] if i.get("id")}
    for iid, it in items.items():
        for d in it["depends_on"]:
            if d not in items:
                err("dangling-dependency", f"issues[{iid}].depends_on",
                    f'depends on "{d}", which is not an issue in this roadmap')
    for cyc in _cycles(items):
        err("cycle", f"issues[{cyc[0]}]", "dependencies loop: " + " -> ".join(cyc))

    # Glossary: never "milestone"; prefer the agreed words.
    for where, text in _strings(data):
        plain = URL.sub("", text)
        if MILESTONE.search(plain):
            err("glossary-milestone", where,
                'uses "milestone"; say Gate (a check) or Issue (a deliverable) instead')
        for pattern, word in SYNONYMS.items():
            m = re.search(pattern, plain, re.IGNORECASE)
            if m:
                warn("glossary-term", where, f'uses "{m.group(0)}"; the glossary word is "{word}"')

    # Warnings about the state of the work.
    for iid, it in items.items():
        if it.get("status") == "done" and model.open_gates(it):
            warn("done-gates-open", f"issues[{iid}]",
                 "is Done but gates " + " ".join(model.open_gates(it)) + " are not ticked")
        if it.get("status") in ("in_progress", "in_review", "done"):
            waiting = [d for d in it["depends_on"] if d in items and items[d].get("status") != "done"]
            if waiting:
                warn("started-early", f"issues[{iid}]",
                     "started before its dependencies were Done: " + ", ".join(waiting))

    out.sort(key=lambda f: f.level != "error")
    return out


def errors(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.level == "error"]


def _cycles(items: dict) -> list[list[str]]:
    """Each dependency loop once, as a path that ends where it started."""
    found, seen_sets = [], set()
    state: dict[str, int] = {}

    def visit(node, path):
        state[node] = 1
        path.append(node)
        for d in items[node]["depends_on"]:
            if d not in items:
                continue
            if state.get(d) == 1:
                loop = path[path.index(d):] + [d]
                key = frozenset(loop)
                if key not in seen_sets:
                    seen_sets.add(key)
                    found.append(loop)
            elif state.get(d) is None:
                visit(d, path)
        path.pop()
        state[node] = 2

    for node in items:
        if state.get(node) is None:
            visit(node, [])
    return found


def _strings(data: dict):
    """Every reader-facing text field with a readable location."""
    for key in ("title", "goal", "rule", "version"):
        if isinstance(data.get(key), str):
            yield key, data[key]
    for letter, text in data.get("gates", {}).items():
        if isinstance(text, str):
            yield f"gates.{letter}", text
    for ep in data["epics"]:
        for key in ("name", "note"):
            if isinstance(ep.get(key), str):
                yield f"epics[{ep.get('id')}].{key}", ep[key]
    for it in data["issues"]:
        for key in ("title", "detail"):
            if isinstance(it.get(key), str):
                yield f"issues[{it.get('id')}].{key}", it[key]
    for n, ev in enumerate(data.get("timeline", [])):
        if isinstance(ev, dict) and isinstance(ev.get("text"), str):
            yield f"timeline[{n}]", ev["text"]
