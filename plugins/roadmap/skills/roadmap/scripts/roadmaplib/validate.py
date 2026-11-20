"""validate: schema, dependency cycles, dangling dependencies, and glossary checks.

Errors mean the roadmap cannot be rendered or published as it stands.
Warnings are things a reader should look at before the next update.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import chain

from . import blocks, model, observation

READABLE_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
# Codes such as A1, T1.1, E1.4 or TE2 used instead of a readable name.
CODE = re.compile(r"\b[A-Z]{1,4}\d+(?:\.\d+)*[a-z]?\b")
# Ordinary technical words that look like codes. A roadmap may add its own in
# "allowed_terms".
TECH_TERMS = {t.casefold() for t in (
    "S3", "EC2", "UTF8", "UTF16", "UTF32", "HTTP1", "HTTP2", "HTTP3", "MP3", "MP4", "H264", "H265", "IPV4", "IPV6",
    "SHA1", "SHA256", "SHA512", "MD5", "OAUTH2", "P50", "P90", "P95", "P99", "K8S", "B2B", "B2C", "WCAG2", "ES6",
    "X509", "TLS1", "CO2", "PM25", "L1", "L2", "L3", "G5", "AV1", "VP9", "DDR4", "DDR5", "PCIE4", "PCIE5", "USB3",
    "RS232", "ISO8601", "BASE64")}
GATE_LETTER = re.compile(r"^[A-Z]$")
CODE_ID = re.compile(r"^[a-z]{1,3}\d+(?:[.-]\d+)*$")
MILESTONE = re.compile(r"\bmilestones?\b", re.IGNORECASE)
BAD_AUTHOR_CHAR = re.compile(r"[A-Z]|[^ -~]")
# Words the glossary replaces, and what to say instead.
SYNONYMS = {
    r"\bsprints?\b": "Iteration",
    r"\btickets?\b": "Issue",
    r"\bwork ?streams?\b": "Epic",
    r"\bswim ?lanes?\b": "Epic",
}
URL = re.compile(r"https?://\S+")
_PATH = r"[\w.-]+(?:/[\w.-]+)*"
ISSUE_REF = re.compile(rf"^{_PATH}#\d+$")
GITLAB_EPIC_REF = re.compile(rf"^{_PATH}&\d+$")
HASH_EPIC_REF = re.compile(rf"^{_PATH}#\d+$")
FORGES = ("gitlab", "github", "forgejo", "gitea")
BARE_HOST = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?(?::\d{1,5})?$")
WHERE_LEVELS = "orchestration.levels"


def _epic_ref_ok(ref: object, kind: str | None) -> bool:
    """GitLab epics are group&N; GitHub and Forgejo parents are issues, project#N; unknown allows both."""
    ref = str(ref)
    if kind == "gitlab":
        return bool(GITLAB_EPIC_REF.match(ref))
    if kind in ("github", "forgejo", "gitea"):
        return bool(HASH_EPIC_REF.match(ref))
    return bool(GITLAB_EPIC_REF.match(ref) or HASH_EPIC_REF.match(ref))


@dataclass(frozen=True)
class Finding:
    level: str  # "error" or "warning"
    code: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level}: {self.where}: {self.message} [{self.code}]"


