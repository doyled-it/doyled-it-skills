"""Command-line interface for the roadmap tool."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import model, render, validate


def _load(path: str) -> dict:
    try:
        return model.load(path)
    except model.RoadmapError as exc:
        print(f"error: {exc}")
        raise SystemExit(1) from exc


def _refuse_broken(data: dict) -> bool:
    """Print the findings and return True when the roadmap's shape is too broken to run a command on."""
    from . import render

    blocking = [f for f in validate.errors(validate.check(data)) if f.code in render.BLOCKING]
    if blocking:
        print("error: fix these first (roadmap.py validate lists them all):")
        for f in blocking:
            print(f"  {f}")
    return bool(blocking)


def cmd_validate(args) -> int:
    findings = validate.check(_load(args.roadmap))
    for f in findings:
        print(f)
    n_err = len(validate.errors(findings))
    print(f"{n_err} errors, {len(findings) - n_err} warnings")
    return 1 if n_err else 0


def cmd_render(args) -> int:
    data = _load(args.roadmap)
    try:
        page = render.render_page(data, author_icon_dir=args.author_icon_dir)
    except render.RenderError as exc:
        print(exc)
        return 1
    out = Path(args.out) if args.out else Path(args.roadmap).with_suffix(".html")
    out.write_text(page)
    print(f"wrote {out} ({len(data['issues'])} issues, {len(data['epics'])} epics)")
    for f in validate.errors(validate.check(data)):
        print(f"note: {f}")
    return 0


def cmd_epic_preview(args) -> int:
    from . import preview

    data = _load(args.roadmap)
    if args.epic not in {e.get("id") for e in data.get("epics", [])}:
        print(f'error: no epic "{args.epic}" in {args.roadmap}')
        return 1
    try:
        page = render.render_page(data, author_icon_dir=args.author_icon_dir)
    except render.RenderError as exc:
        print(exc)
        return 1
    src = Path(args.roadmap)
    out = Path(args.out) if args.out else src.with_name(f"{src.stem}-epic-{args.epic}.html")
    # The full page goes beside the preview under the preview's own name, so it
    # never replaces a page of the same name the user keeps there.
    full = out.with_name(f"{out.stem}-full.html")
    for path in (out, full):
        if path.exists() and 'name="generator" content="roadmap' not in path.read_text(errors="replace")[:2000]:
            print(f"error: {path} exists and was not written by roadmap; choose another -o")
            return 1
    full.write_text(page)
    kind = (data.get("forge") or {}).get("kind")
    out.write_text(preview.preview_page(data, args.epic, full.name, task_list=kind in ("forgejo", "gitea")))
    print(f"wrote {out} (preview of epic {args.epic}, nothing written to the forge) and the full page {full}")
    return 0


def cmd_publish(args) -> int:
    from . import forge, publish

    data = _load(args.roadmap)
    if _refuse_broken(data):
        return 2
    try:
        fg = forge.from_args(data, args)
        report = publish.publish(data, fg, apply=args.apply, allow_draft=False)
    except (publish.PublishRefused, forge.ForgeError) as exc:
        print(f"error: {exc}")
        return 2
    print(report.text())
    if args.apply and report.changed:
        model.save(args.roadmap, report.roadmap)
        print(f"wrote forge links back into {args.roadmap}")
    return 2 if report.failed else 0


