"""Timeline storage, validation and standalone HTML."""

from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import CLI, FIXTURES, SCHEMA, example, fixture, issue
from roadmaplib import forge, model, publish, render, validate
from test_publish import NoWrites, gitlab_roadmap
from test_render import parse
from test_sync import sync_roadmap

SVG_ICON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><path d="M0 0h8v8z"/></svg>'


def event(text, date="Nov 18", **fields):
    return {"date": date, "text": text, **fields}


def deep_append(data):
    nested = event("(Codex) Recorded detail", extra={"unchanged": [1, "é"]})
    for _ in range(400):
        nested = event("Grouped result", children=[nested])
    data["timeline"].append(nested)
    data["extra"] = {"record": ["keep", {"checked": True}]}
    return data


class TimelineConsumers(unittest.TestCase):
    def test_recorded_sync_write_round_trips_deep_unrelated_history(self):
        data = deep_append(sync_roadmap())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            model.save(path, data)
            result = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "sync",
                    str(path),
                    "--write",
                    "--no-orca",
                    "--recorded",
                    str(FIXTURES / "gitlab_sync.json"),
                    "--now",
                    "2026-11-17",
                ],
                capture_output=True,
                check=False,
                text=True,
            )
            self.assertEqual(
                result.returncode, 0, result.stdout + result.stderr[-2600:]
            )
            updated = model.load(path)
        self.assertEqual(issue(updated, "ranking-model")["status"], "in_review")
        self.assertTrue(json.dumps(updated["timeline"]) == json.dumps(data["timeline"]))
        self.assertEqual(updated["extra"], data["extra"])

    def test_recorded_publish_dry_run_round_trips_raw_deep_history(self):
        data = deep_append(gitlab_roadmap())
        fg = forge.GitLab(
            NoWrites(fixture("gitlab_publish.json")),
            host="gitlab.example.com",
            project="acme/search",
            group="acme",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            model.save(path, data)
            before = path.read_text()
            raw = model.load(path)
            try:
                report = publish.publish(raw, fg)
            except RecursionError:
                self.fail("publish exhausted the stack when copying a valid timeline")
            self.assertEqual(path.read_text(), before)
            self.assertTrue(json.dumps(raw) == json.dumps(data))
            model.save(path, report.roadmap)
            proposed = model.load(path)
        untouched = {
            key: value for key, value in data.items() if key not in ("epics", "issues")
        }
        self.assertTrue(
            json.dumps({key: proposed[key] for key in untouched})
            == json.dumps(untouched)
        )
        self.assertIn("Dry run", report.text())
        self.assertTrue(any(action.kind == "create-issue" for action in report.actions))


class TimelineModel(unittest.TestCase):
    def test_normalization_copies_history_and_adds_only_supported_legacy_attribution(
        self,
    ):
        original = example()
        original["timeline"] = [
            event("Codex handed off to Claude"),
            event(" (Claude) This prefix is not at the beginning"),
            event("(codex) This prefix is not literal"),
            event(
                "(Claude) Keep this as recorded\nSecond line",
                id="source-history",
                provenance={"record": ["review", {"number": 42}]},
                children=[
                    event("(Claude) Preserve the explicit author", author="codex"),
                    event("(Codex) Explicit unknown author", author="reviewer"),
                    event("Mentioned (Claude) in the middle"),
                    event(
                        "Recorded group", children=[event("(Codex) Recorded detail")]
                    ),
                ],
                extra={"pending": [True]},
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            model.save(path, original)
            raw = model.load(path)
            normalized = model.normalize(raw)

        self.assertEqual(raw, original)
        original_entry = original["timeline"][-1]
        entry = normalized["timeline"][-1]
        self.assertEqual(normalized["timeline"][:3], original["timeline"][:3])
        self.assertEqual(entry.get("author"), "claude")
        self.assertEqual(entry["text"], original_entry["text"])
        self.assertEqual(entry["id"], "source-history")
        self.assertEqual(entry["children"][:3], original_entry["children"][:3])
        self.assertEqual(entry["children"][3]["children"][0]["author"], "codex")
        self.assertEqual(entry["extra"], original_entry["extra"])
        self.assertEqual(entry["provenance"], original_entry["provenance"])
        entry["provenance"]["record"][1]["number"] = 99
        entry["extra"]["pending"].append(False)
        self.assertEqual(raw, original)

    def test_schema_references_same_event_shape_at_each_depth(self):
        schema = json.loads(SCHEMA.read_text())
        event_ref = schema["properties"]["timeline"]["items"].get("$ref")
        self.assertIsInstance(event_ref, str)
        event_schema = schema["$defs"][event_ref.rsplit("/", 1)[-1]]
        fields = event_schema["properties"]
        self.assertEqual(set(event_schema["required"]), {"date", "text"})
        self.assertEqual(fields["children"]["items"]["$ref"], event_ref)
        self.assertEqual(fields["children"]["type"], "array")
        self.assertEqual(fields["provenance"]["type"], "object")
        self.assertTrue(event_schema.get("additionalProperties", True))


class TimelineValidation(unittest.TestCase):
    def test_author_text_matches_schema_for_ascii_and_non_ascii(self):
        schema = json.loads(SCHEMA.read_text())
        author = schema["$defs"]["timelineEvent"]["properties"]["author"]
        for value, supported in (
            ("claude", True),
            ("codex", True),
            ("review team", True),
            ("ops-2", True),
            ("", False),
            (" ", False),
            ("Claude", False),
            ("Élodie", False),
            ("élodie", False),
            ("审阅者", False),
            ("coder😀", False),
            ("reviewer\n", False),
        ):
            with self.subTest(author=value):
                data = example()
                data["timeline"] = [event("Recorded detail", author=value)]
                runtime = not any(
                    f.where == "timeline[0].author" for f in validate.check(data)
                )
                schema_valid = bool(
                    re.search(author["pattern"], value)
                ) and not re.search(author["not"]["pattern"], value)
                self.assertEqual((schema_valid, runtime), (supported, supported))

    def test_invalid_child_shapes_report_original_paths_and_block_rendering(self):
        cases = [
            ("child", "", "bad-type"),
            ({"text": "Missing date"}, ".date", "missing-field"),
            ({"date": "Nov 17"}, ".text", "missing-field"),
            (event(None), ".text", "bad-type"),
            (event("Text", date=[]), ".date", "bad-type"),
            (event("Text", title=None), ".title", "bad-type"),
            (event("Text", author="Claude"), ".author", "bad-type"),
            (event("Text", author=None), ".author", "bad-type"),
            (event("Text", author=""), ".author", "bad-type"),
            (event("Text", id={}), ".id", "bad-type"),
            (event("Text", children=None), ".children", "bad-type"),
            (event("Text", provenance=[]), ".provenance", "bad-type"),
        ]
        for child, field, code in cases:
            with self.subTest(child=child):
                data = example()
                data["timeline"] = [event("Group", children=[child])]
                errors = validate.errors(validate.check(data))
                where = f"timeline[0].children[0]{field}"
                self.assertIn((where, code), [(f.where, f.code) for f in errors])
                with self.assertRaises(render.RenderError):
                    render.render_page(data)

    def test_nested_content_keeps_reader_text_and_control_checks(self):
        data = example()
        data["timeline"] = [
            event(
                "Group",
                children=[event("Bad\x00text", title="Retire the milestone\nToday")],
            )
        ]
        findings = {(f.where, f.code) for f in validate.check(data)}
        self.assertIn(("timeline[0].children[0].title", "glossary-milestone"), findings)
        self.assertIn(("timeline[0].children[0].title", "control-character"), findings)
        self.assertIn(("timeline[0].children[0].text", "control-character"), findings)

    def test_deep_tree_can_be_validated_and_rendered(self):
        nested = event("Deepest result", author="reviewer")
        for _ in range(400):
            nested = event("Grouped result", children=[nested])
        data = example()
        data["timeline"] = [nested]
        try:
            self.assertEqual(validate.errors(validate.check(data)), [])
            doc = parse(render.render_page(data))
        except RecursionError:
            self.fail("a deep timeline exhausted the Python stack")
        self.assertEqual(len(doc.having("details")), 401)
        self.assertIn("Deepest result", doc.text)

    def test_circular_in_memory_children_are_reported(self):
        nested = event("Circular group")
        nested["children"] = [nested]
        data = example()
        data["timeline"] = [nested]
        try:
            findings = validate.errors(validate.check(data))
        except RecursionError:
            self.fail("a circular timeline exhausted the Python stack")
        self.assertTrue(
            any(
                f.code == "bad-type" and f.where == "timeline[0].children[0]"
                for f in findings
            )
        )

    def test_decoder_nesting_refusal_is_a_read_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            path.write_text('{"timeline":[]}')
            with patch.object(model.json, "loads", side_effect=RecursionError):
                try:
                    with self.assertRaisesRegex(model.RoadmapError, "nesting"):
                        model.load(path)
                except RecursionError:
                    self.fail("the decoder's nesting refusal escaped the loader")


class TimelineRender(unittest.TestCase):
    def setUp(self):
        self.data = example()
        self.data["timeline"] = [
            event("Codex mentioned in an older note", date="Nov 19 (early)"),
            event(
                "(Codex) Raw outcome <img src=x onerror=fail>\nSecond line",
                date="Nov 2 <later update>",
                title="Grouped <work>",
                children=[
                    event("(Claude) Visible child"),
                    event("(Codex) Override author", author="reviewer"),
                    event(
                        "Raw grandchild <script>fail()</script>",
                        children=[event("(Claude) Explicit source", author="codex")],
                    ),
                ],
            ),
        ]

    def test_root_and_children_follow_source_order(self):
        page = render.render_page(self.data)
        ordered = [
            "Grouped &lt;work&gt;",
            "Visible child",
            "Override author",
            "Raw grandchild &lt;script&gt;",
            "Explicit source",
            "Codex mentioned in an older note",
        ]
        offsets = [page.find(text) for text in ordered]
        self.assertNotIn(-1, offsets)
        self.assertEqual(offsets, sorted(offsets))

    def test_native_details_show_full_escaped_record_and_author_text(self):
        page = render.render_page(self.data)
        doc = parse(page)
        self.assertEqual(len(doc.having("details")), 6)
        self.assertEqual(len(doc.having("summary")), 6)
        self.assertRegex(page, r"<details>\s*<summary>")
        self.assertNotIn("<script>", page)
        self.assertNotIn("<img src=x", page)
        self.assertIn("Nov 2 &lt;later update&gt;", page)
        self.assertIn(
            "(Codex) Raw outcome <img src=x onerror=fail>\nSecond line", doc.text
        )
        self.assertIn(">(Claude) Visible child<", page)
        self.assertIn("(Claude) Explicit source", doc.text)
        self.assertEqual(doc.text.count("Claude"), 1)
        self.assertEqual(doc.text.count("Codex"), 2)
        self.assertEqual(doc.text.count("Unattributed"), 3)
        marks = doc.having("svg", "timeline-mark")
        self.assertEqual(len(marks), 3)
        self.assertTrue(all(mark["aria-hidden"] == "true" for mark in marks))
        self.assertFalse(doc.having("script"))
        self.assertFalse(doc.having("link"))

    def test_unavailable_mark_leaves_accessible_author_label(self):
        data = example()
        data["timeline"] = [event("Reviewed repair", author="claude")]
        default = render.render_page(data)
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp)
            svg = assets / "claude.svg"
            for invalid in (
                None,
                b"<svg",
                b"<html><script>ignored</script></html>",
                b"\xff",
                b"<!DOCTYPE svg>" + SVG_ICON.encode(),
            ):
                with self.subTest(invalid=repr(invalid)[:60]):
                    if invalid is not None:
                        svg.write_bytes(invalid)
                    self.assertEqual(
                        render.render_page(data, author_icon_dir=assets), default
                    )
            svg.unlink()
            svg.mkdir()  # Unreadable as a file regardless of test privileges.
            self.assertEqual(render.render_page(data, author_icon_dir=assets), default)

    def test_incompatible_xml_encoding_uses_working_fallback(self):
        default = render.render_page(self.data)
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp)
            for encoding in ("UTF-16", "unknown-encoding", "ISO-8859-1"):
                with self.subTest(encoding=encoding):
                    (assets / "claude.svg").write_bytes(
                        f'<?xml version="1.0" encoding="{encoding}"?>{SVG_ICON}'.encode()
                    )
                    self.assertEqual(
                        render.render_page(self.data, author_icon_dir=assets), default
                    )

    def test_utf16_bytes_use_fallback_even_without_a_bom(self):
        data = example()
        data["timeline"] = [event("Reviewed repair", author="claude")]
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp)
            for encoding in ("utf-16-le", "utf-16-be"):
                for prologue in (
                    '<?xml version="1.0" encoding="UTF-16"?>',
                    "<!DOCTYPE svg>",
                ):
                    with self.subTest(encoding=encoding, prologue=prologue):
                        (assets / "claude.svg").write_bytes(
                            (prologue + SVG_ICON).encode(encoding)
                        )
                        doc = parse(render.render_page(data, author_icon_dir=assets))
                        self.assertIn("Claude", doc.text)
                        self.assertEqual(len(doc.having("svg", "timeline-mark")), 1)
                        self.assertFalse(doc.having("img", "timeline-mark"))

    def test_overlay_size_limit_keeps_marks_for_a_long_history(self):
        data = example()
        data["timeline"] = [event("Reviewed repair", author="claude")] * 100
        default = render.render_page(data)
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp)
            path = assets / "claude.svg"
            accepted = SVG_ICON.encode().ljust(4096, b" ")
            path.write_bytes(accepted)
            page = render.render_page(data, author_icon_dir=assets)
            self.assertEqual(len(parse(page).having("img", "timeline-mark")), 100)
            path.write_bytes(accepted + b" ")
            self.assertEqual(render.render_page(data, author_icon_dir=assets), default)

    def test_local_overlay_is_an_isolated_image_only_for_its_known_author(self):
        svg = f'\ufeff<?xml version="1.0" encoding="UTF-8"?>{SVG_ICON}<!-- Café -->'
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp)
            (assets / "claude.svg").write_bytes(svg.encode())
            (assets / "reviewer.svg").write_text(SVG_ICON)
            page = render.render_page(self.data, author_icon_dir=assets)
        doc = parse(page)
        self.assertEqual(doc.text.count("Claude"), 1)
        self.assertEqual(doc.text.count("Codex"), 2)
        self.assertEqual(doc.text.count("Unattributed"), 3)
        self.assertEqual(len(doc.having("svg", "timeline-mark")), 2)
        self.assertEqual(
            doc.having("img", "timeline-mark"),
            [
                {
                    "class": "timeline-mark",
                    "alt": "",
                    "aria-hidden": "true",
                    "src": "data:image/svg+xml;base64,"
                    + base64.b64encode(svg.encode()).decode(),
                }
            ],
        )
        self.assertNotIn(SVG_ICON, page)
        self.assertNotIn(str(assets), page)


