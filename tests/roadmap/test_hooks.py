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
from unittest import mock

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

    def transcript(self, text, commands=(), turns=()):
        """A transcript: earlier (text, commands) turns, then the user's text and the Bash commands this turn ran.

        Each command gets a tool result, which is a user line but not a new turn.
        """
        lines = []
        for n, (said, ran) in enumerate([*turns, (text, commands)]):
            lines.append({"type": "user", "message": {"role": "user", "content": said}})
            for k, command in enumerate(ran):
                lines.append({"type": "assistant", "message": {"content": [
                    {"type": "text", "text": "Running it."},
                    {"type": "tool_use", "id": f"t{n}-{k}", "name": "Bash", "input": {"command": command}}]}})
                lines.append({"type": "user", "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": f"t{n}-{k}", "content": "ok"}]}})
        path = self.dir / "transcript.jsonl"
        path.write_text("".join(json.dumps(x) + "\n" for x in lines))
        return path

    def run_hook(self, mode, payload, recorded="gitlab_sync.json", extra_env=None, argv=()):
        env = {k: v for k, v in os.environ.items() if not k.startswith("ROADMAP_")}
        env.update({"ROADMAP_HOOK_NOW": "2026-11-17"})
        if recorded:
            env["ROADMAP_HOOK_RECORDED"] = str(FIXTURES / recorded) if "/" not in recorded else recorded
        env.update(extra_env or {})
        return subprocess.run([sys.executable, str(HOOK), mode, *argv], input=json.dumps(payload), text=True,
                              capture_output=True, env=env, cwd=self.dir, timeout=60)

    def stop(self, text, active=False, commands=(), turns=(), **kw):
        return self.run_hook("stop", {"hook_event_name": "Stop", "cwd": str(self.dir), "stop_hook_active": active,
                                      "transcript_path": str(self.transcript(text, commands, turns))}, **kw)

    def load(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("roadmap_hook_under_test", HOOK)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


class StopHook(Hook):
    def test_no_roadmap_means_nothing_to_check(self):
        res = self.stop("worked on page-design")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), "")

    def test_drift_on_work_this_session_changed_blocks_the_turn(self):
        data = sync_roadmap()
        issue(data, "page-design")["status"] = "done"     # #20 is still open on the forge
        self.roadmap(data)
        res = self.stop("Finish the results page design.",
                        commands=['git commit -m "feat: results page layout (page-design)"'])
        self.assertEqual(res.returncode, 0, res.stderr)
        out = json.loads(res.stdout)
        self.assertEqual(out["decision"], "block")
        self.assertIn("done-but-open", out["reason"])
        self.assertLess(len(out["reason"]), 900)

    def test_a_roadmap_behind_the_forge_blocks_a_turn_that_changed_the_issue(self):
        self.roadmap()
        res = self.stop("Merge it.", commands=["glab mr merge 31 --squash  # ranking-model"])
        out = json.loads(res.stdout)
        self.assertEqual(out["decision"], "block")
        self.assertIn("--write", out["reason"])

    def test_an_issue_only_mentioned_is_not_checked(self):
        """Reading roadmap.json or asking about an issue names it; that is not work on it, so nothing is synced."""
        data = sync_roadmap()
        issue(data, "page-design")["status"] = "done"
        self.roadmap(data)
        res = self.stop("What does page-design depend on? Just asking, no work. Also ranking-model?",
                        commands=["cat roadmap.json", "python3 tools/roadmap/roadmap.py validate roadmap.json"])
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), "")

    def test_only_changes_made_in_this_turn_are_checked(self):
        data = sync_roadmap()
        issue(data, "page-design")["status"] = "done"
        self.roadmap(data)
        earlier = [("Finish the results page design.", ['git commit -m "feat: results page layout (page-design)"'])]
        res = self.stop("Thanks. What is next on the roadmap?", turns=earlier, commands=["cat roadmap.json"])
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), "")
        res = self.stop("Commit it.", turns=earlier, commands=['git commit -m "fix: spacing (page-design)"'])
        self.assertEqual(json.loads(res.stdout)["decision"], "block")

    def test_text_that_only_looks_like_a_change_command_is_not_one(self):
        data = sync_roadmap()
        issue(data, "page-design")["status"] = "done"
        self.roadmap(data)
        for command in ("echo 'git commit page-design'", 'printf "%s" "gh pr create page-design"',
                        "grep -n 'git push' notes.md  # page-design", "# git commit page-design"):
            with self.subTest(command=command):
                res = self.stop("Look around.", commands=[command])
                self.assertEqual(res.stdout.strip(), "")

    def test_real_change_commands_count_in_any_form(self):
        hook = self.load()
        for command in ('cd repo && git commit -m "x"', 'git -C repo -c user.name=x commit -m "x"',
                        "FOO=1 gh pr create --title x", "(cd repo; /usr/bin/git push origin HEAD)",
                        "git status\ngit commit -m 'it\'s done'", "git commit -F - <<'EOF'\nDon't stop\nEOF",
                        "tea pulls merge 3", "glab issue close 20", "echo start  # note\ngit commit -m x",
                        'git commit -m "first line\nsecond line"'):
            with self.subTest(command=command):
                self.assertTrue(hook.runs_change(command))
        for command in ("echo 'git commit x'", "git log --oneline", "gh pr view 3", "cat roadmap.json",
                        "python3 -c 'import os; os.system(\"ls\")'", "git commitish"):
            with self.subTest(command=command):
                self.assertFalse(hook.runs_change(command))

    def test_a_turn_that_changed_many_issues_checks_a_capped_few(self):
        """Each issue costs forge calls; the turn end must stay well inside the hook's timeout."""
        data = sync_roadmap()
        self.roadmap(data)
        hook = self.load()
        ids = [it["id"] for it in data["issues"]]
        seen = []

        def fake_sync(path, chosen):
            seen.append(list(chosen))
            return {"drift": [], "status_changes": [], "gate_ticks": []}, None

        commands = "\n".join(f'git commit -m "work on {i}"' for i in ids)
        with mock.patch.object(hook, "run_sync", fake_sync), mock.patch.object(hook, "MAX_STOP_ISSUES", 2), \
                mock.patch.dict("os.environ", {"ROADMAP_FILE": str(self.dir / "roadmap.json")}):
            fix, show, warning, checked = hook.check(str(self.dir), commands, limit=hook.MAX_STOP_ISSUES)
        self.assertEqual(len(seen), 1)
        self.assertEqual(len(seen[0]), 2)
        self.assertEqual(checked, seen[0])
        self.assertTrue(any("not checked" in line for line in show), show)
        self.assertLessEqual(self.load().MAX_STOP_ISSUES, 5)
        stop_timeout = json.loads(HOOKS_JSON.read_text())["hooks"]["Stop"][0]["hooks"][0]["timeout"]
        self.assertLessEqual(hook.DEFAULT_TIMEOUT, stop_timeout - 10)

    def test_drift_only_the_lead_or_time_can_clear_never_blocks(self):
        """A stale backlog item and a lead gate ticked on the forge need the lead, not the agent."""
        data = sync_roadmap()
        issue(data, "page-design")["status"] = "to_do"    # #20: D ticked on the forge, no activity for weeks
        self.roadmap(data)
        res = self.stop("Started on it.", commands=['git commit -m "chore: page-design sketch"'])
        out = json.loads(res.stdout or "{}")
        self.assertNotIn("decision", out)
        self.assertIn("lead-gate-ticked-on-forge", out.get("systemMessage", ""))
        self.assertNotIn("no-recent-activity", out.get("systemMessage", ""))

    def test_work_not_on_the_roadmap_is_not_checked(self):
        self.roadmap()
        res = self.stop("Tidied the docs.")
        self.assertEqual(res.stdout.strip(), "")

    def test_it_never_blocks_twice_in_a_row(self):
        self.roadmap()
        res = self.stop("Merge it.", active=True, commands=["glab mr merge 31  # ranking-model"])
        self.assertEqual(res.stdout.strip(), "")

    def test_network_errors_fail_open_with_a_warning(self):
        data = sync_roadmap()
        data["forge"] = {"kind": "forgejo", "host": "127.0.0.1:9", "project": "acme/search"}   # nothing listens
        self.roadmap(data)
        res = self.stop("Merge it.", commands=["glab mr merge 31  # ranking-model"], recorded=None)
        self.assertEqual(res.returncode, 0)
        out = json.loads(res.stdout)
        self.assertNotIn("decision", out)
        self.assertIn("skipped", out["systemMessage"])

    def test_a_broken_tool_fails_open_too(self):
        self.roadmap()
        res = self.stop("Merge it.", commands=["glab mr merge 31  # ranking-model"],
                        recorded=str(self.dir / "missing.json"))
        self.assertEqual(res.returncode, 0)
        out = json.loads(res.stdout)
        self.assertNotIn("decision", out)
        self.assertIn("skipped", out["systemMessage"])


