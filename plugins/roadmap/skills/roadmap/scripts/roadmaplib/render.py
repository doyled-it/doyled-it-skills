"""render: the roadmap as one HTML page.

The page has epic swimlanes with issue boxes (status and gates), dependency
arrows (dashed when they cross epics), a legend, a "right now" panel, an issue
table per epic, and the timeline. It works in light and dark mode, and every
box is reachable by keyboard with a text description for screen readers.
"""

from __future__ import annotations

import html

from . import model, validate

# Findings that make a diagram impossible to draw. Glossary problems do not stop
# rendering: a draft has to be shown before it can be agreed and fixed.
BLOCKING = {"missing-field", "duplicate-id", "unknown-epic", "bad-status", "dangling-dependency",
            "cycle", "bad-type", "unknown-gate"}

COL_W, NODE_W, NODE_H = 300, 248, 112
LANE_PAD, LABEL_W, ROW_GAP = 22, 150, 18


class RenderError(Exception):
    """The roadmap has structural errors; the message lists them."""


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def wrap(text: str, width: int = 30, lines: int = 2) -> list[str]:
    words, out, cur = str(text).split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            out.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    out.append(cur)
    if len(out) > lines:
        out = out[:lines]
        out[-1] = out[-1].rstrip(".,") + "..."
    return out


def clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 3] + "..."


def _link(url, text) -> str:
    url = model.safe_url(url)
    return f'<a href="{esc(url)}">{esc(text)}</a>' if url else esc(text)


def _short(it: dict) -> str:
    """Short name, then the forge link once the issue is published."""
    if it.get("ref"):
        return f'{esc(it["id"])} ({_link(it.get("url"), it["ref"])})'
    return esc(it["id"])


def _layout(data: dict, items: dict):
    # Column = length of the longest dependency chain below the issue. Worked out
    # with an explicit stack: a chain of thousands of issues must not overflow it.
    level: dict[str, int] = {}
    for root in items:
        stack = [root]
        while stack:
            iid = stack[-1]
            if iid in level:
                stack.pop()
                continue
            waiting = [d for d in items[iid]["depends_on"] if d not in level]
            if waiting:
                stack.extend(waiting)
                continue
            deps = items[iid]["depends_on"]
            level[iid] = 0 if not deps else 1 + max(level[d] for d in deps)
            stack.pop()
    cols = max(level.values(), default=0) + 1
    pos, lane_top, lane_h = {}, {}, {}
    y = 0
    for ep in data["epics"]:
        rows, slot = 1, {}
        for iid, it in items.items():
            if it["epic"] != ep["id"]:
                continue
            c = level[iid]
            r = slot.get(c, 0)
            slot[c] = r + 1
            rows = max(rows, r + 1)
            pos[iid] = (c, r)
        h = LANE_PAD * 2 + rows * NODE_H + (rows - 1) * ROW_GAP
        lane_top[ep["id"]], lane_h[ep["id"]] = y, h
        y += h
    return pos, lane_top, lane_h, cols, y


