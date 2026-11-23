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
import plan_report as report_lib  # noqa: E402
from helpers import (PLAN_STAGES, make_build, make_critic, make_deepdive, make_design,  # noqa: E402
                     make_money, make_product, make_profile, make_ranked_item, make_roadmap,
                     make_run_entry, make_sales)


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


class RenderPlanTest(unittest.TestCase):
    def report(self, **overrides):
        report = {"plan_id": "2026-11-24-offline-tickets", "date_label": "24 November 2026",
                  "title": "<script>alert(1)</script> Offline tickets", "one_liner": "Tickets without data.",
                  "source_run": "2026-11-23", "previous": None, "notes": None, "founder": make_profile(),
                  "product": make_product(), "design": make_design(), "build": make_build(),
                  "sales": make_sales(), "money": make_money(), "critic": make_critic(),
                  "roadmap": make_roadmap(), "left_out": [], "kept_earlier": []}
        report.update(overrides)
        return report

    def test_has_every_section_in_order(self):
        html = report_lib.render_plan_html(self.report())
        positions = [html.index(f">{name}<") for name in (
            "Summary", "Roadmap", "Decisions for you", "Product", "Design", "Build", "Sales",
            "Money and legal", "What the critic found", "Your profile and sources")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Start, with caution", html)
        self.assertIn("Confirm legal and tax points with a local professional", html)

    def test_escapes_agent_text_and_unsafe_links(self):
        build = make_build()
        build["sources"] = [{"title": "Bad", "url": "javascript:alert(1)"}]
        html = report_lib.render_plan_html(self.report(build=build))
        self.assertNotIn("<script>", html)
        self.assertNotIn('href="javascript:', html)

    def test_stop_verdict_has_no_roadmap_or_checklist(self):
        html = report_lib.render_plan_html(self.report(roadmap=make_roadmap(verdict="stop")))
        self.assertIn("Do not start", html)
        self.assertIn("What would change this", html)
        self.assertNotIn(">Roadmap<", html)
        self.assertNotIn('class="checklist"', html)
        self.assertIn("What the planners worked out, for reference", html)

    def test_missing_roadmap_shows_no_verdict(self):
        html = report_lib.render_plan_html(self.report(roadmap=None, left_out=["roadmap"]))
        self.assertIn("No verdict: the plan lead did not finish", html)
        self.assertIn("The critic's verdict", html)
        self.assertNotIn(">Roadmap<", html)
        self.assertNotIn(">Summary<", html)

    def test_missing_parts_do_not_crash_and_are_named(self):
        html = report_lib.render_plan_html(self.report(
            design=None, money=None, critic=None, roadmap=None, left_out=["design", "money", "critic", "roadmap"]))
        self.assertIn("Left out of this plan", html)
        self.assertIn("Money and legal", html)

    def test_lean_documents_do_not_crash(self):
        lean = {"id": "offline-tickets", "not_checked": []}
        html = report_lib.render_plan_html(self.report(
            product=lean, design=lean, build=lean, sales=lean, money=lean, critic=lean, roadmap=lean))
        self.assertIn("Launch Plan", html)

    def test_not_checked_is_printed_and_summarised(self):
        sales = make_sales()
        sales["not_checked"] = ["Prices of two rivals"]
        html = report_lib.render_plan_html(self.report(sales=sales))
        self.assertIn("Some points could not be checked in: Sales", html)
        self.assertIn("Prices of two rivals", html)

    def test_kept_earlier_and_previous_plan_are_mentioned(self):
        html = report_lib.render_plan_html(self.report(
            kept_earlier=["build"], previous={"plan_id": "2026-11-23-offline-tickets", "date_label": "23 November 2026"}))
        self.assertIn("Kept from before the critic", html)
        self.assertIn("23 November 2026", html)

    def test_screens_swatches_and_stage_names(self):
        html = report_lib.render_plan_html(self.report())
        self.assertIn('class="screen phone"', html)
        self.assertIn('class="screen wide"', html)
        self.assertIn('class="swatch"', html)
        self.assertIn("Stage 1: prove-demand", html)

    def test_bad_hex_is_not_put_into_a_style(self):
        design = make_design()
        design["look"]["colors"][0]["hex"] = "red;background:url(x)"
        html = report_lib.render_plan_html(self.report(design=design))
        self.assertNotIn("url(x)\"", html)
        self.assertEqual(html.count('class="swatch"'), 1)


@unittest.skipUnless(lib.find_browser(), "no Chrome-based browser installed")
class PlanCliEndToEndTest(unittest.TestCase):
    """Runs the real plan CLI against a fake finished hunt (no agents), from start to PDF."""
    IDEA = "offline-tickets"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name) / "data"
        self.out = Path(tmp.name) / "Desktop"
        self.env = {**os.environ, "BH_DATA_DIR": str(self.data), "BH_OUTPUT_DIR": str(self.out)}
        run_dir = self.data / "runs" / "2026-11-23"
        self.write(run_dir / "run.json", {"run_id": "2026-11-23", "date": "2026-11-23",
                                          "finished_at": "2026-11-23T14:00:00"})
        self.write(run_dir / "ranked.json", {
            "ranked": [make_ranked_item(self.IDEA, 1),
                       make_ranked_item("study-buddy", 2, top=False, title="Study buddy")],
            "excluded": [{"id": "old-idea", "title": "Old idea", "why": "Killed by the skeptic"}]})
        self.write(run_dir / "deepdives" / f"{self.IDEA}.json", make_deepdive(self.IDEA))

    def write(self, path, doc):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc), encoding="utf-8")

    def read(self, path):
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "plan.py"), *args],
                              capture_output=True, text=True, env=self.env, cwd=ROOT)

    def ok(self, *args):
        out = self.cli(*args)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        return out.stdout

    def ready(self, raw="1"):
        self.write(self.data / "founder.json", make_profile())
        status = json.loads(self.ok("start", "--raw", raw))
        self.assertEqual(status["status"], "ready", status)
        return Path(status["plan_dir"]), status

    def write_parts(self, plan_dir, **docs):
        for name, doc in docs.items():
            target = plan_dir / f"{name}.json" if name in ("critic", "roadmap") else plan_dir / "parts" / f"{name}.json"
            self.write(target, doc)

    def test_start_statuses(self):
        status = json.loads(self.ok("start", "--raw", ""))
        self.assertEqual(status["status"], "pick_idea")
        self.assertEqual([i["id"] for i in status["ideas"]], [self.IDEA])

        status = json.loads(self.ok("start", "--raw", "1"))
        self.assertEqual(status["status"], "profile_missing")
        self.assertEqual(len(status["questions"]), 6)
        self.assertFalse((self.data / "plans").exists())

        self.write(self.data / "founder.json", make_profile())
        self.assertIn("OK profile", self.ok("validate-profile"))

        status = json.loads(self.ok("start", "--raw", "study-buddy"))
        self.assertEqual((status["status"], status["idea_id"]), ("needs_deepdive", "study-buddy"))

        out = self.cli("start", "--raw", "old-idea")
        self.assertEqual(out.returncode, 1)
        self.assertIn("Killed by the skeptic", out.stdout + out.stderr)
        self.assertFalse((self.data / "plans").exists())

        plan_dir, status = self.ready("[1] web only")
        self.assertIsNone(status["builds_on"])
        given = self.read(plan_dir / "input.json")
        self.assertEqual(given["notes"], "web only")
        self.assertIsNone(given["previous"])
        self.assertEqual(given["deepdive"]["id"], self.IDEA)
        self.assertEqual(given["founder"]["country"], "Kenya")
        self.assertEqual(given["idea"]["rank"], 1)

    def test_invalid_profile_is_reported(self):
        self.write(self.data / "founder.json", {"builder": "Me"})
        out = self.cli("validate-profile")
        self.assertEqual(out.returncode, 1)
        self.assertIn("goal", out.stdout)

    def test_full_plan_produces_pdf(self):
        plan_dir, _ = self.ready()
        self.assertEqual(self.cli("validate", "parts", str(plan_dir)).returncode, 1)  # no product yet
        self.write_parts(plan_dir, product=make_product())
        self.assertIn("OK product", self.ok("validate", "product", str(plan_dir)))

        self.write_parts(plan_dir, design=make_design(), sales=make_sales(), build={"id": self.IDEA})
        out = self.cli("validate", "parts", str(plan_dir))
        self.assertEqual(out.returncode, 1)
        self.assertIn("ERROR build", out.stdout)
        self.assertIn("SKIPPED build", self.ok("validate", "parts", str(plan_dir), "--skip-invalid"))

        self.write_parts(plan_dir, money=make_money(), critic=make_critic(), roadmap=make_roadmap())
        for stage in ("money", "critic", "roadmap"):
            self.assertIn(f"OK {stage}", self.ok("validate", stage, str(plan_dir)))

        fixes = json.loads(self.ok("fixes", str(plan_dir)))  # the critic names build, which was left out
        self.assertEqual(fixes, {"fixes": {}, "order": []})
        self.assertEqual(list((plan_dir / "parts").glob("*.before-fix.json")), [])

        result = json.loads(self.ok("finalize", str(plan_dir)))
        self.assertTrue(Path(result["pdf"]).read_bytes().startswith(b"%PDF"))
        self.assertEqual((result["verdict"], result["left_out"]), ("caution", ["build"]))
        self.assertEqual(len(result["stages"]), 3)
        self.assertEqual(len(result["this_week"]), 3)
        self.assertIn("Launch Plan - Offline bus tickets", Path(result["pdf"]).name)

        again = json.loads(self.ok("finalize", str(plan_dir)))
        self.assertEqual(again["pdf"], result["pdf"])
        self.assertEqual(len(list(self.out.glob("*.pdf"))), 1)

    def test_fix_round_keeps_earlier_version(self):
        plan_dir, _ = self.ready()
        critic = make_critic()
        critic["problems"][0]["fix_in"] = ["build", "money"]
        self.write_parts(plan_dir, product=make_product(), design=make_design(), build=make_build(),
                         sales=make_sales(), money=make_money(), critic=critic)
        fixes = json.loads(self.ok("fixes", str(plan_dir)))
        self.assertEqual(fixes["order"], [["build"], ["money"]])
        self.assertRegex(fixes["fixes"]["build"][0], "^c1: ")
        self.assertTrue((plan_dir / "parts" / "build.before-fix.json").exists())

        self.write_parts(plan_dir, build={"id": self.IDEA})  # the "fixed" version is broken
        self.assertEqual(self.cli("validate", "parts", str(plan_dir)).returncode, 1)
        self.assertIn("KEPT build", self.ok("validate", "parts", str(plan_dir), "--skip-invalid"))
        self.assertIn("OK build", self.ok("validate", "parts", str(plan_dir)))
        state = self.read(plan_dir / "plan.json")
        self.assertEqual((state["kept_earlier"], state["left_out"]), (["build"], []))

    def test_second_plan_builds_on_first_unless_fresh(self):
        first_dir, first = self.ready()
        self.write_parts(first_dir, product=make_product())
        first_pdf = json.loads(self.ok("finalize", str(first_dir)))["pdf"]

        second_dir, second = self.ready()
        self.assertTrue(second["plan_id"].endswith("-2"), second["plan_id"])
        self.assertEqual(second["builds_on"], first["plan_id"])
        previous = self.read(second_dir / "input.json")["previous"]
        self.assertEqual(previous["parts"]["product"]["id"], self.IDEA)
        self.assertIsNone(previous["roadmap"])
        self.write_parts(second_dir, product=make_product())
        second_pdf = json.loads(self.ok("finalize", str(second_dir)))["pdf"]
        self.assertNotEqual(second_pdf, first_pdf)
        self.assertTrue(second_pdf.endswith(" (2).pdf"), second_pdf)

        _, third = self.ready("1 --fresh")
        self.assertIsNone(third["builds_on"])

    def test_unfinished_plan_is_not_built_on(self):
        self.ready()  # started, never finalized
        _, second = self.ready()
        self.assertIsNone(second["builds_on"])

    def test_stop_plan_and_missing_roadmap(self):
        plan_dir, _ = self.ready()
        self.write_parts(plan_dir, product=make_product(), roadmap=make_roadmap(verdict="stop", resolved=()))
        self.assertIn("OK roadmap", self.ok("validate", "roadmap", str(plan_dir)))
        result = json.loads(self.ok("finalize", str(plan_dir)))
        self.assertEqual((result["verdict"], result["this_week"]), ("stop", []))

        plan_dir, _ = self.ready("1 --fresh")
        self.write_parts(plan_dir, product=make_product(), roadmap={"id": self.IDEA})
        self.assertEqual(self.cli("validate", "roadmap", str(plan_dir)).returncode, 1)
        self.assertIn("SKIPPED roadmap", self.ok("validate", "roadmap", str(plan_dir), "--skip-invalid"))
        result = json.loads(self.ok("finalize", str(plan_dir)))
        self.assertIsNone(result["verdict"])
        self.assertIn("roadmap", result["left_out"])

    def test_roadmap_start_blocked_by_budget(self):
        plan_dir, _ = self.ready()
        money = make_money()
        money["budget_check"]["fits"] = False
        self.write_parts(plan_dir, product=make_product(), money=money,
                         roadmap=make_roadmap(verdict="start", resolved=()))
        self.assertIn("OK money", self.ok("validate", "money", str(plan_dir)))
        out = self.cli("validate", "roadmap", str(plan_dir))
        self.assertEqual(out.returncode, 1)
        self.assertIn("budget", out.stdout)

    def test_not_a_plan_folder(self):
        out = self.cli("finalize", str(self.data))
        self.assertEqual(out.returncode, 1)
        self.assertIn("not a plan folder", out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