class QuietWithoutARoadmap(Hook):
    """The hook runs in every project; it says nothing unless this one has a roadmap of ours."""

    def test_an_old_python_is_silent_where_there_is_no_roadmap(self):
        hook = self.load()
        with mock.patch.object(hook.sys, "version_info", (3, 9, 6)), \
                mock.patch.dict("os.environ", {"ROADMAP_FILE": ""}):
            self.assertEqual(hook.check(str(self.dir), "page-design"), ([], [], None, []))
            self.roadmap()
            fix, show, warning, _ = hook.check(str(self.dir), "page-design")
        self.assertIn("3.11", warning)

    def test_a_roadmap_json_from_another_tool_is_ignored(self):
        for other in ({"name": "q3", "items": ["page-design"]}, {"issues": "page-design", "epics": 3}, ["page-design"],
                      {"issues": [{"id": "page-design"}]}):
            with self.subTest(other=other):
                (self.dir / "roadmap.json").write_text(json.dumps(other))
                res = self.stop("worked on page-design", commands=['git commit -m "page-design"'])
                self.assertEqual(res.returncode, 0, res.stderr)
                self.assertEqual(res.stdout.strip(), "")


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
        for command in ("ls -la", "echo 'glab mr merge 31'", "grep 'gh issue close' notes.md"):
            with self.subTest(command=command):
                self.assertEqual(self.post(command).stdout.strip(), "")