def _svg(data: dict, items: dict) -> str:
    pos, lane_top, lane_h, cols, total_h = _layout(data, items)
    total_w = LABEL_W + cols * COL_W + 20

    def xy(iid):
        c, r = pos[iid]
        return LABEL_W + 26 + c * COL_W, lane_top[items[iid]["epic"]] + LANE_PAD + r * (NODE_H + ROW_GAP)

    out = [f'<svg class="flow" viewBox="0 0 {total_w} {total_h}" width="100%" '
           f'preserveAspectRatio="xMinYMin meet" style="min-width:{total_w}px" role="img" '
           f'aria-label="Roadmap flow: {len(data["epics"])} epics as lanes, {len(items)} issues as boxes, '
           f'arrows show what each issue depends on. The tables below list the same information.">',
           '<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" '
           'orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" class="arrowhead"/></marker></defs>']
    for n, ep in enumerate(data["epics"]):
        top, h = lane_top[ep["id"]], lane_h[ep["id"]]
        out.append(f'<rect class="lane{" alt" if n % 2 else ""}" x="0" y="{top}" width="{total_w}" height="{h}"/>')
        out.append(f'<rect class="lanehead" x="0" y="{top}" width="{LABEL_W - 14}" height="{h}"/>')
        out.append(f'<text class="lanelabel" x="18" y="{top + 30}">Epic</text>')
        name = "".join(f'<text class="lanename" x="18" y="{top + 54 + k * 19}">{esc(line)}</text>'
                       for k, line in enumerate(wrap(ep["name"], 14, 2)))
        out.append(f'<a href="{esc(ep["url"])}">{name}</a>' if model.safe_url(ep.get("url")) else name)

    # Arrows first so boxes sit on top. Each arrow turns in the gap just before
    # its target column, offset per incoming arrow so the vertical legs never overlap.
    for iid, it in items.items():
        x2, y2 = xy(iid)
        deps = it["depends_on"]
        for k, d in enumerate(deps):
            x1, y1 = xy(d)
            sx, sy = x1 + NODE_W, y1 + NODE_H / 2
            ex = x2 - 6
            ey = y2 + NODE_H / 2 + (k - (len(deps) - 1) / 2) * 12
            mx = ex - 16 - k * 9
            cross = " cross" if items[d]["epic"] != it["epic"] else ""
            out.append(f'<path class="edge{cross}" d="M{sx} {sy} H{mx} V{ey} H{ex}" marker-end="url(#arr)"/>')

    for iid, it in items.items():
        x, y = xy(iid)
        status = model.STATUSES[it["status"]]
        gates_text = ", ".join(f'{g["gate"]} {"passed" if g["passed"] else "open"}' for g in it["gates"]) or "none"
        deps_text = ", ".join(it["depends_on"]) or "nothing"
        url = model.safe_url(it.get("url"))
        if url:
            out.append(f'<a href="{esc(url)}">')
        focus = "" if url else ' tabindex="0"'
        out.append(f'<g class="node {model.STATUS_CLASS[it["status"]]}"{focus}>'
                   f'<title>{esc(model.label(it))}: {esc(it["title"])}. {esc(it["detail"])}. Status {esc(status)}. '
                   f'Depends on {esc(deps_text)}. Gates: {esc(gates_text)}.</title>')
        out.append(f'<rect class="box" x="{x}" y="{y}" width="{NODE_W}" height="{NODE_H}" rx="10"/>')
        out.append(f'<rect class="stripe" x="{x}" y="{y}" width="6" height="{NODE_H}" rx="3"/>')
        out.append(f'<text class="nid" x="{x + 18}" y="{y + 24}">{esc(clip(model.label(it), 26))}</text>')
        out.append(f'<text class="nstatus" x="{x + NODE_W - 14}" y="{y + 24}" text-anchor="end">{esc(status)}</text>')
        for k, line in enumerate(wrap(it["title"], 30, 2)):
            out.append(f'<text class="ntitle" x="{x + 18}" y="{y + 48 + k * 18}">{esc(line)}</text>')
        gx = x + 18
        for g in it["gates"]:
            cls = "gate passed" if g["passed"] else "gate"
            out.append(f'<g class="{cls}"><rect x="{gx}" y="{y + NODE_H - 30}" width="22" height="20" rx="4"/>'
                       f'<text x="{gx + 11}" y="{y + NODE_H - 15}" text-anchor="middle">{esc(g["gate"])}</text></g>')
            gx += 27
        out.append("</g></a>" if url else "</g>")
    out.append("</svg>")
    return "".join(out)


def _gate_chips(data: dict, it: dict) -> str:
    chips = []
    for g in it["gates"]:
        meaning = data["gates"].get(g["gate"], "")
        state = "passed" if g["passed"] else "not passed yet"
        chip = (f'<span class="g{" done" if g["passed"] else ""}" title="{esc(meaning)}, {state}">'
                f'{esc(g["gate"])}<span class="sr"> {state}</span></span>')
        url = model.safe_url(g.get("evidence"))
        chips.append(f'<a href="{esc(url)}">{chip}</a>' if url else chip)
    return " ".join(chips) or "none"


