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
    if g.get("evidence"):
        out["evidence"] = g["evidence"]
    return out


def normalize(data: dict) -> dict:
    """Return a copy with defaults filled in and older field names mapped.

    Older roadmaps used "issue" and "issue_url" for the forge reference; they
    become "ref" and "url". Gates become objects so every reader can see
    whether each one passed.
    """
    data = copy.deepcopy(data)
    data.setdefault("gates", dict(DEFAULT_GATES))
    data.setdefault("epics", [])
    data.setdefault("issues", [])
    data.setdefault("timeline", [])
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


def label(it: dict) -> str:
    """How an issue is named on the page: its forge reference once published."""
    return it.get("ref") or it["id"]


def is_ready(it: dict, items: dict) -> bool:
    """To do, and every dependency is Done."""
    return it["status"] == "to_do" and all(
        items[d]["status"] == "done" for d in it.get("depends_on", []) if d in items)


def open_gates(it: dict) -> list[str]:
    return [g["gate"] for g in it.get("gates", []) if not g.get("passed")]