class EveryHookIsCapped(Hook):
    """PostToolUse and codex-notify sync at most MAX_STOP_ISSUES issues, like the Stop hook."""

    def many(self):
        data = sync_roadmap()
        for n, it in enumerate(data["issues"]):
            it["status"], it["ref"] = "in_progress", it.get("ref") or f"acme/search#{100 + n}"
        self.roadmap(data)
        return [it["id"] for it in data["issues"]]

    def capped(self, call):
        hook = self.load()
        seen = []

        def fake_sync(path, chosen):
            seen.append(list(chosen))
            return {"drift": [], "status_changes": [], "gate_ticks": []}, None

        with mock.patch.object(hook, "run_sync", fake_sync), mock.patch.object(hook, "MAX_STOP_ISSUES", 2), \
                mock.patch.object(hook, "notify", lambda message: seen.append(message)), \
                mock.patch.dict("os.environ", {"ROADMAP_FILE": str(self.dir / "roadmap.json")}):
            call(hook)
        return seen

    def test_a_merge_that_names_no_issue_syncs_a_capped_few(self):
        ids = self.many()
        self.assertGreater(len(ids), 2)
        seen = self.capped(lambda hook: hook.post_tool_use(
            {"tool_name": "Bash", "cwd": str(self.dir), "tool_input": {"command": "glab mr merge 99"}}))
        self.assertEqual([len(x) for x in seen], [2])

    def test_codex_notify_syncs_a_capped_few(self):
        ids = self.many()
        payload = json.dumps({"type": "agent-turn-complete", "cwd": str(self.dir),
                              "input-messages": [" ".join(ids)], "last-assistant-message": "Done."})
        seen = self.capped(lambda hook: hook.codex_notify(payload))
        self.assertEqual(len(seen[0]), 2)


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
