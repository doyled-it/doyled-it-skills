"""The roadmap data model: loading, normalizing, and the shared vocabulary.

roadmap.json is the source of truth for the agreed plan. These helpers read it,
accept a few older field names, and give every other command the same view.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

# Status values as stored, and how a reader sees them.
STATUSES = {
    "to_do": "To do",
    "in_progress": "In progress",
    "in_review": "In review",
    "blocked": "Blocked",
    "done": "Done",
}

COORDINATOR_ROLES = ("meta", "area", "worker")
# Short CSS class per status, used by the renderer.
STATUS_CLASS = {
    "to_do": "todo",
    "in_progress": "prog",
    "in_review": "review",
    "blocked": "block",
    "done": "done",
}
ACTIVE = ("in_progress", "in_review")

# The default gate set. A project may define its own in roadmap.json "gates".
DEFAULT_GATES = {
    "D": "Design agreed before building",
    "R": "Independent review, every finding fixed and re-checked",
    "G": "Quality gate with a recorded visual inspection of the output",
    "S": "Screen gate: every screen at every width, light and dark, accessibility checks",
    "M": "Merged and released",
    "U": "Explicit approval from the program lead",
}

# Gates only the program lead can pass: they pass only from an approval recorded
# in roadmap.json ("approved_by"), never from a checkbox or a forge event. A
# roadmap may name its own set in "lead_gates".
DEFAULT_LEAD_GATES = ("D", "U")

REQUIRED_TOP = ("title", "version", "date", "agreed", "goal", "rule", "gates", "epics", "issues")
REQUIRED_EPIC = ("id", "name")
REQUIRED_ISSUE = ("id", "title", "epic", "status")

# Working days in two weeks: an issue bigger than this becomes a child epic.
MAX_ISSUE_DAYS = 10


# A link the page, the preview and the forge sections may make live: http or
# https, with nothing that could end an attribute or a Markdown link early.
SAFE_URL = re.compile(r"^https?://[^\s\"'<>`\\()\[\]]+$", re.IGNORECASE)


def safe_url(url) -> str | None:
    """The URL when it is a plain http or https link, otherwise None."""
    return url if isinstance(url, str) and SAFE_URL.match(url) else None


# GitLab names one issue's page two ways: /-/issues/N, and /-/work_items/N,
# which is what its API returns as web_url from GitLab 17 on. GitHub and
# Forgejo paths have no "/-/" and are left as they are.
GITLAB_ITEM_PAGE = re.compile(r"/-/(?:issues|work_items)/(\d+)$")


def item_urls(url: str) -> set[str]:
    """Every URL that names the same issue page as url (url itself, without a trailing slash)."""
    url = url.rstrip("/")
    m = GITLAB_ITEM_PAGE.search(url)
    if not m:
        return {url}
    base = url[:m.start()]
    return {f"{base}/-/issues/{m[1]}", f"{base}/-/work_items/{m[1]}"}


class RoadmapError(Exception):
    """The roadmap file cannot be read at all."""


def load(path: str | Path) -> dict:
    """Read roadmap.json and return it normalized."""
    path = Path(path)
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise RoadmapError(f"{path} does not exist") from exc
    except json.JSONDecodeError as exc:
        raise RoadmapError(f"{path} is not valid JSON: {exc}") from exc
    except RecursionError as exc:
        raise RoadmapError(f"{path} exceeds the JSON decoder's nesting limit") from exc
    if not isinstance(raw, dict):
        raise RoadmapError(f"{path} must hold one JSON object")
    return raw


def save(path: str | Path, data: dict) -> None:
    """Write roadmap.json back in a stable, readable layout."""
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def gate_obj(g) -> dict:
    """A gate entry as an object: {"gate": letter, "passed": bool, "evidence"?: url}."""
    if isinstance(g, str):
        return {"gate": g, "passed": False}
    out = {"gate": g.get("gate"), "passed": bool(g.get("passed"))}
    for key in ("evidence", "approved_by", "approved_on"):
        if g.get(key):
            out[key] = g[key]
    return out


def lead_gates(data: dict) -> set[str]:
    """Gate letters only the program lead can pass."""
    lead = data.get("lead_gates")
    return {g for g in lead if isinstance(g, str)} if isinstance(lead, list) else set(DEFAULT_LEAD_GATES)


# The forge rule for M unless the roadmap sets forge.gate_rules.
DEFAULT_GATE_RULES = {"M": "mr_merged"}
# Rules that tick a gate from forge evidence (a merged or green merge request).
EVIDENCE_RULES = ("mr_merged", "mr_green")


def gate_rules(data: dict) -> dict[str, str]:
    """Each gate letter with a forge rule, defaults included."""
    cfg = data.get("forge") if isinstance(data.get("forge"), dict) else {}
    rules = cfg.get("gate_rules") if isinstance(cfg.get("gate_rules"), dict) else {}
    return dict(DEFAULT_GATE_RULES, **rules)


def unchecked_gates(data: dict) -> set[str]:
    """Gates a ticked checklist line never passes.

    Lead gates pass only from the approval recorded in roadmap.json, and a gate
    with a merge request rule (M by default) only from that merge request.
    """
    return lead_gates(data) | {g for g, rule in gate_rules(data).items() if rule in EVIDENCE_RULES}


TIMELINE_AUTHOR_PREFIXES = {"(Claude)": "claude", "(Codex)": "codex"}


def timeline_prefix(text: str) -> str:
    """Return only a literal author prefix at the start of the record."""
    return next((prefix for prefix in TIMELINE_AUTHOR_PREFIXES if text.startswith(prefix)), "")


def copy_json(data):
    """Deep-copy raw roadmap values without consuming the stack on JSON containers."""
    memo = {}
    containers = []

    def clone(value):
        if not isinstance(value, (dict, list)):
            return copy.deepcopy(value, memo)
        identity = id(value)
        if identity not in memo:
            result = {} if isinstance(value, dict) else []
            memo[identity] = result
            containers.append((value, result))
        return memo[identity]

    copied = clone(data)
    while containers:
        value, result = containers.pop()
        if isinstance(value, dict):
            result.update((key, clone(child)) for key, child in value.items())
        else:
            result.extend(clone(child) for child in value)
    return copied


def _attribute_timeline(events: list) -> None:
    pending = list(events)
    seen = set()
    while pending:
        entry = pending.pop()
        if not isinstance(entry, dict) or id(entry) in seen:
            continue
        seen.add(id(entry))
        if "author" not in entry and isinstance(entry.get("text"), str):
            prefix = timeline_prefix(entry["text"])
            if prefix:
                entry["author"] = TIMELINE_AUTHOR_PREFIXES[prefix]
        if isinstance(entry.get("children"), list):
            pending.extend(entry["children"])


def normalize_timeline(events: list) -> list:
    """Copy the timeline, filling only absent authors with literal prefix evidence."""
    copied = copy_json(events)
    _attribute_timeline(copied)
    return copied


def normalize(data: dict) -> dict:
    """Return a copy with defaults filled in and older field names mapped.

    Older roadmaps used "issue" and "issue_url" for the forge reference; they
    become "ref" and "url". Gates become objects so every reader can see
    whether each one passed.
    """
    data = copy_json(data)
    data.setdefault("gates", dict(DEFAULT_GATES))
    data.setdefault("epics", [])
    data.setdefault("issues", [])
    events = data.setdefault("timeline", [])
    if isinstance(events, list):
        _attribute_timeline(events)
    data.setdefault("iterations", [])
    for ep in data["epics"]:
        if isinstance(ep, dict):
            ep.setdefault("note", "")
    for it in data["issues"]:
        if not isinstance(it, dict):
            continue
        if "issue" in it and "ref" not in it:
            it["ref"] = it.pop("issue")
        else:
            it.pop("issue", None)
        if "issue_url" in it and "url" not in it:
            it["url"] = it.pop("issue_url")
        else:
            it.pop("issue_url", None)
        if it.get("ref") is None:
            it.pop("ref", None)
        if it.get("url") is None:
            it.pop("url", None)
        it.setdefault("detail", "")
        it.setdefault("depends_on", [])
        it["gates"] = [gate_obj(g) for g in it.get("gates", []) if g]
        it.setdefault("links", [])
    return data


def issues_by_id(data: dict) -> dict:
    return {i["id"]: i for i in data["issues"]}


def coordinators(data: dict) -> dict:
    orchestration = data.get("orchestration", {})
    if isinstance(orchestration, dict) and isinstance(orchestration.get("coordinators"), dict):
        return orchestration["coordinators"]
    return {}


def label(it: dict) -> str:
    """How an issue is named on the page: its forge reference once published."""
    return it.get("ref") or it["id"]


def is_ready(it: dict, items: dict) -> bool:
    """To do, and every dependency is Done."""
    return it["status"] == "to_do" and all(
        items[d]["status"] == "done" for d in it.get("depends_on", []) if d in items)


def open_gates(it: dict) -> list[str]:
    return [g["gate"] for g in it.get("gates", []) if not g.get("passed")]