class PortableTimelineCommand(unittest.TestCase):
    def test_copied_package_renders_without_svg_assets_or_remote_resources(self):
        data = example()
        data["timeline"] = [
            event("Repair verified", author="claude"),
            event("Review complete", author="codex"),
            event("Claude mentioned in a handoff"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = shutil.copytree(
                CLI.parent, root / "scripts", ignore=shutil.ignore_patterns("*.svg")
            )
            path = root / "roadmap.json"
            model.save(path, data)
            # Run the copied CLI with network access refused in this process.
            runner = (
                "import os, runpy, sys\n"
                "def offline(event, args):\n"
                "    if event.startswith('socket.'):\n"
                "        raise AssertionError(event)\n"
                "sys.addaudithook(offline)\n"
                "sys.argv.pop(0)\n"
                "sys.path.insert(0, os.path.dirname(sys.argv[0]))\n"
                "runpy.run_path(sys.argv[0], run_name='__main__')\n"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    runner,
                    str(scripts / CLI.name),
                    "render",
                    str(path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            doc = parse(path.with_suffix(".html").read_text())
        self.assertIn("Claude", doc.text)
        self.assertIn("Codex", doc.text)
        self.assertIn("Unattributed", doc.text)
        self.assertEqual(len(doc.having("svg", "timeline-mark")), 2)
        self.assertFalse(doc.having("img"))
        self.assertFalse(doc.having("script"))
        self.assertFalse(doc.having("link"))

    def test_render_and_epic_preview_keep_ownership_and_observations_with_overlays(
        self,
    ):
        data = example()
        data["timeline"] = [event("Repair verified", author="claude")]
        data["orchestration"] = {
            "coordinators": {"area": {"name": "Search team", "run": "run_search"}}
        }
        issue(data, "ranking-model")["orchestrators"] = ["area"]
        data["orca_observation"] = {
            "source": "recorded",
            "observed_at": "2026-11-19T19:15:40Z",
            "coverage_complete": True,
            "workers": [
                {
                    "run": "run_search",
                    "task": "task_ranking",
                    "dispatch": "dispatch_ranking",
                    "activity": "working",
                    "observed_at": "2026-11-19T19:15:41Z",
                    "owners": {"area": None},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "roadmap.json"
            model.save(path, data)
            (root / "claude.svg").write_text(SVG_ICON)
            for args, page in (
                (["render", str(path)], root / "roadmap.html"),
                (
                    ["epic-preview", str(path), "--epic", "ranking"],
                    root / "roadmap-epic-ranking-full.html",
                ),
            ):
                with self.subTest(command=args[0]):
                    result = subprocess.run(
                        [sys.executable, str(CLI), *args, "--author-icon-dir", tmp],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(
                        result.returncode, 0, result.stdout + result.stderr
                    )
                    doc = parse(page.read_text())
                    self.assertIn("Claude", doc.text)
                    self.assertEqual(len(doc.having("img", "timeline-mark")), 1)
                    self.assertIn("Owner: Search team", doc.text)
                    self.assertIn("1 confirmed working, 0 Unknown.", doc.text)
                    self.assertIn("task_ranking", doc.text)
                    self.assertIn("2026-11-19T19:15:41Z", doc.text)


if __name__ == "__main__":
    unittest.main()
