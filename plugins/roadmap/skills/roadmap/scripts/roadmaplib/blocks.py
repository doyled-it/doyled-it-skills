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
DRIFT_START, DRIFT_END = "<!-- roadmap:drift:start -->", "<!-- roadmap:drift:end -->"
# A checklist line as issue_block writes it: "- [x] R: what the gate checks (link)".
TICK = re.compile(r"^[ \t]*[-*] \[(?P<x>[ xX])\] (?P<gate>[A-Z]):(?P<rest>.*)$", re.MULTILINE)
URL = re.compile(r"https?://[^\s)>\]]+")

# Mermaid colors per status: fill and stroke readable in light and dark themes.
MERMAID_STYLE = {
    "to_do": "fill:#f4f6f9,stroke:#5d6b7f,color:#17243a",
    "in_progress": "fill:#e8effa,stroke:#2556a8,color:#17243a,stroke-width:2px",
    "in_review": "fill:#fbf1dd,stroke:#b7790c,color:#17243a,stroke-width:2px",
    "blocked": "fill:#fbe7e5,stroke:#a3302a,color:#17243a,stroke-width:2px",
    "done": "fill:#e6f2ec,stroke:#2f7d5b,color:#17243a",
}


# A line shaped like a GitLab quick action: "/word" alone or before a space
# (/close, /move x). Generated text escapes every such line wherever it sits.
COMMAND_LINE = re.compile(r"^([ \t]*)/(?=[^\s/]+(?:[ \t]|$))", re.MULTILINE)
# GitLab's quick action names and aliases (its quick actions documentation).
# GitLab runs a line only when it names one of these, so prose such as
# "/etc is full" is never held back. Text the tool writes is escaped whatever
# the name (defang), so this list matters only for hand text. Names the current
# docs no longer list stay, for older self-managed GitLab: holding back too much
# is the safe side.
GITLAB_COMMANDS = frozenset("""
    add_child add_contacts add_email approve assign assign_reviewer award blocked_by blocks board_move cc
    checkin_reminder child_epic clear_health_status clear_weight clone close confidential convert_to_ticket
    copy_metadata create_merge_request done draft due duplicate epic estimate estimate_time health_status
    internal_note invite_email iteration label labels link lock merge milestone move page parent_epic promote
    promote_to promote_to_incident publish q react ready reassign reassign_reviewer rebase relabel relate
    remove_child remove_child_epic remove_contacts remove_due_date remove_email remove_epic remove_estimate
    remove_iteration remove_label remove_milestone remove_parent remove_parent_epic remove_reviewer
    remove_time_estimate remove_time_spent remove_zoom reopen request_review reviewer run_pipeline set_parent
    severity shrug spend spend_time spent status submit_review subscribe summarize_diff tableflip tag
    target_branch timeline title todo type unapprove unassign unassign_reviewer unlabel unlink unlock unsubscribe
    weight wip zoom
""".split())
# How GitLab finds the quick actions it runs, scanning left to right as its own
# extractor does: a command counts only at the very start of a line and outside
# a ``` code block, an HTML block and a >>> quote, and only when its name is in
# GITLAB_COMMANDS (any case).
GITLAB_SCAN = re.compile(r"""
    (?P<code>^```.+?\n```$)
  | (?P<html>^<[^>]+?>\n.+?\n</[^>]+?>$)
  | (?P<quote>^>>>.+?\n>>>$)
  | (?P<cmd>^/[^\s/]+(?:[ ][^\n]*)?)(?:\s*\n|\s*$)
""", re.MULTILINE | re.DOTALL | re.IGNORECASE | re.VERBOSE)
# Control characters that would let one field spill onto another line.
CONTROL = re.compile(r"[\x00-\x1f\x7f\u2028\u2029]")
FENCE_OR_LIST = re.compile(r"^([ \t]*)(```|~~~|#{1,6} |[-*+] \[)", re.MULTILINE)


def defang(text: str) -> str:
    """Escape the slash of every line that starts with one, so no forge runs it as a command.

    Markdown shows "\\/close" as "/close"; GitLab no longer sees a quick action.
    """
    return COMMAND_LINE.sub(lambda m: m.group(1) + "\\/", str(text or ""))


def gitlab_commands(text) -> list[str]:
    """The lines of text GitLab would run as quick actions if it were written to a description."""
    found = []
    for m in GITLAB_SCAN.finditer(str(text or "").replace("\r", "")):
        if m.group("cmd") and m.group("cmd")[1:].split(" ", 1)[0].lower() in GITLAB_COMMANDS:
            found.append(m.group("cmd").rstrip())
    return found