def cmd_sync(args) -> int:
    from . import forge, orca, sync

    if args.only is not None and args.update_drift_issue:
        print("error: --update-drift-issue requires a program-wide sync. Remove --only to update the shared issue.")
        return 2
    if args.update_epics and not args.write:
        print("error: --update-epics needs --write, so the epics on the forge and roadmap.json show the same status")
        return 2
    data = _load(args.roadmap)
    if _refuse_broken(data):
        return 2
    try:
        fg = forge.from_args(data, args)
    except forge.ForgeError as exc:
        print(f"error: {exc}")
        return 2
    only = {key.strip() for key in args.only.split(",") if key.strip()} if args.only is not None else None
    tasks = orca.tasks_from_args(data, args) if only is None else None
    try:
        report = sync.sync(data, fg, orca_tasks=tasks, stale_days=args.stale_days, now=args.now,
                           update_epics=args.update_epics, only=only)
    except (sync.SyncRefused, forge.ForgeError) as exc:
        print(f"error: {exc}")
        return 2
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(report.text())
    if report.errors:
        return 1
    if args.write and report.changed:
        model.save(args.roadmap, report.roadmap)
        print(f"saved sync updates in {args.roadmap}. Re-render the page next.")
    if args.update_drift_issue:
        if report.orca_complete is False:
            print("Orca coverage is incomplete. The drift issue was left as it is.", file=sys.stderr)
            return 1
        # The drift issue is written from this same report, so a scheduled run syncs once.
        from datetime import date

        from . import driftissue

        try:
            result = driftissue.run(data, fg, report, apply=True, today=args.now or date.today().isoformat())
        except forge.ForgeError as exc:
            print(f"error: {exc}")
            return 2
        print(result.text())
    return 1 if report.write_errors else 0


def cmd_check_mr(args) -> int:
    from . import checkmr

    changed = args.changed
    try:
        if args.from_ci:
            title, body, project = checkmr.from_ci()
            base = checkmr.ci_base()
            if not base:
                # The only roadmap left would be the merge request's own copy, which it can edit.
                print("error: the forge gave no base commit (CI_MERGE_REQUEST_DIFF_BASE_SHA on GitLab, "
                      "pull_request.base.sha on GitHub and Forgejo), so the agreed roadmap cannot be read; "
                      "run the job only for merge request pipelines")
                return 2
            # The agreed roadmap is the base commit's, never the merge request's own copy.
            data = checkmr.base_roadmap(base, args.roadmap)
            if changed is None:
                changed = checkmr.changed_files(base)
                if changed is None:
                    print("note: git could not list the changed files (fetch the full history); checked the "
                          "title and description only")
        else:
            data = _load(args.roadmap)
            body = args.body or ""
            if args.body_file:
                body = Path(args.body_file).read_text()
            title, project = args.title or "", args.project or (data.get("forge") or {}).get("project")
    except (ValueError, OSError) as exc:
        print(f"error: {exc}")
        return 2
    result = checkmr.check(data, title, body, project, changed=changed, roadmap_path=args.roadmap)
    print(("OK: " if result.ok else "FAIL: ") + result.message)
    for w in result.warnings:
        print(f"warning: {w}")
    return 0 if result.ok else 1


def cmd_drift_issue(args) -> int:
    from datetime import date

    from . import driftissue, forge, orca, sync

    data = _load(args.roadmap)
    if _refuse_broken(data):
        return 2
    try:
        fg = forge.from_args(data, args)
        tasks = orca.tasks_from_args(data, args)
        report = sync.sync(data, fg, orca_tasks=tasks, stale_days=args.stale_days, now=args.now)
        if isinstance(tasks, orca.TaskCollection):
            for note in tasks.notes:
                print(f"note: {note}")
        if report.orca_complete is False:
            print("Orca coverage is incomplete. The drift issue was left as it is.")
            return 1
        result = driftissue.run(data, fg, report, apply=args.apply, today=args.now or date.today().isoformat())
    except (sync.SyncRefused, forge.ForgeError, ValueError) as exc:
        print(f"error: {exc}")
        return 2
    print(result.text())
    return 1 if report.errors else 0


def _iso_date(value: str) -> str:
    from . import sync

    try:
        sync.parse_now(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f'"{value}" is not an ISO date such as 2026-11-17') from None
    return value


