"""Generated sections: text outside one well-formed marker pair is never changed.

When the markers are missing on one side, duplicated, out of order or edited by
hand, nothing is written and the description is reported for a hand fix.
"""

from __future__ import annotations

import unittest

from helpers import example, fixture, issue
from roadmaplib import blocks, forge, model, publish, sync
from test_publish import NoWrites, Recorder, gitlab_roadmap
from test_sync import sync_roadmap

S, E = blocks.EPIC_START, blocks.EPIC_END
IS, IE = blocks.ISSUE_START, blocks.ISSUE_END


def write(body: str) -> str:
    return blocks.epic_body(example(), "search-page", body)


class WellFormedPair(unittest.TestCase):
    def test_text_outside_the_pair_is_kept_byte_for_byte(self):
        body = f"Intro.\n\n  {S}\nstale\n{E}\n\nOutro, with trailing space.  \n"
        new = write(body)
        self.assertTrue(new.startswith("Intro.\n\n"))
        self.assertTrue(new.endswith(f"{E}\n\nOutro, with trailing space.  \n"))
        self.assertNotIn("stale", new)
        self.assertEqual(write(new), new)

    def test_appending_keeps_the_hand_written_text_exactly(self):
        body = "Hand text.  \n\n\n"
        new = write(body)
        self.assertTrue(new.startswith(body))
        self.assertEqual(write(new), new)

    def test_empty_description_gets_just_the_block(self):
        self.assertTrue(write("").startswith(S))

    def test_markers_quoted_in_prose_are_not_markers(self):
        body = f"Write between `{S}` and `{E}` only.\n"
        new = write(body)
        self.assertTrue(new.startswith(body))
        again = write(new)
        self.assertEqual(again, new)
        self.assertIn(f"`{S}` and `{E}` only.", again)


class BrokenMarkersAreRefused(unittest.TestCase):
    def assert_refused(self, body):
        with self.assertRaises(blocks.MarkerError) as ctx:
            write(body)
        self.assertIn("by hand", str(ctx.exception))
        return str(ctx.exception)

    def test_missing_end_marker(self):
        self.assert_refused(f"Intro.\n{S}\nold generated\nHAND TEXT THE USER WROTE\n")

    def test_second_write_after_a_missing_end_marker_keeps_the_hand_text(self):
        # The state an earlier version left after its first write: the orphan
        # start marker, the hand text, then an appended block. Writing again used
        # to delete everything from the orphan marker to the new end marker.
        body = f"Intro.\n{S}\nold generated\nHAND TEXT THE USER WROTE\n\n{S}\nnew\n{E}"
        self.assert_refused(body)

    def test_end_marker_before_start_marker(self):
        msg = self.assert_refused(f"Intro.\n{E}\nMIDDLE\n{S}\nTRAILING\n")
        self.assertIn("before", msg)

    def test_second_write_after_reordered_markers_keeps_the_trailing_text(self):
        self.assert_refused(f"Intro.\n{E}\nMIDDLE\n{S}\nTRAILING\n\n{S}\nnew\n{E}")

    def test_missing_start_marker(self):
        self.assert_refused(f"Intro.\nold generated\n{E}\nOutro.\n")

    def test_two_complete_blocks(self):
        self.assert_refused(f"{S}\none\n{E}\nMiddle.\n{S}\ntwo\n{E}\n")

    def test_hand_edited_markers(self):
        for bad in ("<!-- roadmap:epic:end-->", "<!--ROADMAP:EPIC:END-->", "<!-- roadmap:epic:end",
                    f"text before {E}"):
            with self.subTest(bad=bad):
                self.assert_refused(f"Intro.\n{S}\ngenerated\n{bad}\nOutro.\n")

    def test_issue_sections_follow_the_same_rule(self):
        data = model.normalize(example())
        it = issue(data, "page-design")
        with self.assertRaises(blocks.MarkerError):
            blocks.issue_body(data, it, f"Notes.\n{IS}\n- [ ] D\nHAND\n", "New search page")


class PublishReportsBrokenMarkers(unittest.TestCase):
    def test_issue_with_broken_markers_is_reported_and_not_written(self):
        responses = dict(fixture("gitlab_publish.json"))
        broken = dict(responses["GET projects/acme%2Fsearch/issues/12"])
        broken["description"] = f"Blend.\n{IS}\nold\nHAND TEXT\n"
        responses["GET projects/acme%2Fsearch/issues/12"] = broken
        rec = Recorder(responses)
        fg = forge.GitLab(rec, host="gitlab.example.com", project="acme/search", group="acme")
        report = publish.publish(gitlab_roadmap(), fg, apply=False)
        fixes = [a for a in report.actions if a.kind == "hand-fix"]
        self.assertEqual([a.target for a in fixes], ["ranking-model"])
        self.assertNotIn("ranking-model", {a.target for a in report.actions if a.kind == "update-issue"})
        self.assertIn("Needs a hand fix", report.text())

    def test_apply_does_not_write_a_description_with_broken_markers(self):
        data = gitlab_roadmap()
        data["epics"] = data["epics"][:1]
        data["issues"] = [issue(data, "click-signals")]
        responses = dict(fixture("gitlab_publish.json"))
        epic = dict(responses["GET groups/acme/epics/10"])
        epic["description"] = f"Ranking work.\n{S}\nold\nHAND TEXT\n"
        responses["GET groups/acme/epics/10"] = epic
        rec = Recorder(responses)
        fg = forge.GitLab(rec, host="gitlab.example.com", project="acme/search", group="acme")
        publish.publish(data, fg, apply=True)
        self.assertNotIn("groups/acme/epics/10", [p for _, p, _ in rec.calls])


class SyncReportsBrokenMarkers(unittest.TestCase):
    def test_update_epics_skips_a_broken_epic_and_says_so(self):
        responses = dict(fixture("gitlab_sync.json"))
        responses["GET groups/acme/epics/10"] = {"id": 510, "iid": 10, "title": "Better ranking",
                                                 "description": f"Hand.\n{E}\nMIDDLE\n{S}\nTRAILING\n",
                                                 "web_url": "https://gitlab.example.com/groups/acme/-/epics/10"}
        rec = Recorder(responses)
        fg = forge.GitLab(rec, host="h", project="acme/search", group="acme")
        report = sync.sync(sync_roadmap(), fg, orca_tasks=[], now="2026-11-17", update_epics=True)
        self.assertEqual(rec.calls, [])
        self.assertTrue(any(d.kind == "marker-problem" and d.target == "acme&10" for d in report.drift))

    def test_read_only_sync_reports_the_broken_epic(self):
        responses = dict(fixture("gitlab_sync.json"))
        responses["GET groups/acme/epics/10"] = {"id": 510, "iid": 10, "title": "Better ranking",
                                                 "description": f"Hand.\n{S}\nold\n", "web_url": "u"}
        fg = forge.GitLab(NoWrites(responses), host="h", project="acme/search", group="acme")
        report = sync.sync(sync_roadmap(), fg, orca_tasks=[], now="2026-11-17")
        self.assertTrue(any(d.kind == "marker-problem" for d in report.drift))


if __name__ == "__main__":
    unittest.main()
