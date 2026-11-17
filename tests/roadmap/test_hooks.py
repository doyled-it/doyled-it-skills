"""Agent enforcement (layer 2): the Claude Code hooks and the Codex notify program.

The hook script is driven with real hook payloads. Forge reads come from
recorded responses (ROADMAP_HOOK_RECORDED), so nothing touches the network.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import FIXTURES, ROOT, fixture, issue
from test_publish import NoWrites
from test_sync import sync_roadmap

from roadmaplib import forge, sync

HOOK = ROOT / "plugins" / "roadmap" / "hooks" / "roadmap_hook.py"
HOOKS_JSON = ROOT / "plugins" / "roadmap" / "hooks" / "hooks.json"


class Hook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def roadmap(self, data=None):
        path = self.dir / "roadmap.json"
        path.write_text(json.dumps(data or sync_roadmap()))
        return path

    def transcript(self, text):
        path = self.dir / "transcript.jsonl"
        path.write_text(json.dumps({"type": "user", "message": {"content": text}}) + "\n")
        return path

    def run_hook(self, mode, payload, recorded="gitlab_sync.json", extra_env=None, argv=()):
        env = {k: v for k, v in os.environ.items() if not k.startswith("ROADMAP_")}
        env.update({"ROADMAP_HOOK_NOW": "2026-11-17"})
        if recorded:
            env["ROADMAP_HOOK_RECORDED"] = str(FIXTURES / recorded) if "/" not in recorded else recorded
        env.update(extra_env or {})
        return subprocess.run([sys.executable, str(HOOK), mode, *argv], input=json.dumps(payload), text=True,
                              capture_output=True, env=env, cwd=self.dir, timeout=60)

    def stop(self, text, active=False, **kw):
        return self.run_hook("stop", {"hook_event_name": "Stop", "cwd": str(self.dir), "stop_hook_active": active,
                                      "transcript_path": str(self.transcript(text))}, **kw)


class StopHook(Hook):
    def test_no_roadmap_means_nothing_to_check(self):
        res = self.stop("worked on page-design")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), "")

    def test_drift_on_work_this_session_touched_blocks_the_turn(self):
        data = sync_roadmap()
        issue(data, "page-design")["status"] = "done"     # #20 is still open on the forge
        self.roadmap(data)
        res = self.stop("Finished page-design and sent the update.")
        self.assertEqual(res.returncode, 0, res.stderr)
        out = json.loads(res.stdout)
        self.assertEqual(out["decision"], "block")
        self.assertIn("page-design", out["reason"])
        self.assertLess(len(out["reason"]), 900)

    def test_a_roadmap_behind_the_forge_blocks_the_turn(self):
        self.roadmap()
        res = self.stop("Merged the change for ranking-model.")
        out = json.loads(res.stdout)
        self.assertEqual(out["decision"], "block")
        self.assertIn("--write", out["reason"])

    def test_work_not_on_the_roadmap_is_not_checked(self):
        self.roadmap()
        res = self.stop("Tidied the docs.")
        self.assertEqual(res.stdout.strip(), "")

    def test_it_never_blocks_twice_in_a_row(self):
        self.roadmap()
        res = self.stop("Merged the change for ranking-model.", active=True)
        self.assertEqual(res.stdout.strip(), "")

    def test_network_errors_fail_open_with_a_warning(self):
        data = sync_roadmap()
        data["forge"] = {"kind": "forgejo", "host": "127.0.0.1:9", "project": "acme/search"}   # nothing listens
        self.roadmap(data)
        res = self.stop("Merged the change for ranking-model.", recorded=None)
        self.assertEqual(res.returncode, 0)
        out = json.loads(res.stdout)
        self.assertNotIn("decision", out)
        self.assertIn("skipped", out["systemMessage"])

    def test_a_broken_tool_fails_open_too(self):
        self.roadmap()
        res = self.stop("Merged the change for ranking-model.", recorded=str(self.dir / "missing.json"))
        self.assertEqual(res.returncode, 0)
        self.assertNotIn("decision", json.loads(res.stdout))


class PostToolUseHook(Hook):
    def post(self, command):
        return self.run_hook("post-tool-use", {"hook_event_name": "PostToolUse", "cwd": str(self.dir),
                                               "tool_name": "Bash", "tool_input": {"command": command}})

    def test_a_merge_runs_sync_and_tells_the_agent(self):
        self.roadmap()
        res = self.post("glab mr merge 31 --squash")
        self.assertEqual(res.returncode, 0, res.stderr)
        ctx = json.loads(res.stdout)["hookSpecificOutput"]
        self.assertEqual(ctx["hookEventName"], "PostToolUse")
        self.assertIn("ranking-model", ctx["additionalContext"])

    def test_an_issue_close_runs_sync(self):
        self.roadmap()
        res = self.post("gh issue close 20")
        self.assertIn("hookSpecificOutput", res.stdout)

    def test_other_commands_do_nothing(self):
        self.roadmap()
        self.assertEqual(self.post("ls -la").stdout.strip(), "")


class CodexNotify(Hook):
    def test_drift_is_sent_to_the_notifier(self):
        data = sync_roadmap()
        issue(data, "page-design")["status"] = "done"
        self.roadmap(data)
        seen = self.dir / "seen.txt"
        notifier = self.dir / "notify.sh"
        notifier.write_text(f'#!/bin/sh\nprintf "%s" "$1" > "{seen}"\n')
        notifier.chmod(0o755)
        payload = json.dumps({"type": "agent-turn-complete", "cwd": str(self.dir),
                              "input-messages": ["finish page-design"], "last-assistant-message": "Done."})
        res = self.run_hook("codex-notify", {}, argv=(payload,), extra_env={"ROADMAP_HOOK_NOTIFIER": str(notifier)})
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("page-design", seen.read_text())


class HooksJson(unittest.TestCase):
    def test_plugin_registers_post_tool_use_and_stop(self):
        hooks = json.loads(HOOKS_JSON.read_text())["hooks"]
        post = hooks["PostToolUse"][0]
        self.assertEqual(post["matcher"], "Bash")
        self.assertIn("roadmap_hook.py\" post-tool-use", post["hooks"][0]["command"])
        self.assertIn("roadmap_hook.py\" stop", hooks["Stop"][0]["hooks"][0]["command"])
        for entry in (post, hooks["Stop"][0]):
            self.assertLessEqual(entry["hooks"][0]["timeout"], 60)


class SyncOnly(unittest.TestCase):
    def test_only_reads_the_named_issues(self):
        responses = {k: v for k, v in fixture("gitlab_sync.json").items() if "/issues/12" in k or
                     "merge_requests/31" in k}
        fg = forge.GitLab(NoWrites(responses), host="h", project="acme/search", group="acme")
        report = sync.sync(sync_roadmap(), fg, orca_tasks=None, now="2026-11-17", only={"ranking-model"})
        self.assertEqual(report.errors, [])
        self.assertEqual([c.issue for c in report.status_changes], ["ranking-model"])
        self.assertFalse([d for d in report.drift if d.target != "ranking-model"])


if __name__ == "__main__":
    unittest.main()
