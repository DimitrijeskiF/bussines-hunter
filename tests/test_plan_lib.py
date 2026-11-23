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
from helpers import make_ranked_item, make_run_entry  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
