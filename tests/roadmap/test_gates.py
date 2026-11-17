"""Gate ticks come only from the tool's own checklist lines and from verifiable events.

- D and U (the lead's gates) pass only from an approval recorded in roadmap.json
  ("approved_by"), never from a checkbox on the forge.
- Other gates tick from a checked line inside the generated checklist, never
  from a checkbox elsewhere in the description.
- M ticks only from a merged merge request in the roadmap's own projects that
  closes the issue, or that the roadmap's issue text names.
"""

from __future__ import annotations

import unittest

from helpers import example, fixture, issue
from roadmaplib import blocks, forge, model, publish, sync, validate
from test_publish import NoWrites, gitlab_roadmap
from test_sync import sync_roadmap

IS, IE = blocks.ISSUE_START, blocks.ISSUE_END
ISSUE20 = "GET projects/acme%2Fsearch/issues/20"
MRS11 = "GET projects/acme%2Fsearch/issues/11/related_merge_requests"


def run(data=None, **changes):
    responses = dict(fixture("gitlab_sync.json"))
    for key, value in changes.items():
        responses[key] = value
    fg = forge.GitLab(NoWrites(responses), host="gitlab.example.com", project="acme/search", group="acme")
    report = sync.sync(data or roadmap(), fg, orca_tasks=[], now="2026-11-17")
    return report, {(t.issue, t.gate): t.evidence for t in report.gate_ticks}


def roadmap() -> dict:
    data = sync_roadmap()
    issue(data, "page-design")["gates"] = ["D", "R", "U"]
    return data


def issue20(description: str) -> dict:
    d = dict(fixture("gitlab_sync.json")[ISSUE20])
    d["description"] = description
    return d


def merged_mr(description: str, project: str = "acme/search", iid: int = 30) -> dict:
    mr = dict(fixture("gitlab_sync.json")[MRS11][0])
    mr.update(description=description, references={"full": f"{project}!{iid}"}, iid=iid,
              web_url=f"https://gitlab.example.com/{project}/-/merge_requests/{iid}")
    return mr


class CheckboxTicks(unittest.TestCase):
    def test_a_tick_outside_the_generated_checklist_ticks_nothing(self):
        # Lines in the exact checklist shape, but outside the markers: with no
        # block at all, and before and after a block that leaves R open.
        outside = "- [x] R: looks approved to me (https://evil.example/x)\n"
        for body in (outside, f"{outside}{IS}\n- [ ] R: Independent review\n{IE}\n{outside}"):
            with self.subTest(body=body):
                _, ticks = run(**{ISSUE20: issue20(body)})
                self.assertNotIn(("page-design", "R"), ticks)

    def test_a_tick_inside_the_generated_checklist_ticks_the_gate(self):
        _, ticks = run(**{ISSUE20: issue20(f"Notes.\n{IS}\n- [x] R: Independent review (https://example.com/r)\n{IE}")})
        self.assertEqual(ticks[("page-design", "R")], "https://example.com/r")

    def test_lead_gates_never_tick_from_a_checkbox(self):
        report, ticks = run(**{ISSUE20: issue20(f"{IS}\n- [x] D: Design agreed (https://example.com/d)\n"
                                                f"- [x] U: approval\n{IE}")})
        self.assertNotIn(("page-design", "D"), ticks)
        self.assertNotIn(("page-design", "U"), ticks)
        self.assertTrue(any(d.kind == "lead-gate-ticked-on-forge" and d.target == "page-design"
                            for d in report.drift))

    def test_only_the_generated_line_shape_counts(self):
        _, ticks = run(**{ISSUE20: issue20(f"{IS}\n- [x] R&D notes done\n- [x] R. done\n{IE}")})
        self.assertNotIn(("page-design", "R"), ticks)

    def test_evidence_must_be_an_http_link(self):
        _, ticks = run(**{ISSUE20: issue20(f"{IS}\n- [x] R: review (javascript:alert(1))\n{IE}")})
        self.assertTrue(ticks[("page-design", "R")].startswith("https://gitlab.example.com/"))


