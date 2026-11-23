import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import hunt_lib as lib  # noqa: E402
import plan_lib as plan  # noqa: E402
from helpers import (PLAN_STAGES, make_build, make_critic, make_design, make_money,  # noqa: E402
                     make_product, make_profile, make_ranked_item, make_roadmap, make_run_entry,
                     make_sales)


class ParsePlanArgsTest(unittest.TestCase):
    def test_empty_means_pick(self):
        self.assertEqual(plan.parse_plan_args(""),
                         {"rank": None, "idea_id": None, "notes": None, "fresh": False})

    def test_rank_forms(self):
        for raw in ("1", "#1", "[1]", "1.", " 1 "):
            self.assertEqual(plan.parse_plan_args(raw)["rank"], 1, raw)

    def test_id_notes_and_fresh(self):
        args = plan.parse_plan_args("offline-tickets web only, don't build an app --fresh")
        self.assertEqual(args, {"rank": None, "idea_id": "offline-tickets",
                                "notes": "web only, don't build an app", "fresh": True})

    def test_whole_text_in_brackets(self):
        args = plan.parse_plan_args("[2 start in one city]")
        self.assertEqual((args["rank"], args["notes"]), (2, "start in one city"))

    def test_unreadable_idea_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Which idea"):
            plan.parse_plan_args("Web_Only please")


class FindIdeaTest(unittest.TestCase):
    def runs(self):
        old = make_run_entry("2026-11-08", "2026-11-08T18:00:00",
                             ranked=[make_ranked_item("a-idea", 1), make_ranked_item("b-idea", 2, top=False)])
        new = make_run_entry("2026-11-23", "2026-11-23T14:00:00",
                             ranked=[make_ranked_item("c-idea", 1)],
                             excluded=[{"id": "a-idea", "title": "A", "why": "Killed by the skeptic"}])
        unfinished = make_run_entry("2026-11-24", None, ranked=[make_ranked_item("d-idea", 1)])
        return [old, unfinished, new]

    def test_rank_uses_latest_finished_run(self):
        found = plan.find_idea(self.runs(), rank=1)
        self.assertEqual((found["run"]["run_id"], found["item"]["id"]), ("2026-11-23", "c-idea"))

    def test_id_found_in_older_run(self):
        self.assertEqual(plan.find_idea(self.runs(), idea_id="b-idea")["run"]["run_id"], "2026-11-08")

    def test_idea_cut_by_newer_run_is_refused(self):
        with self.assertRaisesRegex(LookupError, "2026-11-23.*Killed by the skeptic"):
            plan.find_idea(self.runs(), idea_id="a-idea")

    def test_unknown_rank_and_id(self):
        with self.assertRaisesRegex(LookupError, "#7"):
            plan.find_idea(self.runs(), rank=7)
        with self.assertRaisesRegex(LookupError, "nope"):
            plan.find_idea(self.runs(), idea_id="nope")

    def test_no_finished_run(self):
        with self.assertRaisesRegex(LookupError, "/hunt"):
            plan.find_idea([], rank=1)

    def test_top_ideas_lists_latest_top(self):
        top = plan.top_ideas(self.runs())
        self.assertEqual((top["run_id"], [i["id"] for i in top["ideas"]]), ("2026-11-23", ["c-idea"]))
        self.assertIsNone(plan.top_ideas([]))


class PreviousPlanAndPdfNameTest(unittest.TestCase):
    def test_previous_plan_is_newest_finished_for_same_idea(self):
        plans = [{"plan_id": "p1", "idea_id": "a", "finished_at": "2026-11-23T10:00:00"},
                 {"plan_id": "p2", "idea_id": "a", "finished_at": "2026-11-24T10:00:00"},
                 {"plan_id": "p3", "idea_id": "a"},
                 {"plan_id": "p4", "idea_id": "b", "finished_at": "2026-11-25T10:00:00"}]
        self.assertEqual(plan.previous_plan(plans, "a")["plan_id"], "p2")
        self.assertIsNone(plan.previous_plan(plans, "zzz"))

    def test_pdf_name(self):
        name = plan.pdf_name("2026-11-24", "Fee ledger: <b>managers</b> управители", set())
        self.assertEqual(name, "2026-11-24 Launch Plan - Fee ledger bmanagersb управители.pdf")
        self.assertEqual(plan.pdf_name("2026-11-24", "X", {"2026-11-24 Launch Plan - X.pdf"}),
                         "2026-11-24 Launch Plan - X (2).pdf")


