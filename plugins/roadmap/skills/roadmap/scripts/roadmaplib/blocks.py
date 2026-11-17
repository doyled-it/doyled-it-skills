"""Generated sections inside forge descriptions.

Each generated section sits between hidden start and end markers. Only the text
between the markers is ever replaced; hand-written text outside them is kept
exactly as it was.

- Issue block: which roadmap issue this is, and the gate checklist.
- Epic block: a link to the full roadmap page, a Mermaid flowchart of the epic's
  issues (with arrows to and from other epics), and a small status table.
"""

from __future__ import annotations

import re

from . import model

ISSUE_START, ISSUE_END = "<!-- roadmap:start -->", "<!-- roadmap:end -->"
EPIC_START, EPIC_END = "<!-- roadmap:epic:start -->", "<!-- roadmap:epic:end -->"
TICK = re.compile(r"^\s*[-*] \[(?P<x>[ xX])\] (?P<gate>[A-Z])\b[:.)]?(?P<rest>.*)$", re.MULTILINE)
URL = re.compile(r"https?://[^\s)>\]]+")

# Mermaid colors per status: fill and stroke readable in light and dark themes.
MERMAID_STYLE = {
    "to_do": "fill:#f4f6f9,stroke:#5d6b7f,color:#17243a",
    "in_progress": "fill:#e8effa,stroke:#2556a8,color:#17243a,stroke-width:2px",
    "in_review": "fill:#fbf1dd,stroke:#b7790c,color:#17243a,stroke-width:2px",
    "blocked": "fill:#fbe7e5,stroke:#a3302a,color:#17243a,stroke-width:2px",
    "done": "fill:#e6f2ec,stroke:#2f7d5b,color:#17243a",
}


class MarkerError(Exception):
    """A description's markers are not one well-formed pair; nothing is written."""


MARKERS = (ISSUE_START, ISSUE_END, EPIC_START, EPIC_END)
# Anything that looks like a roadmap marker, however it was edited.
LOOSE_MARKER = re.compile(r"<!--\s*roadmap\s*:", re.IGNORECASE)


def _real_markers(body: str) -> list[tuple[str, int, int]]:
    """Each marker line as (marker, start offset, end offset without the newline).

    A marker counts only when it is alone on its line. Marker text quoted in
    inline code is prose and ignored. Anything else that looks like a marker
    (edited, run into other text, unclosed) raises MarkerError.
    """
    found, offset = [], 0
    for n, line in enumerate(body.splitlines(keepends=True), 1):
        text = line.rstrip("\r\n")
        if text.strip() in MARKERS:
            found.append((text.strip(), offset, offset + len(text)))
        else:
            for m in LOOSE_MARKER.finditer(text):
                if text[:m.start()].count("`") % 2 == 0:
                    raise MarkerError(f'line {n} looks like a roadmap marker but is not exactly one on its own '
                                      f'line ("{text.strip()[:60]}"); fix it by hand')
        offset += len(line)
    return found


def find_block(body: str, start: str, end: str) -> tuple[int, int] | None:
    """Offsets of the one well-formed block, None when there is none.

    Raises MarkerError when the markers are missing on one side, duplicated,
    out of order, or edited: the description then needs a hand fix.
    """
    found = _real_markers(body or "")
    starts = [f for f in found if f[0] == start]
    ends = [f for f in found if f[0] == end]
    if not starts and not ends:
        return None
    if len(starts) == 1 and len(ends) == 1:
        if starts[0][1] < ends[0][1]:
            return starts[0][1], ends[0][2]
        raise MarkerError("the end marker comes before the start marker; fix the description by hand")
    raise MarkerError(f"the description has {len(starts)} start and {len(ends)} end markers where one of each "
                      "is expected; fix it by hand")


def block_content(body: str, start: str, end: str) -> str | None:
    """Text between the one well-formed pair, or None when there is none or it is broken."""
    try:
        span = find_block(body, start, end)
    except MarkerError:
        return None
    if span is None:
        return None
    return body[span[0]:span[1]].split("\n", 1)[1].rsplit("\n", 1)[0]