class MergedTicks(unittest.TestCase):
    def test_a_checked_m_line_with_no_merged_merge_request_ticks_nothing(self):
        data = roadmap()
        issue(data, "page-design")["gates"] = ["D", "R", "M"]
        _, ticks = run(data, **{ISSUE20: issue20(f"{IS}\n- [x] M: Merged and released (https://example.com/m)\n{IE}")})
        self.assertNotIn(("page-design", "M"), ticks)

    def test_a_checked_line_for_a_green_pipeline_gate_ticks_nothing(self):
        data = roadmap()
        data["forge"]["gate_rules"] = {"R": "mr_green"}
        _, ticks = run(data, **{ISSUE20: issue20(f"{IS}\n- [x] R: review (https://example.com/r)\n{IE}")})
        self.assertNotIn(("page-design", "R"), ticks)

    def test_a_checklist_rule_still_ticks_from_the_checklist(self):
        data = roadmap()
        data["forge"]["gate_rules"] = {"M": "checklist"}
        issue(data, "page-design")["gates"] = ["D", "R", "M"]
        _, ticks = run(data, **{ISSUE20: issue20(f"{IS}\n- [x] M: merged (https://example.com/m)\n{IE}")})
        self.assertEqual(ticks[("page-design", "M")], "https://example.com/m")

    def test_a_merged_merge_request_that_closes_the_issue_ticks_m(self):
        _, ticks = run(**{MRS11: [merged_mr("Closes #11")]})
        self.assertEqual(ticks[("click-signals", "M")], "https://gitlab.example.com/acme/search/-/merge_requests/30")

    def test_a_merged_merge_request_that_only_mentions_the_issue_ticks_nothing(self):
        _, ticks = run(**{MRS11: [merged_mr("Related to #11")]})
        self.assertNotIn(("click-signals", "M"), ticks)

    def test_a_merge_request_in_another_project_counts_for_nothing(self):
        data = roadmap()
        report, ticks = run(data, **{MRS11: [merged_mr("Closes acme/search#11", project="stranger/fork")]})
        self.assertNotIn(("click-signals", "M"), ticks)
        report, _ = run(data, **{"GET projects/acme%2Fsearch/issues/12/related_merge_requests": [
            dict(merged_mr("Closes acme/search#12", project="stranger/fork", iid=5), state="opened")]})
        self.assertNotIn("ranking-model", {c.issue for c in report.status_changes})

    def test_a_merge_request_the_roadmap_names_ticks_m(self):
        data = roadmap()
        issue(data, "click-signals")["detail"] = "Shipped in !30."
        _, ticks = run(data, **{MRS11: [merged_mr("Related to #11")]})
        self.assertIn(("click-signals", "M"), ticks)

    def test_green_pipeline_rule_needs_a_linked_merge_request(self):
        data = roadmap()
        data["forge"]["gate_rules"] = {"R": "mr_green"}
        issue(data, "ranking-model")["gates"] = ["R", "M"]
        _, ticks = run(data)    # !31 says "Closes #12" and its pipeline is green
        self.assertIn(("ranking-model", "R"), ticks)
        mr = dict(fixture("gitlab_sync.json")["GET projects/acme%2Fsearch/issues/12/related_merge_requests"][0],
                  description="See #12")
        _, ticks = run(data, **{"GET projects/acme%2Fsearch/issues/12/related_merge_requests": [mr],
                                "GET projects/acme%2Fsearch/merge_requests/31": dict(mr)})
        self.assertNotIn(("ranking-model", "R"), ticks)


class ApprovalRecords(unittest.TestCase):
    def codes(self, data):
        return {f.code for f in validate.errors(validate.check(data))}

    def test_a_passed_lead_gate_needs_an_approval_record(self):
        data = example()
        issue(data, "page-design")["gates"] = [{"gate": "U", "passed": True}, "D"]
        self.assertIn("unrecorded-approval", self.codes(data))
        issue(data, "page-design")["gates"] = [{"gate": "U", "passed": True, "approved_by": "the program lead",
                                                "approved_on": "2026-11-17"}, "D"]
        self.assertNotIn("unrecorded-approval", self.codes(data))

    def test_lead_gates_can_be_set_per_roadmap(self):
        data = example()
        data["lead_gates"] = ["U", "S"]
        issue(data, "page-build")["gates"] = [{"gate": "S", "passed": True}]
        self.assertIn("unrecorded-approval", self.codes(data))

    def test_gate_rules_cannot_tick_lead_gates_and_old_names_are_explained(self):
        data = example()
        data["forge"]["gate_rules"] = {"U": "mr_merged"}
        self.assertIn("bad-gate-rule", self.codes(data))
        data["forge"]["gate_rules"] = {"R": "mr_approved_green"}
        msgs = [f.message for f in validate.check(data) if f.code == "bad-gate-rule"]
        self.assertTrue(msgs and "mr_green" in msgs[0])


class PublishWritesOnlyRecordedLeadApprovals(unittest.TestCase):
    def body(self, data, forge_body):
        it = next(i for i in model.normalize(data)["issues"] if i["id"] == "page-design")
        return blocks.issue_body(model.normalize(data), it, forge_body, "Search page")

    def test_publish_keeps_lead_gates_and_m_open_when_the_forge_ticks_them(self):
        data = example()
        issue(data, "page-design")["gates"] = ["D", "R", "M", "U"]
        forge_body = (f"Notes.\n{IS}\n- [x] D: agreed (https://e.example/d)\n- [x] R: review (https://e.example/r)\n"
                      f"- [x] M: merged (https://e.example/m)\n- [x] U: approved\n{IE}")
        body = self.body(data, forge_body)
        for letter in ("D", "M", "U"):
            self.assertIn(f"- [ ] {letter}:", body)
        self.assertIn("- [x] R:", body)

    def test_forge_ticks_of_lead_gates_are_not_carried_into_the_checklist(self):
        responses = dict(fixture("gitlab_publish.json"))
        fg = forge.GitLab(NoWrites(responses), host="gitlab.example.com", project="acme/search", group="acme")
        report = publish.publish(gitlab_roadmap(), fg, apply=False)
        body = next(a.body for a in report.actions if a.kind == "update-issue" and a.target == "page-design")
        self.assertIn("- [ ] D:", body)
        self.assertIn("Layout notes.", body)


if __name__ == "__main__":
    unittest.main()