class ValidateProfileTest(unittest.TestCase):
    def test_valid_profile(self):
        self.assertEqual(plan.validate_profile(make_profile()), [])

    def test_missing_answer_and_number_are_reported(self):
        doc = make_profile()
        del doc["goal"]
        doc["hours_per_week"] = 10
        errors = "\n".join(plan.validate_profile(doc))
        self.assertIn("goal", errors)
        self.assertIn("hours_per_week", errors)

    def test_extra_is_optional(self):
        doc = make_profile()
        doc["extra"] = None
        self.assertEqual(plan.validate_profile(doc), [])

    def test_six_questions_in_order(self):
        self.assertEqual([field for field, _ in plan.PROFILE_QUESTIONS],
                         ["builder", "hours_per_week", "budget_six_months", "country", "languages", "goal"])


class ValidateProductTest(unittest.TestCase):
    def test_valid_product(self):
        doc = make_product()
        self.assertEqual(plan.validate_product(doc, "offline-tickets"), [])
        self.assertEqual(plan.stage_ids(doc), PLAN_STAGES)

    def test_first_stage_must_not_build_software(self):
        doc = make_product()
        doc["stages"][0]["needs_software"] = True
        self.assertRegex("\n".join(plan.validate_product(doc, "offline-tickets")), "prove demand")

    def test_stage_count_ids_and_booleans(self):
        doc = make_product(stages=["a", "b"])
        self.assertTrue(plan.validate_product(doc, "offline-tickets"))
        doc = make_product()
        doc["stages"][1]["id"] = doc["stages"][0]["id"]
        self.assertRegex("\n".join(plan.validate_product(doc, "offline-tickets")), "duplicate")
        doc = make_product()
        doc["stages"][1]["needs_software"] = "yes"
        self.assertTrue(plan.validate_product(doc, "offline-tickets"))

    def test_wrong_id_and_missing_not_checked(self):
        doc = make_product()
        del doc["not_checked"]
        errors = "\n".join(plan.validate_product(doc, "other-idea"))
        self.assertIn("other-idea", errors)
        self.assertIn("not_checked", errors)


class ValidatePartsTest(unittest.TestCase):
    MAKERS = {"design": make_design, "build": make_build, "sales": make_sales, "money": make_money}

    def test_valid_parts(self):
        for name, maker in self.MAKERS.items():
            self.assertEqual(plan.PART_VALIDATORS[name](maker(), "offline-tickets", PLAN_STAGES), [], name)

    def test_unknown_stage_is_reported(self):
        for name, maker in self.MAKERS.items():
            errors = plan.PART_VALIDATORS[name](maker(), "offline-tickets", ["only-this"])
            self.assertTrue(errors, name)

    def test_per_stage_must_cover_every_stage_in_order(self):
        for name in ("build", "sales", "money"):
            doc = self.MAKERS[name]()
            doc["per_stage"].pop()
            self.assertRegex("\n".join(plan.PART_VALIDATORS[name](doc, "offline-tickets", PLAN_STAGES)),
                             "per_stage", name)

    def test_design_rules(self):
        doc = make_design()
        doc["look"]["colors"][0]["hex"] = "blue"
        doc["screens"][0]["kind"] = "tablet"
        errors = "\n".join(plan.validate_design(doc, "offline-tickets", PLAN_STAGES))
        self.assertIn("hex", errors)
        self.assertIn("kind", errors)
        doc = make_design()
        doc["screens"] = doc["screens"][:3]
        self.assertTrue(plan.validate_design(doc, "offline-tickets", PLAN_STAGES))

    def test_sales_needs_support_and_keeping_customers(self):
        doc = make_sales()
        del doc["support"]
        doc["keeping_customers"] = doc["keeping_customers"][:1]
        errors = "\n".join(plan.validate_sales(doc, "offline-tickets", PLAN_STAGES))
        self.assertIn("support", errors)
        self.assertIn("keeping_customers", errors)

    def test_money_rules(self):
        doc = make_money()
        doc["budget_check"]["fits"] = "yes"
        doc["legal"] = doc["legal"][:2]
        errors = "\n".join(plan.validate_money(doc, "offline-tickets", PLAN_STAGES))
        self.assertIn("fits", errors)
        self.assertIn("legal", errors)

    def test_unsafe_source_link_is_reported(self):
        doc = make_build()
        doc["sources"] = [{"title": "x", "url": "javascript:alert(1)"}]
        self.assertTrue(plan.validate_build(doc, "offline-tickets", PLAN_STAGES))

    def test_wrong_shapes_give_errors_not_crashes(self):
        for bad in (None, [], "text", 7, {"stages": "x", "screens": [1, "a"], "per_stage": {"a": 1},
                                          "look": [], "budget_check": 3, "tools": [None]}):
            self.assertTrue(plan.validate_profile(bad))
            self.assertTrue(plan.validate_product(bad, "offline-tickets"))
            self.assertEqual(plan.stage_ids(bad), [])
            for name, validator in plan.PART_VALIDATORS.items():
                self.assertTrue(validator(bad, "offline-tickets", PLAN_STAGES), name)