def check(raw: dict) -> list[Finding]:
    """Run every check and return the findings, errors first."""
    out: list[Finding] = []

    def err(code, where, msg):
        out.append(Finding("error", code, where, msg))

    def warn(code, where, msg):
        out.append(Finding("warning", code, where, msg))

    for key in model.REQUIRED_TOP:
        if key not in raw:
            err("missing-field", "roadmap", f'missing required field "{key}"')
    if "agreed" in raw and not isinstance(raw["agreed"], bool):
        err("bad-type", "agreed", '"agreed" must be true or false')
    for key in ("title", "version", "date", "goal", "rule"):
        if key in raw and not isinstance(raw[key], str):
            err("bad-type", key, f'"{key}" must be text')
    for key in ("epics", "issues"):
        if key in raw and not isinstance(raw[key], list):
            err("bad-type", key, f'"{key}" must be a list')
            return out
    if "gates" in raw and not isinstance(raw["gates"], dict):
        err("bad-type", "gates", '"gates" must map each gate letter to what it checks')
        return out
    for letter, text in (raw.get("gates") or {}).items():
        if not GATE_LETTER.match(str(letter)) or not isinstance(text, str):
            err("bad-gate", f"gates.{letter}", "each gate is one capital letter with a plain description")

    raw = _well_typed(raw, err)
    _check_ownership(raw, err)
    _check_levels(raw, err)
    if "orca_observation" in raw:
        for location, problem in observation.problems(raw["orca_observation"]):
            err("bad-type", f"orca_observation{location}", problem)
    timeline_text = list(_timeline_text_fields(raw.get("timeline", []), err))
    data = model.normalize({key: value for key, value in raw.items() if key != "timeline"})
    forge = data.get("forge")
    if forge is not None:
        if not isinstance(forge, dict) or forge.get("kind") not in FORGES:
            err("bad-forge", "forge", 'forge "kind" must be "gitlab", "github" or "forgejo"')
        elif forge.get("host") is not None and not BARE_HOST.match(str(forge["host"])):
            err("bad-forge", "forge.host", 'forge "host" must be a bare host name such as gitlab.example.com '
                "(no scheme, path or user)")

    gates = data["gates"]
    allowed = {t.casefold() for t in data.get("allowed_terms") or [] if isinstance(t, str)} | TECH_TERMS
    lead = model.lead_gates(data)
    if "lead_gates" in data and (not isinstance(data["lead_gates"], list)
                                 or any(not isinstance(g, str) or g not in gates for g in data["lead_gates"])):
        err("bad-lead-gates", "lead_gates", '"lead_gates" must list gate letters defined in "gates"')
    if isinstance(forge, dict):
        rules = forge.get("gate_rules") or {}
        if not isinstance(rules, dict):
            err("bad-gate-rule", "forge.gate_rules", '"gate_rules" must map a gate letter to a rule')
            rules = {}
        for letter, rule in rules.items():
            where = f"forge.gate_rules.{letter}"
            if rule == "mr_approved_green":
                err("bad-gate-rule", where, '"mr_approved_green" never checked approvals; it is now "mr_green" '
                    "(a linked merge request with a green pipeline)")
            elif rule not in ("mr_merged", "mr_green", "checklist"):
                err("bad-gate-rule", where, f'unknown rule "{rule}"; use mr_merged, mr_green or checklist')
            if letter in lead:
                err("bad-gate-rule", where, f'{letter} is a lead gate; it passes only from an approval recorded in '
                    'roadmap.json ("approved_by"), never from a forge rule')
            elif letter not in gates:
                err("bad-gate-rule", where, f'gate "{letter}" is not defined in "gates"')
    iterations = {i.get("name") for i in data.get("iterations", []) if isinstance(i, dict)}

    kind = forge.get("kind") if isinstance(forge, dict) and forge.get("kind") in FORGES else None

    # Epics.
    epic_ids: set[str] = set()
    for n, ep in enumerate(data["epics"]):
        where = f"epics[{ep.get('id', n)}]"
        for key in model.REQUIRED_EPIC:
            if not ep.get(key):
                err("missing-field", where, f'missing required field "{key}"')
        eid = ep.get("id")
        if eid in epic_ids:
            err("duplicate-id", where, f'epic id "{eid}" is used twice')
        if eid:
            epic_ids.add(eid)
            if not READABLE_ID.match(eid) or CODE_ID.match(eid):
                err("unreadable-id", where,
                    f'"{eid}" is not a short readable name (lowercase words joined by hyphens)')
        if ep.get("name") and _codes(ep["name"], allowed):
            err("glossary-code", f"{where}.name",
                f'"{ep["name"]}" uses a code; give the epic a plain name')
        if ep.get("ref") and not _epic_ref_ok(ep["ref"], kind):
            like = "group&12" if kind == "gitlab" else "group/project#12" if kind else "group&12 or group/project#12"
            err("bad-ref", f"{where}.ref", f'"{ep["ref"]}" is not a {kind or "forge"} epic reference like {like}')
    by_epic = {ep.get("id"): ep for ep in data["epics"]}
    for ep in data["epics"]:
        parent = ep.get("parent")
        if parent and parent not in epic_ids:
            err("unknown-parent", f"epics[{ep.get('id')}].parent", f'parent epic "{parent}" does not exist')
    for ep in data["epics"]:
        seen, cur = [], ep
        while cur and cur.get("parent"):
            if cur["id"] in seen:
                err("cycle", f"epics[{ep['id']}]", "epic parents loop: " + " -> ".join(seen + [cur["id"]]))
                break
            seen.append(cur["id"])
            cur = by_epic.get(cur["parent"])

    # Issues.
    ids: set[str] = set()
    for n, it in enumerate(data["issues"]):
        iid = it.get("id", f"#{n}")
        where = f"issues[{iid}]"
        for key in model.REQUIRED_ISSUE:
            if not it.get(key):
                err("missing-field", where, f'missing required field "{key}"')
        if iid in ids:
            err("duplicate-id", where, f'issue id "{iid}" is used twice')
        ids.add(iid)
        if iid in epic_ids:
            err("duplicate-id", where, f'"{iid}" names both an epic and an issue')
        if isinstance(iid, str) and (not READABLE_ID.match(iid) or CODE_ID.match(iid)):
            err("unreadable-id", where,
                f'"{iid}" is not a short readable name (lowercase words joined by hyphens)')
        if it.get("title") and _codes(it["title"], allowed):
            err("glossary-code", f"{where}.title",
                f'"{it["title"]}" uses a code; say what the issue delivers')
        if it.get("epic") and it["epic"] not in epic_ids:
            err("unknown-epic", f"{where}.epic", f'epic "{it["epic"]}" does not exist')
        if it.get("status") and it["status"] not in model.STATUSES:
            err("bad-status", f"{where}.status",
                f'"{it["status"]}" is not a status; use one of {", ".join(model.STATUSES)}')
        for g in it["gates"]:
            if g["gate"] not in gates:
                err("unknown-gate", f"{where}.gates", f'gate "{g["gate"]}" is not defined in "gates"')
            who = g.get("approved_by")
            if g["passed"] and g["gate"] in lead and not (isinstance(who, str) and who.strip()):
                err("unrecorded-approval", f"{where}.gates[{g['gate']}]",
                    f'{g["gate"]} is passed but only the program lead can pass it; record who approved it '
                    'and when ("approved_by" naming them, "approved_on"), or leave it open')
        days = it.get("estimate_days")
        if isinstance(days, (int, float)) and days > model.MAX_ISSUE_DAYS:
            err("too-big", where,
                f"{days} days is more than two weeks; make it a child epic with its own issues")
        if it.get("iteration") and iterations and it["iteration"] not in iterations:
            err("unknown-iteration", f"{where}.iteration", f'iteration "{it["iteration"]}" is not defined')
        if it.get("ref") and not ISSUE_REF.match(str(it["ref"])):
            err("bad-ref", f"{where}.ref", f'"{it["ref"]}" is not a forge reference like group/project#12')

    # Publish links forge items by title and by reference, so both must be unique.
    titles: dict[str, str] = {}
    refs: dict[str, str] = {}
    for kind, coll, key in (("epics", data["epics"], "name"), ("issues", data["issues"], "title")):
        for x in coll:
            where = f"{kind}[{x.get('id')}]"
            if isinstance(x.get(key), str) and x[key].strip():
                t = blocks.one_line(x[key]).casefold()
                if t in titles:
                    err("duplicate-title", f"{where}.{key}", f'"{x[key]}" is also the title of {titles[t]}; '
                        "publish links forge items by title, so give each epic and issue its own")
                titles.setdefault(t, where)
            if isinstance(x.get("ref"), str):
                if x["ref"] in refs:
                    err("duplicate-ref", f"{where}.ref", f'{x["ref"]} is also named by {refs[x["ref"]]}; '
                        "each forge item belongs to one epic or issue")
                refs.setdefault(x["ref"], where)

    items = {i["id"]: i for i in data["issues"] if i.get("id")}
    for iid, it in items.items():
        for d in it["depends_on"]:
            if d not in items:
                err("dangling-dependency", f"issues[{iid}].depends_on",
                    f'depends on "{d}", which is not an issue in this roadmap')
    for cyc in _cycles(items):
        err("cycle", f"issues[{cyc[0]}]", "dependencies loop: " + " -> ".join(cyc))

    # Glossary: never "milestone"; prefer the agreed words.
    timeline_prose = ((where, text) for where, text, _ in timeline_text)
    for where, text in chain(_strings(data), timeline_prose):
        plain = URL.sub("", text)
        if MILESTONE.search(plain):
            err("glossary-milestone", where,
                'uses "milestone"; say Gate (a check) or Issue (a deliverable) instead')
        for pattern, word in SYNONYMS.items():
            m = re.search(pattern, plain, re.IGNORECASE)
            if m:
                warn("glossary-term", where, f'uses "{m.group(0)}"; the glossary word is "{word}"')

    # Text the tool writes to the forge: one-line fields stay on one line, and
    # no field may carry text that looks like a generated-section marker.
    for where, text, multiline in chain(_text_fields(data), timeline_text):
        bad = blocks.CONTROL.findall(text.replace("\n", "").replace("\t", "") if multiline else text)
        if bad:
            err("control-character", where, "must be one line with no control characters" if not multiline
                else "has a control character other than a line break or tab")
    for where, text in _all_strings(raw, "roadmap"):
        if blocks.LOOSE_MARKER.search(text):
            err("marker-text", where, "holds text that looks like a generated-section marker (<!-- roadmap: ...); "
                "remove it")

    # Links: only plain http and https links are allowed anywhere they become live.
    for where, url in _url_fields(data):
        if not model.safe_url(url):
            err("bad-url", where, f'"{str(url)[:80]}" is not an http or https link')

    # Warnings about the state of the work.
    for iid, it in items.items():
        if it.get("status") == "done" and model.open_gates(it):
            warn("done-gates-open", f"issues[{iid}]",
                 "is Done but gates " + " ".join(model.open_gates(it)) + " are not ticked")
        if it.get("status") in ("in_progress", "in_review", "done"):
            waiting = [d for d in it["depends_on"] if d in items and items[d].get("status") != "done"]
            if waiting:
                warn("started-early", f"issues[{iid}]",
                     "started before its dependencies were Done: " + ", ".join(waiting))

    out.sort(key=lambda f: f.level != "error")
    return out