def _forge_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--forge", choices=("gitlab", "github", "forgejo"),
                   help="override the forge kind (default: roadmap forge.kind, then the git remote)")
    p.add_argument("--repo", default=".", help="checkout whose origin remote picks the forge (default: .)")
    p.add_argument("--recorded", metavar="FILE",
                   help="answer forge reads from a recorded JSON file instead of the network (tests, demos)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="roadmap", description="Keep one agreed roadmap and work only from it.")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="check schema, cycles, dangling dependencies, glossary")
    v.add_argument("roadmap")
    v.set_defaults(func=cmd_validate)

    r = sub.add_parser("render", help="write the one-page HTML roadmap")
    r.add_argument("roadmap")
    r.add_argument("-o", "--out", help="output HTML path (default: roadmap path with .html)")
    r.add_argument("--author-icon-dir", type=Path, help="directory with optional claude.svg and codex.svg")
    r.set_defaults(func=cmd_render)

    ep = sub.add_parser("epic-preview",
                        help="write a local page showing an epic's generated section beside the full roadmap")
    ep.add_argument("roadmap")
    ep.add_argument("--epic", required=True, help="epic id")
    ep.add_argument("-o", "--out", help="output HTML path (default: <roadmap>-epic-<id>.html)")
    ep.add_argument("--author-icon-dir", type=Path, help="directory with optional claude.svg and codex.svg for the full page")
    ep.set_defaults(func=cmd_epic_preview)

    pb = sub.add_parser("publish", help="create or update forge epics and issues (dry run by default)")
    pb.add_argument("roadmap")
    pb.add_argument("--apply", action="store_true", help="make the changes; without it nothing is written")
    _forge_args(pb)
    pb.set_defaults(func=cmd_publish)

    c = sub.add_parser("check-mr", help="fail a merge request that names no issue on the agreed roadmap")
    c.add_argument("roadmap")
    c.add_argument("--from-ci", action="store_true",
                   help="read the merge request from GitLab CI, GitHub Actions or Forgejo Actions")
    c.add_argument("--title", help="merge request title")
    c.add_argument("--body", help="merge request description")
    c.add_argument("--body-file", help="read the description from this file")
    c.add_argument("--project", help='project for "#12" references (default: forge.project)')
    c.add_argument("--changed", nargs="*", metavar="PATH",
                   help="files the merge request changes (with --from-ci: read from git); a change to only the "
                        "roadmap and its page passes")
    c.set_defaults(func=cmd_check_mr)

    d = sub.add_parser("drift-issue", help='keep one "Roadmap drift" issue current (dry run unless --apply)')
    d.add_argument("roadmap")
    d.add_argument("--apply", action="store_true", help="create, update or close the drift issue")
    d.add_argument("--stale-days", type=int, default=14, help="no activity for this many days is drift")
    d.add_argument("--now", type=_iso_date, help="ISO date to measure staleness from (default: today)")
    d.add_argument("--orca-run", help="read only this live Orca run (default: coordinator runs and roadmap orca.run)")
    d.add_argument("--orca-json", help="read Orca tasks from this JSON file instead of the orca CLI")
    d.add_argument("--no-orca", action="store_true", help="skip the Orca check")
    _forge_args(d)
    d.set_defaults(func=cmd_drift_issue)

    s = sub.add_parser("sync", help="read status, merge requests, pipelines and Orca tasks; report drift")
    s.add_argument("roadmap")
    s.add_argument("--write", action="store_true",
                   help="save proposed updates to local roadmap.json after root review")
    s.add_argument("--update-epics", action="store_true",
                   help="rewrite each generated epic section on the forge (requires --write)")
    s.add_argument("--update-drift-issue", action="store_true",
                   help="also create, update or close the one Roadmap drift issue from this same report "
                        "(what drift-issue --apply does, without a second sync)")
    s.add_argument("--json", action="store_true", help="print the report as JSON")
    s.add_argument("--stale-days", type=int, default=14, help="no activity for this many days is drift")
    s.add_argument("--now", type=_iso_date, help="ISO date to measure staleness from (default: today)")
    s.add_argument("--orca-run", help="read only this live Orca run (default: coordinator runs and roadmap orca.run)")
    s.add_argument("--orca-json", help="read Orca tasks from this JSON file instead of the orca CLI")
    s.add_argument("--no-orca", action="store_true", help="skip the Orca check")
    s.add_argument("--only", metavar="IDS",
                   help="check only these roadmap issues (comma-separated short names); skips epics, "
                        "the scan for unlinked open merge requests, and Orca")
    _forge_args(s)
    s.set_defaults(func=cmd_sync)
    return p


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 11):
        print("error: roadmap needs Python 3.11 or newer")
        return 2
    args = build_parser().parse_args(argv)
    return args.func(args)