def one_line(text) -> str:
    """Text with every control character and line break turned into a single space."""
    return re.sub(r"\s+", " ", CONTROL.sub(" ", str(text if text is not None else ""))).strip()


def md_inline(text) -> str:
    """One line of plain text, safe inside a table cell, a list item or a heading.

    Markdown link, code and table syntax is escaped and angle brackets become
    entities, so a title cannot add a link, a hidden comment or a marker.
    """
    out = one_line(text).replace("\\", "\\\\")
    for ch in "`[]|":
        out = out.replace(ch, "\\" + ch)
    return out.replace("<", "&lt;").replace(">", "&gt;")


def md_block(text) -> str:
    """Several lines of plain text, safe as paragraphs inside a generated section.

    Lines cannot run forge commands, open a code fence, start a heading or a
    task list line, or hold HTML (and so no hidden comment or marker).
    """
    lines = [CONTROL.sub(" ", ln) for ln in str(text or "").replace("\r\n", "\n").split("\n")]
    out = "\n".join(ln.rstrip() for ln in lines).replace("<", "&lt;").replace(">", "&gt;")
    out = FENCE_OR_LIST.sub(lambda m: m.group(1) + "\\" + m.group(2), out)
    return defang(out)


class MarkerError(Exception):
    """A description's markers are not one well-formed pair; nothing is written."""


MARKERS = (ISSUE_START, ISSUE_END, EPIC_START, EPIC_END, DRIFT_START, DRIFT_END)
# Anything that looks like a roadmap marker, however it was edited.
LOOSE_MARKER = re.compile(r"<!--\s*roadmap\s*:", re.IGNORECASE)


FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
INDENTED = re.compile(r"^(?: {4}| {0,3}\t)")


def _scan(body: str) -> tuple[list[tuple[str, int, int]], bool]:
    """Each marker line as (marker, start offset, end offset without the newline), and
    whether the description ends inside a code block that never closes.

    A marker counts only when it is alone on its line (up to three spaces of
    indent) and outside fenced and indented code: a marker quoted in a code
    block, or in inline code, is an example. Anything else that looks like a
    marker (edited, run into other text, unclosed) raises MarkerError.
    """
    found, offset, fence, fence_line = [], 0, None, 0
    for n, line in enumerate(body.splitlines(keepends=True), 1):
        text = line.rstrip("\r\n")
        if fence:
            close = FENCE_OPEN.match(text)
            if close and close.group(1)[0] == fence[0] and len(close.group(1)) >= len(fence) \
                    and not close.group(2).strip():
                fence = None
        elif (m := FENCE_OPEN.match(text)) and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence, fence_line = m.group(1), n
        elif INDENTED.match(text):
            pass   # indented code
        elif text.strip() in MARKERS:
            found.append((text.strip(), offset, offset + len(text)))
        else:
            for m in LOOSE_MARKER.finditer(text):
                if text[:m.start()].count("`") % 2 == 0:
                    raise MarkerError(f'line {n} looks like a roadmap marker but is not exactly one on its own '
                                      f'line ("{text.strip()[:60]}"); fix it by hand')
        offset += len(line)
    if fence and LOOSE_MARKER.search("".join(body.splitlines(keepends=True)[fence_line:])):
        raise MarkerError(f"the code block opened on line {fence_line} never closes and holds roadmap markers; "
                          "close it by hand")
    return found, fence is not None


def _real_markers(body: str) -> list[tuple[str, int, int]]:
    return _scan(body)[0]


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
    if _scan(body)[1]:
        raise MarkerError("the description ends inside a code block that never closes, so a new section would "
                          "land inside it; close the code block by hand")
    if not body.strip():
        return block
    sep = "" if body.endswith("\n\n") else "\n" if body.endswith("\n") else "\n\n"
    return body + sep + block


def ticked_gates(body: str) -> dict[str, str | None]:
    """Gates ticked in the generated checklist: letter -> first http(s) link on that line.

    Only lines inside the description's one well-formed issue block count; a
    checkbox anywhere else is ignored, and so is a broken block.
    """
    content = block_content(body or "", ISSUE_START, ISSUE_END)
    out: dict[str, str | None] = {}
    for m in TICK.finditer(content or ""):
        if m["x"].lower() == "x":
            links = [u for u in URL.findall(m["rest"]) if model.safe_url(u)]
            out.setdefault(m["gate"], links[0] if links else None)
    return out


