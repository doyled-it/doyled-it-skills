"""epic-preview: a local page showing an epic's generated section beside the full roadmap.

Nothing is written to the forge. The page renders the same Markdown that
publish or sync --update-epics would put in the epic description, with the
Mermaid flowchart drawn by mermaid.js, next to the full roadmap page.
"""

from __future__ import annotations

import html
import re

from . import blocks, model

MERMAID_JS = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"


def _anchor(m: re.Match) -> str:
    """A Markdown link as an anchor, only for http and https targets (already HTML-escaped)."""
    if model.safe_url(html.unescape(m.group(2))):
        return f'<a href="{m.group(2)}">{m.group(1)}</a>'
    return m.group(1)


def _inline(text: str) -> str:
    out = html.escape(text, quote=True)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w])_([^_]+)_(?![\w])", r"<em>\1</em>", out)
    out = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", _anchor, out)
    return out


def markdown_to_html(md: str) -> str:
    """The small Markdown subset the generated sections use."""
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    para: list[str] = []

    def flush():
        if para:
            out.append("<p>" + " ".join(_inline(p) for p in para) + "</p>")
            para.clear()

    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            flush()
            lang = line[3:].strip()
            body = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                body.append(lines[i])
                i += 1
            cls = "mermaid" if lang == "mermaid" else "code"
            out.append(f'<pre class="{cls}">' + html.escape("\n".join(body)) + "</pre>")
        elif line.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            i -= 1
            head, body_rows = rows[0], [r for r in rows[1:] if not all(set(c) <= set("-: ") for c in r)]
            out.append("<table><thead><tr>" + "".join(f'<th scope="col">{_inline(c)}</th>' for c in head)
                       + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in body_rows)
                       + "</tbody></table>")
        elif line.startswith("- "):
            flush()
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                m = re.match(r"- \[([ xX])\] (.*)", lines[i])
                if m:
                    checked = " checked" if m.group(1).lower() == "x" else ""
                    items.append(f'<li><input type="checkbox"{checked} disabled> {_inline(m.group(2))}</li>')
                else:
                    items.append(f"<li>{_inline(lines[i][2:])}</li>")
                i += 1
            i -= 1
            out.append('<ul class="tasks">' + "".join(items) + "</ul>")
        elif line.startswith("#"):
            flush()
            level = min(len(line) - len(line.lstrip("#")), 6)
            out.append(f"<h{level}>{_inline(line[level:].strip())}</h{level}>")
        elif line.startswith("<!--"):
            flush()
        elif not line.strip():
            flush()
        else:
            para.append(line)
        i += 1
    flush()
    return "\n".join(out)


def preview_page(raw: dict, epic_id: str, full_page: str, task_list: bool = False) -> str:
    data = model.normalize(raw)
    epic = next(e for e in data["epics"] if e["id"] == epic_id)
    md = blocks.epic_block(raw, epic_id, task_list=task_list)
    where = epic.get("ref") or "the new epic"
    esc = html.escape
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Epic section preview</title>
<style>
:root {{ --ink:#17243a; --ink2:#4a5a70; --canvas:#eef1f5; --surface:#fff; --rule:#d6dce4; --action:#2556a8;
  --ambertint:#fbf1dd; --ambertext:#7a5208; color-scheme:light dark; }}
@media (prefers-color-scheme: dark) {{ :root {{ --ink:#e6ebf2; --ink2:#b5c0cf; --canvas:#11161e; --surface:#18202b;
  --rule:#2c3747; --action:#7fa8f0; --ambertint:#3a2f17; --ambertext:#f0c879; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--canvas); color:var(--ink); font:400 15px/1.55 system-ui,sans-serif; }}
a {{ color:var(--action); }}
.grid {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.3fr); gap:16px; padding:16px; min-height:100vh; }}
.pane {{ background:var(--surface); border:1px solid var(--rule); border-radius:12px; padding:18px 20px; overflow:auto; }}
.banner {{ background:var(--ambertint); color:var(--ambertext); border-radius:8px; padding:8px 12px; font-weight:600; }}
h1 {{ font-size:20px; margin:0 0 8px; }} h3 {{ font-size:16px; }}
pre.mermaid {{ background:#fff; border:1px solid var(--rule); border-radius:8px; padding:12px; overflow:auto; }}
table {{ border-collapse:collapse; width:100%; font-size:14px; }}
th, td {{ border:1px solid var(--rule); padding:6px 8px; text-align:left; vertical-align:top; }}
ul.tasks {{ list-style:none; padding-left:4px; }}
iframe {{ width:100%; height:calc(100vh - 32px); border:1px solid var(--rule); border-radius:12px; background:var(--surface); }}
details pre {{ white-space:pre-wrap; font-size:12.5px; }}
@media (max-width: 900px) {{ .grid {{ grid-template-columns:1fr; }} iframe {{ height:80vh; }} }}
</style></head><body><main class="grid">
<section class="pane" aria-label="Epic description preview">
<p class="banner">Preview only. Not written to the forge. This is the generated section for {esc(where)}.</p>
<h1>Epic: {esc(epic["name"])}</h1>
{markdown_to_html(md)}
<details><summary>Markdown that would be written between the markers</summary><pre>{esc(md)}</pre></details>
</section>
<section aria-label="Full roadmap page"><iframe src="{esc(full_page)}" title="Full roadmap page"></iframe></section>
</main>
<script src="{MERMAID_JS}"></script>
<script>mermaid.initialize({{ startOnLoad: true, securityLevel: "strict", theme: "default" }});</script>
</body></html>
"""