class ValidateCriticTest(unittest.TestCase):
    def test_valid_critic(self):
        self.assertEqual(plan.validate_critic(make_critic(), "offline-tickets"), [])

    def test_product_cannot_be_sent_back_for_fixes(self):
        doc = make_critic()
        doc["problems"][1]["fix_in"] = ["product"]
        self.assertRegex("\n".join(plan.validate_critic(doc, "offline-tickets")), "fix_in")

    def test_bad_verdict_ids_and_parts(self):
        doc = make_critic(verdict="fine")
        doc["problems"][1]["id"] = "c1"
        doc["problems"][0]["parts"] = ["marketing"]
        errors = "\n".join(plan.validate_critic(doc, "offline-tickets"))
        for word in ("verdict", "duplicate", "marketing"):
            self.assertIn(word, errors)

    def test_no_problems_is_fine(self):
        self.assertEqual(plan.validate_critic(make_critic(verdict="holds", problems=[]), "offline-tickets"), [])


class ValidateRoadmapTest(unittest.TestCase):
    def check(self, doc, **kw):
        return "\n".join(plan.validate_roadmap(doc, "offline-tickets", PLAN_STAGES, **kw))

    def test_valid_roadmap(self):
        self.assertEqual(self.check(make_roadmap(), critic=make_critic(), money=make_money()), "")

    def test_every_critic_problem_must_be_resolved(self):
        self.assertIn("c2", self.check(make_roadmap(resolved=("c1",)), critic=make_critic()))
        self.assertEqual(self.check(make_roadmap(resolved=())), "")  # no valid critic: nothing to cover

    def test_stages_must_match_product(self):
        doc = make_roadmap()
        doc["stages"].reverse()
        self.assertIn("stages", self.check(doc))

    def test_stop_has_no_roadmap_and_says_what_would_change_it(self):
        self.assertEqual(self.check(make_roadmap(verdict="stop")), "")
        doc = make_roadmap(verdict="stop")
        doc["this_week"] = ["Call three managers"]
        self.assertIn("this_week", self.check(doc))
        doc = make_roadmap(verdict="stop")
        doc["what_would_change_this"] = []
        self.assertIn("what_would_change_this", self.check(doc))

    def test_start_is_blocked_by_broken_critic_or_budget(self):
        doc = make_roadmap(verdict="start")
        self.assertIn("broken", self.check(doc, critic=make_critic(verdict="broken")))
        money = make_money()
        money["budget_check"]["fits"] = False
        self.assertIn("budget", self.check(doc, money=money))
        self.assertEqual(self.check(make_roadmap(verdict="caution"), critic=make_critic(verdict="broken")), "")

    def test_wrong_shapes_give_errors_not_crashes(self):
        for bad in (None, [], "x", {"stages": "x", "resolved": [1], "decisions_for_you": {"q": 1}, "problems": "x"}):
            self.assertTrue(plan.validate_roadmap(bad, "offline-tickets", PLAN_STAGES, critic=make_critic()))
            self.assertTrue(plan.validate_critic(bad, "offline-tickets"))
            self.assertEqual(plan.critic_fixes(bad), {})


class CriticFixesTest(unittest.TestCase):
    def test_lines_grouped_by_part(self):
        fixes = plan.critic_fixes(make_critic())
        self.assertEqual(list(fixes), ["build"])
        self.assertRegex(fixes["build"][0], r"^c1: .+ Fix: .+")

    def test_left_out_parts_are_skipped(self):
        self.assertEqual(plan.critic_fixes(make_critic(), available=["design", "sales"]), {})


if __name__ == "__main__":
    unittest.main()
