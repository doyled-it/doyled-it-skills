"""publish reads each epic's members, and the open epics, once per run."""

from __future__ import annotations

import unittest

from fakeforge import github
from helpers import example, fixture
from roadmaplib import forge, publish
from test_apply import fresh_forge
from test_publish import NoWrites, gitlab_roadmap


class CountingFake:
    """Wraps the fake GitHub transport and counts reads by path."""

    def __init__(self, inner):
        self.inner, self.reads = inner, []

    def get(self, path):
        self.reads.append(path)
        return self.inner.get(path)

    def get_all(self, path):
        self.reads.append(path)
        return self.inner.get_all(path)

    def send(self, *args, **kwargs):
        return self.inner.send(*args, **kwargs)


class GitHubMembers(unittest.TestCase):
    def test_each_epics_sub_issues_are_read_once_however_many_issues_it_has(self):
        fake = CountingFake(fresh_forge())
        fg = forge.GitHub(fake, host="github.com", project="example-org/search-service")
        publish.publish(example(), fg, apply=False)
        reads = [p for p in fake.reads if p.endswith("/sub_issues")]
        self.assertEqual(len(reads), len(set(reads)), reads)

    def test_a_member_added_in_this_run_counts_as_a_member_afterwards(self):
        fake = fresh_forge()
        fg = github(fake)
        epic = fg.get_epic("example-org/search-service#10")
        fresh = fg.get_issue("example-org/search-service#12")
        self.assertFalse(fg.in_epic(fresh, epic))
        fg.add_to_epic(fresh, epic)
        self.assertTrue(fg.in_epic(fresh, epic))


class GitLabOpenEpics(unittest.TestCase):
    def test_open_epics_are_listed_once_for_the_whole_run(self):
        class Counting(NoWrites):
            calls = 0

            def get_all(self, path):
                if "epics?state=opened" in path:
                    Counting.calls += 1
                return super().get_all(path)

        fg = forge.GitLab(Counting(fixture("gitlab_publish.json")), host="gitlab.example.com",
                          project="acme/search", group="acme")
        data = gitlab_roadmap()
        data["epics"][0].pop("ref")          # two epics without a ref, so each would search the list
        data["epics"][0].pop("url", None)
        publish.publish(data, fg, apply=False)
        self.assertEqual(Counting.calls, 1)


if __name__ == "__main__":
    unittest.main()