def _epic_table(data: dict, ep: dict, items: dict, with_iteration: bool) -> str:
    rows = []
    for iid, it in items.items():
        if it["epic"] != ep["id"]:
            continue
        status = model.STATUSES[it["status"]]
        cls = model.STATUS_CLASS[it["status"]]
        after = ", ".join(it["depends_on"]) or "nothing"
        ref = f'<span class="ref">{_link(it.get("url"), it["ref"])}</span>' if it.get("ref") else ""
        extra = "".join(f'<span class="xlink">{_link(lk.get("url"), lk.get("label") or lk.get("url"))}</span>'
                        if isinstance(lk, dict) else f'<span class="xlink">{_link(lk, lk)}</span>'
                        for lk in it.get("links", []))
        mrs = "".join(
            f'<span class="mr">{_link(m.get("url"), m.get("ref"))} {esc(m.get("state", ""))}'
            f'{" (draft)" if m.get("draft") else ""}'
            + (f', {_link(m.get("pipeline_url"), "pipeline " + m["pipeline"])}' if m.get("pipeline") else "")
            + "</span>" for m in it.get("merge_requests", []))
        extra += mrs
        iteration = f'<td>{esc(it.get("iteration", ""))}</td>' if with_iteration else ""
        rows.append(f'<tr><th scope="row">{esc(iid)}{ref}</th><td><strong>{esc(it["title"])}</strong>'
                    f'<span class="det">{esc(it["detail"])}</span>{extra}</td><td>{esc(after)}</td>'
                    f'<td class="gates">{_gate_chips(data, it)}</td>{iteration}'
                    f'<td><span class="pill {cls}">{esc(status)}</span></td></tr>')
    head = ("<th scope=\"col\">Issue</th><th scope=\"col\">What it delivers</th><th scope=\"col\">Depends on</th>"
            "<th scope=\"col\">Gates</th>" + ("<th scope=\"col\">Iteration</th>" if with_iteration else "")
            + "<th scope=\"col\">Status</th>")
    body = "".join(rows) or f'<tr><td colspan="{6 if with_iteration else 5}">No issues yet.</td></tr>'
    title = _link(ep.get("url"), ep["name"])
    ref = f' <span class="ref">{_link(ep.get("url"), ep["ref"])}</span>' if ep.get("ref") else ""
    return (f'<div class="track"><h3><span class="tid">Epic</span>{title}{ref}</h3>'
            f'<p class="tnote">{esc(ep.get("note", ""))}</p><div class="tablewrap"><table><thead><tr>{head}</tr></thead>'
            f'<tbody>{body}</tbody></table></div></div>')