def errors(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.level == "error"]


def _check_ownership(data: dict, err) -> None:
    where = "orchestration.coordinators"
    orchestration = data.get("orchestration", {})
    if not isinstance(orchestration, dict):
        err("bad-type", "orchestration", '"orchestration" must be an object')
    elif not isinstance(orchestration.get("coordinators", {}), dict):
        err("bad-type", where, '"coordinators" must map coordinator keys to objects')
    owners = set()
    parents = {}
    for key, owner in model.coordinators(data).items():
        location = f"{where}.{key}"
        if not isinstance(key, str) or not key.strip() or not isinstance(owner, dict):
            err("bad-type", location, "each coordinator needs a nonblank key and an object")
            continue
        owners.add(key)
        for field in ("name", "run", "scope", "parent"):
            if field in owner and (not isinstance(owner[field], str) or not owner[field].strip()):
                err("bad-type", f"{location}.{field}", f'"{field}" must be nonblank text')
        if "role" in owner and owner["role"] not in model.COORDINATOR_ROLES:
            err("bad-coordinator-role", f"{location}.role", 'use "meta", "area" or "worker"')
        parent = owner.get("parent")
        if isinstance(parent, str) and parent.strip():
            parents[key] = parent
    for key, parent in parents.items():
        if parent not in owners:
            err("unknown-coordinator", f"{where}.{key}.parent", f'parent coordinator "{parent}" does not exist')
    for cycle in _cycles({key: {"depends_on": [parent]} for key, parent in parents.items()}):
        err("cycle", where, "coordinator parents form a cycle: " + " -> ".join(cycle))

    for kind in ("epics", "issues"):
        for index, item in enumerate(data.get(kind, [])):
            refs = item.get("orchestrators", [])
            location = f"{kind}[{item.get('id') or index}].orchestrators"
            if not isinstance(refs, list):
                err("bad-type", location, '"orchestrators" must be a list of coordinator keys')
                continue
            for n, key in enumerate(refs):
                if not isinstance(key, str) or not key.strip():
                    err("bad-type", f"{location}[{n}]", "each coordinator key must be nonblank text")
                elif key not in owners:
                    err("unknown-coordinator", f"{location}[{n}]", f'coordinator "{key}" does not exist')


