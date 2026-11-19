"""Standalone HTML timeline shared by the standard and custom renderers."""

from __future__ import annotations

import re
from base64 import b64encode
from html import escape
from pathlib import Path
from xml.etree import ElementTree

from .model import timeline_prefix

_LABELS = {"claude": "Claude", "codex": "Codex"}
_OUTLINES = {
    "claude": '<circle cx="8" cy="8" r="5.5"/>',
    "codex": '<rect x="2.5" y="2.5" width="11" height="11" rx="1"/>',
}
_SVG_LIMIT = 4 * 1024
_SVG_TAG = "{http://www.w3.org/2000/svg}svg"
_XML_ENCODING = re.compile(
    r"""^\ufeff?<\?xml\s+[^?]*\bencoding\s*=\s*["']([^"']+)["']"""
)


def _mark(path: Path) -> str:
    """Return an optional local SVG in the browser's isolated image context."""
    try:
        if not path.is_file():
            return ""
        with path.open("rb") as asset:
            raw = asset.read(_SVG_LIMIT + 1)
        # Byte parsing can auto-detect UTF-16 despite a successful UTF-8 decode.
        if len(raw) > _SVG_LIMIT or b"\x00" in raw:
            return ""
        svg = raw.decode("utf-8")
        declaration = _XML_ENCODING.match(svg)
        if declaration and declaration[1].lower() not in ("utf-8", "utf8"):
            return ""
        if "<!DOCTYPE" in svg or ElementTree.fromstring(raw).tag != _SVG_TAG:
            return ""
    except (OSError, UnicodeError, LookupError, ElementTree.ParseError):
        return ""
    encoded = b64encode(raw).decode("ascii")
    return (
        '<img class="timeline-mark" alt="" aria-hidden="true" '
        f'src="data:image/svg+xml;base64,{encoded}">'
    )


def _default_mark(author: str) -> str:
    return (
        '<svg class="timeline-mark" aria-hidden="true" focusable="false" '
        'viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">'
        f"{_OUTLINES[author]}</svg>"
    )


def _summary(event: dict) -> str:
    title = event.get("title", "").strip()
    if title:
        return title
    text = event["text"]
    text = " ".join(text[len(timeline_prefix(text)) :].split())
    if len(text) <= 96:
        return text or "Timeline entry"
    short = text[:93]
    boundary = short.rfind(" ")
    if boundary >= 70:
        short = short[:boundary]
    return short + "..."


def _event_start(event: dict, marks: dict[str, str]) -> str:
    author = event.get("author")
    label = _LABELS.get(author, "Unattributed")
    mark = marks.get(author, "")
    return (
        "<li><details><summary>"
        f'<span class="timeline-title">{escape(_summary(event))}</span>'
        '<span class="timeline-meta">'
        f"<time>{escape(event['date'])}</time>"
        f'<span class="timeline-author">{mark}{label}</span></span></summary>'
        f'<div class="timeline-text">{escape(event["text"])}</div>'
    )


def render_timeline(events: list, *, author_icon_dir: Path | None = None) -> str:
    """Render validated, normalized events with newest roots and recorded child order."""
    marks = {}
    for author in _LABELS:
        overlay = _mark(author_icon_dir / f"{author}.svg") if author_icon_dir else ""
        marks[author] = overlay or _default_mark(author)
    parts = ['<ol class="timeline" role="list">']
    # Close each group after visiting its children without using the Python stack.
    close_group = object()
    pending = list(events)
    while pending:
        entry = pending.pop()
        if entry is close_group:
            parts.append("</ol></details></li>")
            continue
        parts.append(_event_start(entry, marks))
        children = entry.get("children")
        if children:
            parts.append('<ol class="timeline-children" role="list">')
            pending.append(close_group)
            pending.extend(reversed(children))
        else:
            parts.append("</details></li>")
    parts.append("</ol>")
    return "".join(parts)


TIMELINE_CSS = """
.timeline, .timeline-children { list-style:none; margin:0; padding:0; }
.timeline { max-inline-size:76ch; }
.timeline li { overflow-wrap:anywhere; }
.timeline summary { cursor:pointer; padding:10px 8px; border-radius:4px; }
.timeline summary:focus-visible { outline:2px solid var(--action); outline-offset:1px; }
.timeline summary::marker { color:var(--action); }
.timeline > li { border-block-start:1px solid var(--rule); }
.timeline-title { font-weight:600; }
.timeline-meta { display:flex; flex-wrap:wrap; gap:2px 12px; margin-inline-start:1.05rem;
  align-items:baseline; color:var(--ink3); font-size:0.84rem; }
.timeline-author { display:inline-flex; align-items:center; gap:4px; }
.timeline-mark { block-size:1em; inline-size:1em; }
.timeline-text { max-inline-size:68ch; margin:0 8px 12px 1.55rem; color:var(--ink2);
  white-space:pre-wrap; }
.timeline-children { margin:0 0 12px 1.55rem; padding-inline-start:8px;
  border-inline-start:1px solid var(--rule); }
.timeline-children .timeline-children { margin-inline-start:8px; padding-inline-start:5px; }
.timeline-children .timeline-children .timeline-children {
  margin-inline-start:0; padding-inline-start:0; border-inline-start:0; }
@media (max-width: 420px) {
  .timeline summary { padding-inline:4px; }
  .timeline-meta { margin-inline-start:0.9rem; }
  .timeline-text, .timeline-children { margin-inline-start:0.9rem; }
}
"""
