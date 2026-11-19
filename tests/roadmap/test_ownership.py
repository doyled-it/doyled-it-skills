"""Optional roadmap ownership and coordinator hierarchy."""

from __future__ import annotations

import unittest
from copy import deepcopy

from helpers import issue
from roadmaplib import model, render, validate
from test_render import parse
from test_sync import sync_roadmap


def owned_roadmap():
    data = sync_roadmap()
    data["orca"] = {"run": "run_root"}
    data["orchestration"] = {
        "coordinators": {
            "root": {"name": "Program coordination", "role": "meta", "run": "run_root"},
            "storage": {
                "name": "Storage <team>",
                "scope": "Data <imports>",
                "role": "area",
                "run": "run_storage",
                "parent": "root",
                "metadata": {"channel": "team"},
            },
            "search": {
                "name": "Search team",
                "scope": "Queries",
                "role": "area",
                "run": "run_search",
                "parent": "root",
            },
            "release": {
                "name": "Release team",
                "scope": "Deployment",
                "role": "area",
                "run": "run_release",
                "parent": "root",
            },
        },
        "other": "keep",
    }
    data["epics"][0]["orchestrators"] = ["storage", "search"]
    issue(data, "ranking-model")["orchestrators"] = ["storage", "search"]
    issue(data, "page-build")["orchestrators"] = ["search"]
    issue(data, "page-build")["depends_on"] = []
    return data


class Ownership(unittest.TestCase):
    def test_configured_runs_with_no_snapshot_display_unknown_activity(self):
        for data in (
            {**sync_roadmap(), "orca": {"run": "run_legacy"}},
            {**owned_roadmap(), "orca": {}},
        ):
            with self.subTest(data=data.get("orca")):
                self.assertFalse(validate.errors(validate.check(data)))
                page = render.render_page(data)
                self.assertIn(
                    {"id": "orca-observation", "aria-labelledby": "orca-observation-title"},
                    parse(page).having("section"),
                )
                section = page.split('id="orca-observation"', 1)[1].split("</section>", 1)[0]
                self.assertIn("Unknown", section)
                self.assertNotIn("0 confirmed working", section)
                self.assertNotIn("orca_observation", data)
        self.assertNotIn('id="orca-observation"', render.render_page(sync_roadmap()))

    def test_stored_worker_activity_has_accessible_labels_and_escaped_provenance(self):
        data = owned_roadmap()
        data["orca_observation"] = {
            "source": "recorded",
            "observed_at": None,
            "coverage_complete": False,
            "workers": [
                {
                    "run": "run_<img>",
                    "task": "task_<script>",
                    "dispatch": "dispatch_<b>",
                    "activity": "working",
                    "observed_at": "2026-11-19T19:15:41Z",
                    "owners": {"storage": "root", "<area>": "<parent>"},
                }
            ],
        }
        self.assertFalse(validate.errors(validate.check(data)))
        page = render.render_page(data)
        self.assertIn(
            {"id": "orca-observation", "aria-labelledby": "orca-observation-title"},
            parse(page).having("section"),
        )
        observation = page.split('id="orca-observation"', 1)[1].split("</section>", 1)[0]
        for value in ("&lt;img&gt;", "&lt;script&gt;", "&lt;b&gt;", "&lt;area&gt;", "&lt;parent&gt;"):
            self.assertIn(value, observation)
        self.assertIn("1 confirmed working", observation)
        self.assertIn("Unknown", observation)
        self.assertIn('datetime="2026-11-19T19:15:41Z"', observation)
        self.assertIn("In progress or in review", page)

    def test_invalid_stored_worker_activity_cannot_be_rendered_as_working(self):
        data = owned_roadmap()
        data["orca_observation"] = {
            "source": "recorded",
            "observed_at": None,
            "coverage_complete": True,
            "workers": [
                {
                    "run": "run_storage",
                    "task": "task_work",
                    "dispatch": "dispatch_work",
                    "activity": "working",
                    "observed_at": "2026-11-19",
                    "owners": {},
                }
            ],
        }
        self.assertIn(
            "orca_observation.workers[0].observed_at",
            {finding.where for finding in validate.errors(validate.check(data))},
        )
        with self.assertRaises(render.RenderError):
            render.render_page(data)

    def test_ownerless_and_legacy_coordinators_are_supported(self):
        data = sync_roadmap()
        self.assertFalse(validate.errors(validate.check(data)))
        self.assertNotIn('id="ownership"', render.render_page(data))
        data["orchestration"] = {"coordinators": {"legacy": {"name": "Legacy owner", "run": "run_legacy"}}}
        issue(data, "ranking-model")["orchestrators"] = ["legacy"]
        self.assertFalse(validate.errors(validate.check(data)))
        self.assertIn("Legacy owner", render.render_page(data))

    def test_shared_ownership_is_rendered_with_scope_parent_readiness_and_open_gates(self):
        data = owned_roadmap()
        original = deepcopy(data)
        self.assertFalse(validate.errors(validate.check(data)))
        self.assertEqual(model.normalize(data)["orchestration"], data["orchestration"])
        self.assertEqual(model.normalize(data)["epics"][0]["orchestrators"], ["storage", "search"])
        self.assertEqual(issue(model.normalize(data), "ranking-model")["orchestrators"], ["storage", "search"])
        page = render.render_page(data)
        doc = parse(page)
        self.assertIn({"id": "ownership", "aria-labelledby": "ownership-title"}, doc.having("section"))
        self.assertIn("Storage &lt;team&gt;", page)
        self.assertIn("Data &lt;imports&gt;", page)
        self.assertNotIn("<team>", page)
        self.assertIn("Reports to Program coordination", page)
        self.assertIn("Ready to start", page.split('id="ownership"', 1)[1])
        self.assertIn("page-build", page.split('id="ownership"', 1)[1].split("</section>", 1)[0])
        self.assertIn("Open gates", page.split('id="ownership"', 1)[1].split("</section>", 1)[0])
        self.assertEqual(page.count("Owners: Storage &lt;team&gt;, Search team"), 2)
        self.assertEqual(data, original)

    def test_malformed_coordinator_metadata_and_ownership_references_are_errors(self):
        for field, value in (
            ("role", "manager"),
            ("role", []),
            ("run", 1),
            ("parent", []),
            ("name", None),
            ("scope", {"path": "src"}),
        ):
            with self.subTest(field=field, value=value):
                data = owned_roadmap()
                data["orchestration"]["coordinators"]["storage"][field] = value
                locations = {f.where for f in validate.errors(validate.check(data))}
                self.assertIn(f"orchestration.coordinators.storage.{field}", locations)
        for value in ("storage", [{}], [" "], ["missing"]):
            for kind, index in (("epics", 0), ("issues", 1)):
                with self.subTest(value=value, kind=kind):
                    data = owned_roadmap()
                    item = data[kind][index]
                    item["orchestrators"] = value
                    locations = {f.where for f in validate.errors(validate.check(data))}
                    self.assertTrue(
                        any(where.startswith(f"{kind}[{item['id']}].orchestrators") for where in locations), locations
                    )

    def test_parent_links_reject_missing_coordinators_and_cycles(self):
        data = owned_roadmap()
        root = data["orchestration"]["coordinators"]["root"]
        for parent, expected in (("missing", "missing"), ("root", "cycle"), ("search", "cycle")):
            with self.subTest(parent=parent):
                root["parent"] = parent
                findings = validate.errors(validate.check(data))
                self.assertTrue(
                    any(expected in str(f) and "orchestration.coordinators" in f.where for f in findings), findings
                )


if __name__ == "__main__":
    unittest.main()