def replace_block(body: str, start: str, end: str, content: str) -> str:
    """Put content between the markers, appending the block if there is none.

    Text outside the one well-formed pair is kept byte for byte. Broken markers
    raise MarkerError and nothing changes.
    """
    if LOOSE_MARKER.search(content):
        raise ValueError("generated content must not contain marker text")
    block = f"{start}\n{content.strip()}\n{end}"
    body = body or ""
    span = find_block(body, start, end)
    if span:
        return body[:span[0]] + block + body[span[1]:]
    if not body.strip():
        return block
    sep = "" if body.endswith("\n\n") else "\n" if body.endswith("\n") else "\n\n"
    return body + sep + block


def ticked_gates(body: str) -> dict[str, str | None]:
    """Gates ticked anywhere in a description: letter -> first link on that line."""
    out: dict[str, str | None] = {}
    for m in TICK.finditer(body or ""):
        if m["x"].lower() == "x":
            link = URL.search(m["rest"])
            out.setdefault(m["gate"], link.group(0) if link else None)
    return out


def merged_gates(it: dict, forge_body: str) -> list[dict]:
    """The issue's gates with forge ticks added; a tick is never removed."""
    ticks = ticked_gates(forge_body)
    out = []
    for g in it["gates"]:
        g = dict(g)
        if not g["passed"] and g["gate"] in ticks:
            g["passed"] = True
            if ticks[g["gate"]]:
                g["evidence"] = ticks[g["gate"]]
        out.append(g)
    return out


def issue_block(data: dict, it: dict, gates: list[dict], epic_name: str) -> str:
    deps = ", ".join(f"`{d}`" for d in it["depends_on"]) or "nothing"
    lines = [f"Roadmap issue `{it['id']}` in epic **{epic_name}** ({data['title']}, {data.get('version', '')}). "
             f"Depends on: {deps}.", "", "### Gates", ""]
    for g in gates:
        meaning = data["gates"].get(g["gate"], "")
        tail = f" ({g['evidence']})" if g.get("passed") and g.get("evidence") else ""
        lines.append(f"- [{'x' if g['passed'] else ' '}] {g['gate']}: {meaning}{tail}")
    lines += ["", "_This section is generated from the roadmap; edit the roadmap, not this section._"]
    return "\n".join(lines)


def issue_body(data: dict, it: dict, forge_body: str, epic_name: str) -> str:
    gates = merged_gates(it, forge_body)
    return replace_block(forge_body, ISSUE_START, ISSUE_END, issue_block(data, it, gates, epic_name))


def _node_id(iid: str) -> str:
    return "i_" + re.sub(r"[^A-Za-z0-9_]", "_", iid)


def _mm(text: str) -> str:
    """Text safe inside a quoted Mermaid label."""
    return str(text).replace('"', "'").replace("<", "(").replace(">", ")").replace("#", "#35;")


def _gate_words(it: dict) -> str:
    passed = [g["gate"] for g in it["gates"] if g["passed"]]
    todo = [g["gate"] for g in it["gates"] if not g["passed"]]
    parts = []
    if passed:
        parts.append("passed " + " ".join(passed))
    if todo:
        parts.append("to go " + " ".join(todo))
    return "Gates: " + ("; ".join(parts) if parts else "none")


def _issue_link(it: dict) -> str:
    if it.get("url"):
        return f"[{it.get('ref') or it['id']}]({it['url']})"
    return f"`{it['id']}` (not on the forge yet)"