def _nonblank(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_tier(tier: object, where: str, err) -> None:
    """One model choice: {"model": ..., optional "effort", "agent", "note"}."""
    if not isinstance(tier, dict):
        err("bad-type", where, 'must be an object with a "model"')
        return
    if "model" not in tier:
        err("missing-field", where, 'missing "model"')
    for field, value in tier.items():
        if field not in model.TIER_FIELDS:
            err("unknown-field", f"{where}.{field}", "use " + ", ".join(model.TIER_FIELDS))
        elif not _nonblank(value):
            err("bad-type", f"{where}.{field}", f'"{field}" must be nonblank text')


def _check_levels(data: dict, err) -> None:
    """orchestration.levels, recorded once from the kickoff level question."""
    orchestration = data.get("orchestration")
    if not isinstance(orchestration, dict) or "levels" not in orchestration:
        return
    levels = orchestration["levels"]
    if not isinstance(levels, dict):
        err("bad-type", WHERE_LEVELS, '"levels" must be an object')
        return
    for key in model.REQUIRED_LEVEL_FIELDS:
        if key not in levels:
            err("missing-field", WHERE_LEVELS, f'missing "{key}"; ask the level question at kickoff')
    for key in levels:
        if key not in model.LEVEL_FIELDS:
            err("unknown-field", f"{WHERE_LEVELS}.{key}", "use " + ", ".join(model.LEVEL_FIELDS))
    for level in ("program", "epic"):
        if level in levels:
            _check_tier(levels[level], f"{WHERE_LEVELS}.{level}", err)
    if "worker" in levels:
        worker, where = levels["worker"], f"{WHERE_LEVELS}.worker"
        if not isinstance(worker, dict):
            err("bad-type", where, '"worker" must map role names to model choices')
        else:
            for role in model.REQUIRED_WORKER_ROLES:
                if role not in worker:
                    err("missing-field", where, f'missing the "{role}" role')
            for role, tier in worker.items():
                if not model.ROLE_KEY.match(str(role)):
                    err("bad-type", f"{where}.{role}", "role names are lowercase words joined by underscores")
                    continue
                _check_tier(tier, f"{where}.{role}", err)
    cap = levels.get("parallel_epics")
    if "parallel_epics" in levels and (isinstance(cap, bool) or not isinstance(cap, int) or cap < 1):
        err("bad-type", f"{WHERE_LEVELS}.parallel_epics", '"parallel_epics" must be a whole number, 1 or more')
    for field in ("answered_by", "answered_on"):
        if field in levels and not _nonblank(levels[field]):
            err("bad-type", f"{WHERE_LEVELS}.{field}", f'"{field}" must be nonblank text')



def _cycles(items: dict) -> list[list[str]]:
    """Each dependency loop once, as a path that ends where it started.

    Iterative, so a chain of thousands of issues cannot overflow the stack.
    """
    found, seen_sets = [], set()
    state: dict[str, int] = {}
    for root in items:
        if state.get(root):
            continue
        state[root] = 1
        path = [root]
        stack = [iter(items[root]["depends_on"])]
        while stack:
            for d in stack[-1]:
                if d not in items:
                    continue
                if state.get(d) == 1:
                    loop = path[path.index(d):] + [d]
                    key = frozenset(loop)
                    if key not in seen_sets:
                        seen_sets.add(key)
                        found.append(loop)
                elif state.get(d) is None:
                    state[d] = 1
                    path.append(d)
                    stack.append(iter(items[d]["depends_on"]))
                    break
            else:
                state[path.pop()] = 2
                stack.pop()
    return found


def _strings(data: dict):
    """Every reader-facing text field with a readable location."""
    for key in ("title", "goal", "rule", "version"):
        if isinstance(data.get(key), str):
            yield key, data[key]
    for letter, text in data.get("gates", {}).items():
        if isinstance(text, str):
            yield f"gates.{letter}", text
    for ep in data["epics"]:
        for key in ("name", "note"):
            if isinstance(ep.get(key), str):
                yield f"epics[{ep.get('id')}].{key}", ep[key]
    for it in data["issues"]:
        for key in ("title", "detail"):
            if isinstance(it.get(key), str):
                yield f"issues[{it.get('id')}].{key}", it[key]


SINGLE_TOP = ("title", "version", "date", "agreed_by", "page_url")
MULTI_TOP = ("goal", "rule")


def _text_fields(data: dict):
    """Every string the tool may write, as (where, text, may span lines)."""
    for key in SINGLE_TOP + MULTI_TOP:
        if isinstance(data.get(key), str):
            yield key, data[key], key in MULTI_TOP
    for letter, text in (data.get("gates") or {}).items():
        if isinstance(text, str):
            yield f"gates.{letter}", text, False
    for ep in data.get("epics", []):
        if not isinstance(ep, dict):
            continue
        for key, value in ep.items():
            if isinstance(value, str):
                yield f"epics[{ep.get('id')}].{key}", value, key == "note"
    for it in data.get("issues", []):
        if not isinstance(it, dict):
            continue
        for key, value in it.items():
            if isinstance(value, str):
                yield f"issues[{it.get('id')}].{key}", value, key == "detail"
        for n, lk in enumerate(it.get("links") or []):
            for key, value in (lk.items() if isinstance(lk, dict) else [("url", lk)]):
                if isinstance(value, str):
                    yield f"issues[{it.get('id')}].links[{n}].{key}", value, False


def _timeline_text_fields(events, err):
    """Check event shapes at their original paths and yield the valid text fields."""
    if not isinstance(events, list):
        err("bad-type", "timeline", '"timeline" must be a list of events')
        return
    active = set()
    pending = [(f"timeline[{n}]", event) for n, event in reversed(list(enumerate(events)))]
    while pending:
        where, event = pending.pop()
        if where is None:
            active.remove(id(event))
            continue
        if not isinstance(event, dict) or id(event) in active:
            err("bad-type", where, "each timeline event must be a non-circular object")
            continue
        for field in ("date", "text", "title", "author", "id"):
            path = f"{where}.{field}"
            if field not in event:
                if field in ("date", "text"):
                    err("missing-field", path, f'missing required field "{field}"')
                continue
            value = event[field]
            if not isinstance(value, str):
                err("bad-type", path, f'"{field}" must be text')
                continue
            if field == "author" and (not value.strip(" ") or BAD_AUTHOR_CHAR.search(value)):
                err("bad-type", path, '"author" must be non-blank printable ASCII text without uppercase letters')
            if field in ("text", "title"):
                yield path, value, field == "text"
        if "provenance" in event and not isinstance(event["provenance"], dict):
            err("bad-type", f"{where}.provenance", '"provenance" must be an object')
        if "children" in event:
            children = event["children"]
            if not isinstance(children, list):
                err("bad-type", f"{where}.children", '"children" must be a list of events')
                continue
            active.add(id(event))
            pending.append((None, event))
            pending.extend(
                (f"{where}.children[{n}]", child)
                for n, child in reversed(list(enumerate(children)))
            )


def _all_strings(value, where: str):
    active = set()
    pending = [(where, value)]
    while pending:
        path, value = pending.pop()
        if path is None:
            active.remove(id(value))
        elif isinstance(value, str):
            yield path, value
        elif isinstance(value, (dict, list)) and id(value) not in active:
            active.add(id(value))
            pending.append((None, value))
            if isinstance(value, dict):
                pending.extend((f"{path}.{key}", value[key]) for key in reversed(value))
            else:
                pending.extend((f"{path}[{n}]", value[n]) for n in reversed(range(len(value))))


def _url_fields(data: dict):
    """Every field that becomes a live link, as (where, value)."""
    if data.get("page_url") is not None:
        yield "page_url", data["page_url"]
    for ep in data.get("epics", []):
        if isinstance(ep, dict) and ep.get("url") is not None:
            yield f"epics[{ep.get('id')}].url", ep["url"]
    for it in data.get("issues", []):
        if not isinstance(it, dict):
            continue
        where = f"issues[{it.get('id')}]"
        if it.get("url") is not None:
            yield f"{where}.url", it["url"]
        for n, lk in enumerate(it.get("links") or []):
            if isinstance(lk, dict):
                yield f"{where}.links[{n}].url", lk.get("url")
            else:
                yield f"{where}.links[{n}]", lk
        for g in it.get("gates") or []:
            if isinstance(g, dict) and g.get("evidence") is not None:
                yield f"{where}.gates[{g.get('gate')}].evidence", g["evidence"]
        for n, mr in enumerate(it.get("merge_requests") or []):
            if not isinstance(mr, dict):
                continue
            for key in ("url", "pipeline_url"):
                if mr.get(key) is not None:
                    yield f"{where}.merge_requests[{n}].{key}", mr[key]


def _codes(text: str, allowed: set[str]) -> list[str]:
    """Work codes in the text (A1, T1.1, TE4), leaving out technical words such as S3 or HTTP2."""
    return [m.group(0) for m in CODE.finditer(text) if m.group(0).casefold() not in allowed]


def _well_typed(raw: dict, err) -> dict:
    """A copy with wrongly typed entries reported and dropped, so the other checks cannot crash."""
    raw = dict(raw)
    if "iterations" in raw:
        iterations = raw["iterations"]
        if not isinstance(iterations, list):
            err("bad-type", "iterations", '"iterations" must be a list of objects with a "name"')
            iterations = []
        kept = []
        for n, x in enumerate(iterations):
            where = f"iterations[{n}]"
            if not isinstance(x, dict):
                err("bad-type", where, 'each entry in "iterations" must be an object')
                continue
            x = dict(x)
            for field in ("name", "start", "end"):
                if x.get(field) is not None and not isinstance(x[field], str):
                    err("bad-type", f"{where}.{field}", f'"{field}" must be text')
                    x.pop(field)
            kept.append(x)
        raw["iterations"] = kept
    if "allowed_terms" in raw and not (isinstance(raw["allowed_terms"], list)
                                       and all(isinstance(t, str) for t in raw["allowed_terms"])):
        err("bad-type", "allowed_terms", '"allowed_terms" must be a list of words (text), such as ["GP3"]')
        terms = raw["allowed_terms"]
        raw["allowed_terms"] = [t for t in terms if isinstance(t, str)] if isinstance(terms, list) else []
    if "orca" in raw and raw["orca"] is not None:
        if not isinstance(raw["orca"], dict):
            err("bad-type", "orca", '"orca" must be an object such as {"run": "<run id>"}')
            raw.pop("orca")
        elif raw["orca"].get("run") is not None and not isinstance(raw["orca"]["run"], str):
            err("bad-type", "orca.run", '"run" must be text: the Orca run id')
            raw["orca"] = {k: v for k, v in raw["orca"].items() if k != "run"}
    if "forge" in raw and raw["forge"] is not None:
        if not isinstance(raw["forge"], dict):
            err("bad-type", "forge", '"forge" must be an object with a "kind", such as {"kind": "gitlab"}')
            raw.pop("forge")
        else:
            fg = dict(raw["forge"])
            for field in ("kind", "host", "project", "group"):
                if fg.get(field) is not None and not isinstance(fg[field], str):
                    err("bad-type", f"forge.{field}", f'"{field}" must be text')
                    fg.pop(field)
            projects = fg.get("projects")
            if projects is not None and not (isinstance(projects, list) and all(isinstance(p, str) for p in projects)):
                err("bad-type", "forge.projects", '"projects" must be a list of projects, such as ["group/web"]')
                fg.pop("projects")
            labels = fg.get("status_labels")
            if labels is not None and not (isinstance(labels, dict) and all(isinstance(v, str) for v in labels.values())):
                err("bad-type", "forge.status_labels", '"status_labels" must map a status to a label name (text)')
                fg.pop("status_labels")
            raw["forge"] = fg
    for key in ("epics", "issues"):
        kept = []
        for n, x in enumerate(raw.get(key) or []):
            if not isinstance(x, dict):
                err("bad-type", f"{key}[{n}]", f"each entry in \"{key}\" must be an object")
                continue
            x = dict(x)
            label = x.get("id") if isinstance(x.get("id"), str) else f"#{n}"
            where = f"{key}[{label}]"
            text_fields = ("id", "name", "note", "parent", "ref", "url") if key == "epics" else \
                ("id", "title", "detail", "epic", "status", "ref", "url", "project", "iteration")
            for field in text_fields:
                if field in x and x[field] is not None and not isinstance(x[field], str):
                    err("bad-type", f"{where}.{field}", f'"{field}" must be text')
                    x[field] = None if field in ("id", "title", "name", "epic", "status") else str(x[field])
            if key == "issues":
                deps = x.get("depends_on", [])
                if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
                    err("bad-type", f"{where}.depends_on", '"depends_on" must be a list of issue ids')
                    x["depends_on"] = [d for d in deps if isinstance(d, str)] if isinstance(deps, list) else []
                days = x.get("estimate_days")
                if days is not None and (isinstance(days, bool) or not isinstance(days, (int, float))):
                    err("bad-type", f"{where}.estimate_days", '"estimate_days" must be a number of working days')
                    x.pop("estimate_days")
                gates = x.get("gates", [])
                ok = []
                for g in gates if isinstance(gates, list) else []:
                    letter = g if isinstance(g, str) else g.get("gate") if isinstance(g, dict) else None
                    if isinstance(letter, str) and GATE_LETTER.match(letter):
                        if isinstance(g, dict):
                            for field in ("approved_on", "evidence"):
                                if g.get(field) is not None and not isinstance(g[field], str):
                                    err("bad-type", f"{where}.gates[{letter}].{field}", f'"{field}" must be text')
                        ok.append(g)
                    else:
                        err("bad-type", f"{where}.gates", "each gate is a capital letter or "
                            '{"gate": letter, "passed": true or false}')
                if not isinstance(gates, list):
                    err("bad-type", f"{where}.gates", '"gates" must be a list')
                x["gates"] = ok
                for field in ("links", "merge_requests"):
                    if field in x and not isinstance(x[field], list):
                        err("bad-type", f"{where}.{field}", f'"{field}" must be a list')
                        x[field] = []
                if any(not isinstance(m, dict) for m in x.get("merge_requests") or []):
                    err("bad-type", f"{where}.merge_requests", 'each entry in "merge_requests" must be an object')
                    x["merge_requests"] = [m for m in x["merge_requests"] if isinstance(m, dict)]
            kept.append(x)
        if key in raw:
            raw[key] = kept
    return raw