def merged_gates(it: dict, forge_body: str, never: set[str] | frozenset = frozenset()) -> list[dict]:
    """The issue's gates with checklist ticks added; a tick is never removed.

    Gates in never (model.unchecked_gates: the lead's gates, and M or any gate
    with a merge request rule) are never taken from a checkbox.
    """
    ticks = ticked_gates(forge_body)
    out = []
    for g in it["gates"]:
        g = dict(g)
        if not g["passed"] and g["gate"] in ticks and g["gate"] not in never:
            g["passed"] = True
            if ticks[g["gate"]]:
                g["evidence"] = ticks[g["gate"]]
        out.append(g)
    return out


def issue_block(data: dict, it: dict, gates: list[dict], epic_name: str) -> str:
    deps = ", ".join(f"`{d}`" for d in it["depends_on"]) or "nothing"
    lines = [f"Roadmap issue `{it['id']}` in epic **{md_inline(epic_name)}** ({md_inline(data['title'])}, "
             f"{md_inline(data.get('version', ''))}). Depends on: {deps}.", "", "### Gates", ""]
    for g in gates:
        meaning = md_inline(data["gates"].get(g["gate"], ""))
        evidence = model.safe_url(g.get("evidence"))
        tail = f" ({evidence})" if g.get("passed") and evidence else ""
        lines.append(f"- [{'x' if g['passed'] else ' '}] {g['gate']}: {meaning}{tail}")
    lines += ["", "_This section is generated from the roadmap; edit the roadmap, not this section._"]
    return "\n".join(lines)


def issue_body(data: dict, it: dict, forge_body: str, epic_name: str) -> str:
    gates = merged_gates(it, forge_body, model.unchecked_gates(data))
    return replace_block(forge_body, ISSUE_START, ISSUE_END, issue_block(data, it, gates, epic_name))


def _node_id(iid: str) -> str:
    return "i_" + re.sub(r"[^A-Za-z0-9_]", "_", iid)


def _mm(text: str) -> str:
    """Text safe inside a quoted Mermaid label."""
    return one_line(text).replace('"', "'").replace("<", "(").replace(">", ")").replace("#", "#35;").replace(
        "`", "'")


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
    if model.safe_url(it.get("url")):
        return f"[{md_inline(it.get('ref') or it['id'])}]({it['url']})"
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

    page = model.safe_url(data.get("page_url"))
    version = md_inline(f"{data['title']}, {data.get('version', '')}, {data.get('date', '')}")
    head = (f"**Roadmap:** [{version}]({page})" if page
            else f"**Roadmap:** {version}. The full roadmap page is kept by the program lead.")
    lines = [head, "", md_block(epic.get("note", "")).strip(), "", "```mermaid", "flowchart LR"]

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
        if model.safe_url(it.get("url")):
            lines.append(f'  click {_node_id(it["id"])} href "{it["url"]}" _blank')
    lines += ["```", "", "Solid arrows: depends on. Dashed arrows: depends on an issue in another epic.", "",
              "| Issue | Title | Status | Gates passed | Depends on |", "| --- | --- | --- | --- | --- |"]
    for it in mine:
        passed = " ".join(g["gate"] for g in it["gates"] if g["passed"]) or "none"
        total = " ".join(g["gate"] for g in it["gates"]) or "none"
        deps = ", ".join(_issue_link(items[d]) if model.safe_url(items[d].get("url")) else f"`{d}`"
                         for d in it["depends_on"]) or "nothing"
        lines.append(f"| {_issue_link(it)} | {md_inline(it['title'])} | {model.STATUSES[it['status']]} | "
                     f"{passed} of {total} | {deps} |")
    if task_list:
        lines += ["", "### Issues in this epic", ""]
        for it in mine:
            tick = "x" if it["status"] == "done" else " "
            name = it.get("ref") or f"{it['id']} (not on the forge yet)"
            lines.append(f"- [{tick}] {name} {md_inline(it['title'])}")
    lines += ["", "_This section is generated from the roadmap; edit the roadmap, not this section._"]
    return "\n".join(lines)


def epic_body(raw: dict, epic_id: str, forge_body: str, task_list: bool = False) -> str:
    return replace_block(forge_body, EPIC_START, EPIC_END, epic_block(raw, epic_id, task_list))


def epic_members(body: str) -> set[str]:
    """Issue references listed in the task list of an epic's one well-formed block."""
    content = block_content(body or "", EPIC_START, EPIC_END)
    if content is None:
        return set()
    section = ("\n" + content).rsplit("\n### Issues in this epic\n", 1)
    if len(section) < 2:
        return set()
    return set(re.findall(r"^- \[[ xX]\] ([\w.-]+/[\w.-]+#\d+)", section[1], re.MULTILINE))