def epic_block(raw: dict, epic_id: str, task_list: bool = False) -> str:
    """Markdown for one epic: roadmap link, Mermaid flowchart, status table.

    task_list adds a checklist of the epic's issues. A forge with no epics or
    sub-issues (Forgejo, Codeberg) uses that list as the epic's membership.
    """
    data = model.normalize(raw)
    items = model.issues_by_id(data)
    epics = {e["id"]: e for e in data["epics"]}
    epic = epics[epic_id]
    mine = [i for i in items.values() if i["epic"] == epic_id]
    mine_ids = {i["id"] for i in mine}
    # Issues in other epics that this epic depends on, or that depend on it.
    outside = []
    for it in items.values():
        if it["id"] in mine_ids:
            continue
        if any(d in mine_ids for d in it["depends_on"]) or any(it["id"] in m["depends_on"] for m in mine):
            outside.append(it)

    page = data.get("page_url")
    version = f"{data['title']}, {data.get('version', '')}, {data.get('date', '')}"
    head = (f"**Roadmap:** [{version}]({page})" if page
            else f"**Roadmap:** {version}. The full roadmap page is kept by the program lead.")
    lines = [head, "", f"{epic.get('note', '')}".strip(), "", "```mermaid", "flowchart LR"]

    def node(it, prefix=""):
        status = model.STATUSES[it["status"]]
        name = it.get("ref") or it["id"]
        label = f"{prefix}{_mm(name)}<br/>{_mm(it['title'])}<br/>{status}<br/>{_gate_words(it)}"
        return f'  {_node_id(it["id"])}["{label}"]'

    lines.append(f'  subgraph this_epic["{_mm(epic["name"])}"]')
    for it in mine:
        lines.append("  " + node(it))
    lines.append("  end")
    for it in outside:
        lines.append(node(it, prefix=f"{_mm(epics[it['epic']]['name'])}: "))
    involved = mine + outside
    involved_ids = {i["id"] for i in involved}
    for it in involved:
        for d in it["depends_on"]:
            if d not in involved_ids:
                continue
            if it["id"] not in mine_ids and d not in mine_ids:
                continue
            arrow = "-.->" if items[d]["epic"] != it["epic"] else "-->"
            lines.append(f"  {_node_id(d)} {arrow} {_node_id(it['id'])}")
    for status, style in MERMAID_STYLE.items():
        lines.append(f"  classDef {status} {style}")
    for it in involved:
        lines.append(f"  class {_node_id(it['id'])} {it['status']}")
    for it in involved:
        if it.get("url"):
            lines.append(f'  click {_node_id(it["id"])} href "{it["url"]}" _blank')
    lines += ["```", "", "Solid arrows: depends on. Dashed arrows: depends on an issue in another epic.", "",
              "| Issue | Title | Status | Gates passed | Depends on |", "| --- | --- | --- | --- | --- |"]
    for it in mine:
        passed = " ".join(g["gate"] for g in it["gates"] if g["passed"]) or "none"
        total = " ".join(g["gate"] for g in it["gates"]) or "none"
        deps = ", ".join(_issue_link(items[d]) if items[d].get("url") else f"`{d}`" for d in it["depends_on"]) or "nothing"
        lines.append(f"| {_issue_link(it)} | {it['title'].replace('|', '/')} | {model.STATUSES[it['status']]} | "
                     f"{passed} of {total} | {deps} |")
    if task_list:
        lines += ["", "### Issues in this epic", ""]
        for it in mine:
            tick = "x" if it["status"] == "done" else " "
            name = it.get("ref") or f"{it['id']} (not on the forge yet)"
            lines.append(f"- [{tick}] {name} {it['title']}")
    lines += ["", "_This section is generated from the roadmap; edit the roadmap, not this section._"]
    return "\n".join(lines)


def epic_body(raw: dict, epic_id: str, forge_body: str, task_list: bool = False) -> str:
    return replace_block(forge_body, EPIC_START, EPIC_END, epic_block(raw, epic_id, task_list))


def epic_members(body: str) -> set[str]:
    """Issue references listed in an epic block's task list."""
    m = re.search(re.escape(EPIC_START) + r"(.*?)" + re.escape(EPIC_END), body or "", re.DOTALL)
    if not m:
        return set()
    section = m.group(1).split("### Issues in this epic", 1)
    if len(section) < 2:
        return set()
    return set(re.findall(r"^- \[[ xX]\] ([\w.-]+/[\w.-]+#\d+)", section[1], re.MULTILINE))
