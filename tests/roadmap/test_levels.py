"""orchestration.levels: the model, effort and parallel cap the lead chose at kickoff."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy

from helpers import SCHEMA, example
from roadmaplib import model, validate

WHERE = "orchestration.levels"


def recorded_levels() -> dict:
    return deepcopy(example()["orchestration"]["levels"])


def with_levels(value) -> dict:
    data = example()
    data["orchestration"]["levels"] = value
    return data


def error_keys(data: dict) -> set[tuple[str, str]]:
    return {(f.code, f.where) for f in validate.errors(validate.check(data))}


class LevelsSchema(unittest.TestCase):
    def test_schema_documents_the_fields_validate_checks(self):
        schema = json.loads(SCHEMA.read_text())
        ref = schema["properties"]["orchestration"]["properties"]["levels"]["$ref"]
        levels = schema["$defs"][ref.rsplit("/", 1)[-1]]
        self.assertEqual(set(levels["properties"]), set(model.LEVEL_FIELDS))
        self.assertEqual(set(levels["required"]), set(model.REQUIRED_LEVEL_FIELDS))
        self.assertIs(levels["additionalProperties"], False)
        cap = levels["properties"]["parallel_epics"]
        self.assertEqual((cap["type"], cap["minimum"]), ("integer", 1))
        worker = levels["properties"]["worker"]
        self.assertEqual(set(worker["required"]), set(model.REQUIRED_WORKER_ROLES))
        self.assertEqual(worker["propertyNames"]["pattern"], model.ROLE_KEY.pattern)
        tier = schema["$defs"]["tier"]
        self.assertEqual(set(tier["properties"]), set(model.TIER_FIELDS))
        self.assertEqual(tier["required"], ["model"])
        self.assertIs(tier["additionalProperties"], False)

    def test_example_records_every_level_and_the_default_cap(self):
        levels = recorded_levels()
        for level in model.LEVELS:
            self.assertIn("model", levels[level] if level != "worker" else levels[level]["implementer"])
        self.assertEqual(set(levels["worker"]), set(model.WORKER_ROLES))
        self.assertEqual(levels["parallel_epics"], model.DEFAULT_PARALLEL_EPICS)
        self.assertEqual(model.DEFAULT_PARALLEL_EPICS, 2)
        self.assertFalse(validate.errors(validate.check(example())))

    def test_roadmap_without_levels_stays_valid(self):
        data = example()
        del data["orchestration"]
        self.assertFalse(validate.errors(validate.check(data)))


class LevelsAccepted(unittest.TestCase):
    def test_named_exceptions_and_optional_fields_are_accepted(self):
        levels = recorded_levels()
        levels["worker"]["security_reviewer"] = {"model": "most-capable", "note": "auth and secrets changes"}
        levels["epic"] = {"model": "mid-tier", "agent": "codex"}
        levels["parallel_epics"] = 3
        levels["answered_by"] = "Program lead"
        levels["answered_on"] = "2026-11-20"
        self.assertEqual(error_keys(with_levels(levels)), set())


class LevelsRejected(unittest.TestCase):
    def check_rejects(self, change, code, where):
        levels = recorded_levels()
        change(levels)
        got = error_keys(with_levels(levels))
        self.assertIn((code, where), got)

    def test_levels_must_be_an_object(self):
        self.assertIn(("bad-type", WHERE), error_keys(with_levels(["program", "epic"])))

    def test_every_level_and_the_cap_are_required(self):
        for key in model.REQUIRED_LEVEL_FIELDS:
            with self.subTest(missing=key):
                self.check_rejects(lambda lv, key=key: lv.pop(key), "missing-field", WHERE)

    def test_a_misspelled_level_is_reported(self):
        self.check_rejects(lambda lv: lv.update(progam={"model": "x"}), "unknown-field", f"{WHERE}.progam")

    def test_a_tier_needs_an_object_with_a_model(self):
        self.check_rejects(lambda lv: lv.update(program="most-capable"), "bad-type", f"{WHERE}.program")
        self.check_rejects(lambda lv: lv["program"].pop("model"), "missing-field", f"{WHERE}.program")
        self.check_rejects(lambda lv: lv["program"].update(model="  "), "bad-type", f"{WHERE}.program.model")

    def test_tier_text_fields_must_be_nonblank_text(self):
        for field in ("effort", "agent", "note"):
            with self.subTest(field=field):
                self.check_rejects(lambda lv, field=field: lv["epic"].update({field: 3}), "bad-type",
                                   f"{WHERE}.epic.{field}")

    def test_a_misspelled_tier_field_is_reported(self):
        self.check_rejects(lambda lv: lv["epic"].update(efort="high"), "unknown-field", f"{WHERE}.epic.efort")

    def test_worker_roles_need_an_implementer_and_a_reviewer(self):
        for role in model.REQUIRED_WORKER_ROLES:
            with self.subTest(missing=role):
                self.check_rejects(lambda lv, role=role: lv["worker"].pop(role), "missing-field", f"{WHERE}.worker")

    def test_worker_must_map_role_names_to_tiers(self):
        self.check_rejects(lambda lv: lv.update(worker=["implementer"]), "bad-type", f"{WHERE}.worker")
        self.check_rejects(lambda lv: lv["worker"].update({"Final Reviewer": {"model": "x"}}), "bad-type",
                           f"{WHERE}.worker.Final Reviewer")
        self.check_rejects(lambda lv: lv["worker"].update(mechanical={"effort": "low"}), "missing-field",
                           f"{WHERE}.worker.mechanical")
        self.check_rejects(lambda lv: lv["worker"].update({"tester\n": {"model": "x"}}), "bad-type",
                           f"{WHERE}.worker.tester\n")

    def test_parallel_epics_is_a_positive_whole_number(self):
        for bad in (0, -1, 1.5, "2", True, None):
            with self.subTest(parallel_epics=bad):
                self.check_rejects(lambda lv, bad=bad: lv.update(parallel_epics=bad), "bad-type",
                                   f"{WHERE}.parallel_epics")

    def test_who_answered_and_when_are_nonblank_text(self):
        for field in ("answered_by", "answered_on"):
            with self.subTest(field=field):
                self.check_rejects(lambda lv, field=field: lv.update({field: ""}), "bad-type", f"{WHERE}.{field}")


if __name__ == "__main__":
    unittest.main()