def render_page(raw: dict) -> str:
    """Return the full HTML page, or raise RenderError on structural errors."""
    blocking = [f for f in validate.errors(validate.check(raw)) if f.code in BLOCKING]
    if blocking:
        raise RenderError("cannot render:\n" + "\n".join(str(f) for f in blocking))
    data = model.normalize(raw)
    items = model.issues_by_id(data)

    active = [i for i, it in items.items() if it["status"] in model.ACTIVE]
    blocked = [i for i, it in items.items() if it["status"] == "blocked"]
    ready = [i for i, it in items.items() if model.is_ready(it, items)]
    waiting = [i for i, it in items.items() if it["status"] == "to_do" and i not in ready]

    def names(ids):
        return ", ".join(_short(items[i]) for i in ids) or "none"

    waiting_text = ", ".join(
        f'{_short(items[w])} (depends on '
        f'{esc(", ".join(d for d in items[w]["depends_on"] if items[d]["status"] != "done"))})'
        for w in waiting) or "none"

    if data.get("agreed"):
        who = data.get("agreed_by")
        state = f"Agreed with {who}" if who else "Agreed"
    else:
        state = "Draft, not yet agreed"
    gate_legend = "".join(f'<li><span class="g">{esc(k)}</span>{esc(v)}</li>' for k, v in data["gates"].items())
    status_legend = "".join(f'<li><span class="pill {model.STATUS_CLASS[k]}">{esc(v)}</span></li>'
                            for k, v in model.STATUSES.items())
    timeline = "".join(f'<li><time>{esc(e.get("date", ""))}</time><p>{esc(e.get("text", ""))}</p></li>'
                       for e in data["timeline"])
    with_iteration = any(it.get("iteration") for it in items.values())
    tables = "".join(_epic_table(data, ep, items, with_iteration) for ep in data["epics"])

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(data["title"])}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><main class="wrap">
<header class="top"><h1>{esc(data["title"])}</h1>
<div class="state{" ok" if data.get("agreed") else ""}"><b>{esc(state)}</b>{esc(data.get("version", ""))}, {esc(data.get("date", ""))}</div>
<p class="meta">Epics run in parallel. Arrows mean "depends on"; dashed amber arrows cross epics. Boxes list their gates; filled gates have passed.</p></header>
<p class="goal">{esc(data["goal"])}</p><p class="rule">{esc(data["rule"])}</p>
<h2>Flow</h2><div class="scroller" tabindex="0" aria-label="Roadmap flow diagram, scrolls sideways">{_svg(data, items)}</div>
<section class="legend" aria-label="Legend"><div><h3>Gates</h3><ul>{gate_legend}
<li><span class="g done">D</span>Filled: gate passed</li></ul></div>
<div><h3>Status</h3><ul class="status">{status_legend}</ul>
<h3>Arrows</h3><ul><li><svg width="44" height="12" aria-hidden="true"><path class="keyedge" d="M2 6H34" marker-end="url(#arr)"/></svg>Depends on: the issue at the arrow tip waits for the one at its tail</li>
<li><svg width="44" height="12" aria-hidden="true"><path class="keyedge keycross" d="M2 6H34" marker-end="url(#arr)"/></svg>Depends on an issue in another epic</li></ul></div></section>
<section id="right-now"><h2>Right now</h2><div class="now">
<div><h3>In progress or in review</h3><p>{names(active)}</p></div>
<div><h3>Blocked</h3><p>{names(blocked)}</p></div>
<div><h3>Ready to start</h3><p>{names(ready)}</p></div>
<div><h3>Waiting on dependencies</h3><p>{waiting_text}</p></div></div></section>
<h2>Issues by epic</h2><div class="tracks">{tables}</div>
<h2>Timeline</h2><ol class="timeline">{timeline}</ol>
</main></body></html>
"""


CSS = """
:root { --ink:#17243a; --ink2:#4a5a70; --ink3:#5d6b7f; --canvas:#eef1f5; --surface:#fff; --surface2:#f7f8fa;
  --rule:#d6dce4; --action:#2556a8; --actiontint:#e8effa; --amber:#b7790c; --ambertext:#7a5208; --ambertint:#fbf1dd;
  --done:#2f7d5b; --donetint:#e6f2ec; --muted:#9aa6b5; --danger:#a3302a; color-scheme:light dark; }
@media (prefers-color-scheme: dark) { :root { --ink:#e6ebf2; --ink2:#b5c0cf; --ink3:#93a1b4; --canvas:#11161e;
  --surface:#18202b; --surface2:#1d2633; --rule:#2c3747; --action:#7fa8f0; --actiontint:#1e2c45; --amber:#e0a944;
  --ambertext:#f0c879; --ambertint:#3a2f17; --done:#5fbf92; --donetint:#173226; --muted:#5f6d80; --danger:#f08a83; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--canvas); color:var(--ink); font:400 15px/1.55 "Public Sans",system-ui,sans-serif;
  font-variant-numeric:tabular-nums; }
a { color:var(--action); }
a:focus-visible, .scroller:focus-visible { outline:2.5px solid var(--action); outline-offset:2px; }
.sr { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; }
.wrap { max-width:1320px; margin:0 auto; padding:36px 24px 72px; }
header.top { display:grid; grid-template-columns:1fr auto; gap:6px 28px; align-items:end; border-bottom:1px solid var(--rule);
  padding-bottom:22px; }
h1 { margin:0; font-size:30px; line-height:1.15; font-weight:600; letter-spacing:-0.01em; }
.meta { color:var(--ink3); font-size:14px; margin:0; }
.state { grid-column:2; grid-row:1 / span 2; text-align:right; font-size:14px; }
.state b { display:block; font-size:16px; color:var(--ambertext); font-weight:600; }
.state.ok b { color:var(--done); }
.goal { max-width:78ch; color:var(--ink2); margin:18px 0 6px; }
.rule { max-width:78ch; color:var(--ink2); font-size:14px; margin:0; }
h2 { font-size:19px; margin:36px 0 12px; font-weight:600; }
.scroller { overflow-x:auto; background:var(--surface); border:1px solid var(--rule); border-radius:12px; }
.flow { display:block; }
.lane { fill:var(--surface); } .lane.alt { fill:var(--surface2); }
.lanehead { fill:var(--canvas); }
.lanelabel { font:600 12px "Public Sans",system-ui,sans-serif; fill:var(--ink3); }
.lanename { font:600 15px "Public Sans",system-ui,sans-serif; fill:var(--ink); }
a .lanename { fill:var(--action); text-decoration:underline; }
.edge, .keyedge { fill:none; stroke:var(--ink3); stroke-width:1.6; }
.edge.cross, .keyedge.keycross { stroke:var(--amber); stroke-dasharray:5 4; }
.arrowhead { fill:var(--ink3); }
.node .box { fill:var(--surface); stroke:var(--rule); stroke-width:1.2; }
a:focus .node .box, .node:focus .box, .node:hover .box { stroke:var(--action); stroke-width:2.5; } .node:focus { outline:none; }
.node .stripe { fill:var(--muted); }
.node.prog .stripe { fill:var(--action); } .node.prog .box { stroke:var(--action); }
.node.review .stripe { fill:var(--amber); } .node.block .stripe { fill:var(--danger); }
.node.done .stripe { fill:var(--done); } .node.done .box { fill:var(--donetint); }
.node.todo .ntitle { fill:var(--ink2); }
.nid { font:600 12.5px "Public Sans",system-ui,sans-serif; fill:var(--ink3); }
.nstatus { font:600 12px "Public Sans",system-ui,sans-serif; fill:var(--ink3); }
.node.prog .nstatus { fill:var(--action); } .node.review .nstatus { fill:var(--ambertext); }
.node.block .nstatus { fill:var(--danger); } .node.done .nstatus { fill:var(--done); }
.ntitle { font:600 14.5px "Public Sans",system-ui,sans-serif; fill:var(--ink); }
.gate rect { fill:var(--actiontint); stroke:var(--action); stroke-width:1; }
.gate text { font:700 11.5px "Public Sans",system-ui,sans-serif; fill:var(--action); }
.gate.passed rect { fill:var(--action); } .gate.passed text { fill:var(--surface); }
.legend { display:grid; grid-template-columns:2fr 1fr; gap:22px; margin-top:16px; }
.legend h3 { margin:18px 0 8px; font-size:15px; }
.legend ul { list-style:none; margin:0; padding:0; }
.legend li { display:flex; gap:10px; align-items:center; font-size:14px; color:var(--ink2); margin:3px 0; }
.legend .status li { display:inline-flex; margin-right:6px; }
.g { display:inline-grid; place-items:center; min-width:22px; height:20px; padding:0 5px; border-radius:4px;
  background:var(--actiontint); color:var(--action); font-weight:700; font-size:11.5px; border:1px solid var(--action); }
.g.done { background:var(--action); color:var(--surface); }
.pill { display:inline-block; white-space:nowrap; padding:1px 9px; border-radius:999px; font-size:12.5px; font-weight:600;
  border:1px solid var(--rule); color:var(--ink2); background:var(--surface); }
.pill.prog { color:var(--action); border-color:var(--action); } .pill.block { color:var(--danger); border-color:var(--danger); }
.pill.review { color:var(--ambertext); border-color:var(--amber); background:var(--ambertint); }
.pill.done { color:var(--done); border-color:var(--done); background:var(--donetint); }
.now { display:grid; grid-template-columns:repeat(4, 1fr); gap:18px; }
.now div { background:var(--surface); border:1px solid var(--rule); border-radius:10px; padding:14px 18px; }
.now h3 { margin:0 0 6px; font-size:14px; color:var(--ink2); font-weight:600; }
.now p { margin:0; font-size:15px; }
.tracks { display:grid; gap:18px; }
.track { background:var(--surface); border:1px solid var(--rule); border-radius:12px; padding:18px 20px 8px; }
.track h3 { margin:0; font-size:17px; display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
.tid { display:inline-grid; place-items:center; padding:0 8px; height:24px; font-size:12px; color:var(--ink3);
  border-radius:7px; background:var(--canvas); font-weight:700; }
.tnote { margin:4px 0 10px; color:var(--ink3); font-size:14px; }
.tablewrap { overflow-x:auto; }
table { width:100%; border-collapse:collapse; font-size:14px; }
th, td { text-align:left; padding:10px 8px; border-top:1px solid var(--rule); vertical-align:top; }
thead th { border-top:0; color:var(--ink3); font-weight:500; font-size:13px; }
tbody th { font-weight:600; color:var(--ink3); white-space:nowrap; font-size:13px; }
.ref { display:block; font-weight:500; }
.track h3 .ref { display:inline; font-size:13px; }
.det { display:block; color:var(--ink2); font-size:13.5px; }
.xlink, .mr { display:block; font-size:13px; }
td.gates { white-space:nowrap; } td.gates .g { margin-right:4px; }
ol.timeline { list-style:none; margin:0; padding:0; border-left:2px solid var(--rule); }
ol.timeline li { position:relative; padding:0 0 16px 22px; }
ol.timeline li::before { content:""; position:absolute; left:-7px; top:6px; width:12px; height:12px; border-radius:50%;
  background:var(--surface); border:2px solid var(--action); }
ol.timeline time { font-weight:600; font-size:14px; }
ol.timeline p { margin:2px 0 0; color:var(--ink2); max-width:90ch; }
@media (max-width: 1000px) { .now { grid-template-columns:1fr 1fr; } }
@media (max-width: 860px) { .legend, .now { grid-template-columns:1fr; } header.top { grid-template-columns:1fr; }
  .state { grid-column:1; grid-row:auto; text-align:left; } .wrap { padding:24px 16px 48px; } }
"""
