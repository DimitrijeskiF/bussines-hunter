import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import hunt_lib as lib  # noqa: E402
from helpers import (REGIONS, make_card, make_cards_doc, make_cluster,  # noqa: E402
                     make_deepdive, make_rubric, make_score, make_verdict)


class NextRunIdTest(unittest.TestCase):
    def test_uses_date_when_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(lib.next_run_id(Path(tmp), "2026-11-07"), "2026-11-07")

    def test_adds_counter_when_date_taken(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "2026-11-07").mkdir()
            (Path(tmp) / "2026-11-07-2").mkdir()
            self.assertEqual(lib.next_run_id(Path(tmp), "2026-11-07"), "2026-11-07-3")


class ParseHuntArgsTest(unittest.TestCase):
    def test_empty_means_all_regions_full_run(self):
        args = lib.parse_hunt_args("", REGIONS)
        self.assertEqual(args, {"theme": None, "regions": REGIONS, "quick": False})

    def test_theme_regions_and_quick(self):
        args = lib.parse_hunt_args("study tools --regions europe,latin_america --quick", REGIONS)
        self.assertEqual(args["theme"], "study tools")
        self.assertEqual(args["regions"], ["europe", "latin_america"])
        self.assertTrue(args["quick"])

    def test_unknown_region_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "antarctica"):
            lib.parse_hunt_args("--regions antarctica", REGIONS)


class ValidateCardsTest(unittest.TestCase):
    def test_valid_doc_has_no_errors(self):
        self.assertEqual(lib.validate_cards(make_cards_doc(), "europe"), [])

    def test_missing_field_is_reported_with_path(self):
        doc = make_cards_doc()
        del doc["cards"][0]["problem"]
        errors = lib.validate_cards(doc, "europe")
        self.assertTrue(any("cards[0].problem" in e for e in errors), errors)

    def test_unsafe_evidence_url_is_rejected(self):
        doc = make_cards_doc()
        doc["cards"][0]["evidence"][0]["url"] = "javascript:alert(1)"
        self.assertTrue(lib.validate_cards(doc, "europe"))

    def test_wrong_region_is_rejected(self):
        self.assertTrue(lib.validate_cards(make_cards_doc("europe"), "africa"))

    def test_duplicate_card_ids_are_rejected(self):
        doc = make_cards_doc()
        doc["cards"][1]["id"] = doc["cards"][0]["id"]
        self.assertTrue(any("duplicate" in e for e in lib.validate_cards(doc, "europe")))

    def test_unknown_gap_type_is_rejected(self):
        doc = make_cards_doc()
        doc["cards"][0]["gap_type"] = "sort_of_missing"
        self.assertTrue(any("gap_type" in e for e in lib.validate_cards(doc, "europe")))

    def test_unknown_lens_is_rejected(self):
        doc = make_cards_doc()
        doc["cards"][0]["lens"] = ["vibes"]
        self.assertTrue(lib.validate_cards(doc, "europe"))


class ValidateClustersTest(unittest.TestCase):
    def setUp(self):
        self.card_ids = {"europe/eu-01", "latin_america/la-01"}

    def test_valid_doc_has_no_errors(self):
        doc = {"clusters": [make_cluster()]}
        self.assertEqual(lib.validate_clusters(doc, REGIONS, self.card_ids), [])

    def test_bad_slug_is_rejected(self):
        doc = {"clusters": [make_cluster(cluster_id="Not A Slug")]}
        self.assertTrue(lib.validate_clusters(doc, REGIONS, self.card_ids))

    def test_unknown_card_ref_is_rejected(self):
        doc = {"clusters": [make_cluster(refs=("europe/eu-99",))]}
        errors = lib.validate_clusters(doc, REGIONS, self.card_ids)
        self.assertTrue(any("eu-99" in e for e in errors), errors)

    def test_unknown_region_is_rejected(self):
        doc = {"clusters": [make_cluster(regions=("mars",))]}
        self.assertTrue(lib.validate_clusters(doc, REGIONS, self.card_ids))

    def test_too_many_clusters_is_rejected(self):
        doc = {"clusters": [make_cluster(cluster_id=f"idea-{i}") for i in range(3)]}
        self.assertTrue(lib.validate_clusters(doc, REGIONS, self.card_ids, max_clusters=2))

    def test_cluster_needs_gap_type(self):
        cluster = make_cluster()
        del cluster["gap_type"]
        self.assertTrue(lib.validate_clusters({"clusters": [cluster]}, REGIONS, self.card_ids))

    def test_arbitrage_needs_both_sides(self):
        doc = {"clusters": [make_cluster(arbitrage={"solved_in": [], "open_in": ["europe"], "note": "x"})]}
        self.assertTrue(lib.validate_clusters(doc, REGIONS, self.card_ids))


class ValidateReviewTest(unittest.TestCase):
    def test_scores_must_cover_every_cluster(self):
        errors = lib.validate_scores({"scores": [make_score("a")]}, {"a", "b"})
        self.assertTrue(any("b" in e for e in errors), errors)

    def test_score_out_of_range_is_rejected(self):
        doc = {"scores": [make_score("a", value=6)]}
        self.assertTrue(lib.validate_scores(doc, {"a"}))

    def test_rejected_idea_needs_no_checks(self):
        doc = {"scores": [make_score("a", rejected=True, reason="Sold to large companies")]}
        self.assertEqual(lib.validate_scores(doc, {"a"}), [])

    def test_unknown_verdict_is_rejected(self):
        doc = {"verdicts": [make_verdict("a", verdict="maybe")]}
        self.assertTrue(lib.validate_skeptic(doc, {"a"}))

    def test_big_tech_risk_is_required(self):
        verdict = make_verdict("a")
        del verdict["big_tech_risk"]
        self.assertTrue(lib.validate_skeptic({"verdicts": [verdict]}, {"a"}))

    def test_verdicts_must_cover_every_cluster(self):
        self.assertTrue(lib.validate_skeptic({"verdicts": [make_verdict("a")]}, {"a", "b"}))


class ValidateDeepdiveTest(unittest.TestCase):
    def test_valid_doc_has_no_errors(self):
        self.assertEqual(lib.validate_deepdive(make_deepdive(), "offline-tickets"), [])

    def test_id_must_match(self):
        self.assertTrue(lib.validate_deepdive(make_deepdive(), "other-idea"))

    def test_needs_at_least_five_first_user_places(self):
        self.assertTrue(lib.validate_deepdive(make_deepdive(places=3), "offline-tickets"))

    def test_needs_unit_economics(self):
        doc = make_deepdive()
        del doc["unit_economics"]
        self.assertTrue(any("unit_economics" in e for e in lib.validate_deepdive(doc, "offline-tickets")))


class RankingTest(unittest.TestCase):
    def test_multi_region_score_grows_with_regions(self):
        self.assertEqual([lib.multi_region_score(n) for n in (1, 2, 3, 5, 7)], [1, 2, 3, 4, 5])

    def test_all_fives_score_100_and_all_ones_score_0(self):
        six_regions = ("a", "b", "c", "d", "e", "f")
        clusters = [make_cluster("high", regions=six_regions), make_cluster("low")]
        scores = [make_score("high", 5), make_score("low", 1)]
        verdicts = [make_verdict("high"), make_verdict("low")]
        result = lib.rank_ideas(clusters, scores, verdicts, make_rubric())
        by_id = {item["id"]: item for item in result["ranked"]}
        # "high" is seen in 6 regions -> multi_region 5; "low" in 1 -> 1
        self.assertEqual(by_id["high"]["score"], 100.0)
        self.assertEqual(by_id["low"]["score"], 0.0)

    def test_rejected_and_killed_ideas_are_excluded(self):
        clusters = [make_cluster("keep"), make_cluster("rejected"), make_cluster("killed")]
        scores = [make_score("keep"), make_score("rejected", rejected=True, reason="Enterprise"), make_score("killed")]
        verdicts = [make_verdict("keep"), make_verdict("rejected"), make_verdict("killed", "killed")]
        result = lib.rank_ideas(clusters, scores, verdicts, make_rubric())
        self.assertEqual([item["id"] for item in result["ranked"]], ["keep"])
        excluded = {item["id"]: item["why"] for item in result["excluded"]}
        self.assertIn("Enterprise", excluded["rejected"])
        self.assertIn("skeptic", excluded["killed"].lower())

    def test_weakened_ideas_are_penalized(self):
        clusters = [make_cluster("strong"), make_cluster("weak")]
        scores = [make_score("strong", 4), make_score("weak", 4)]
        verdicts = [make_verdict("strong"), make_verdict("weak", "weakened")]
        result = lib.rank_ideas(clusters, scores, verdicts, make_rubric())
        ranked = result["ranked"]
        self.assertEqual(ranked[0]["id"], "strong")
        self.assertLess(ranked[1]["score"], ranked[0]["score"])
        self.assertEqual(result["weakened_penalty"], 0.85)

    def test_top_n_is_flagged_and_ranks_are_numbered(self):
        clusters = [make_cluster(f"idea-{i}") for i in range(3)]
        scores = [make_score(f"idea-{i}", 5 - i) for i in range(3)]
        verdicts = [make_verdict(f"idea-{i}") for i in range(3)]
        ranked = lib.rank_ideas(clusters, scores, verdicts, make_rubric(top_n=2))["ranked"]
        self.assertEqual([item["rank"] for item in ranked], [1, 2, 3])
        self.assertEqual([item["top"] for item in ranked], [True, True, False])

    def test_weights_change_the_ranking(self):
        clusters = [make_cluster("big"), make_cluster("cheap")]
        big = make_score("big", 3)
        big["checks"]["audience_size"]["score"] = 5
        cheap = make_score("cheap", 3)
        cheap["checks"]["cheap_to_run"]["score"] = 5
        verdicts = [make_verdict("big"), make_verdict("cheap")]
        even = lib.rank_ideas(clusters, [big, cheap], verdicts, make_rubric())
        weights = {**make_rubric()["weights"], "audience_size": 3.0}
        tilted = lib.rank_ideas(clusters, [big, cheap], verdicts, make_rubric(weights=weights))
        self.assertEqual(even["ranked"][0]["score"], even["ranked"][1]["score"])
        self.assertEqual(tilted["ranked"][0]["id"], "big")

    def test_missing_weight_is_rejected(self):
        weights = {k: 1.0 for k in lib.ALL_CHECKS if k != "cheap_reach"}
        with self.assertRaisesRegex(ValueError, "cheap_reach"):
            lib.rank_ideas([], [], [], make_rubric(weights=weights))


class IdeaDatabaseTest(unittest.TestCase):
    def ranked(self, *ids):
        return [{"id": i, "title": i.title(), "score": 80.0 - n, "rank": n + 1, "top": n < 2}
                for n, i in enumerate(ids)]

    def test_first_run_marks_everything_new(self):
        changes = lib.diff_against_db(self.ranked("a", "b"), lib.empty_db())
        self.assertTrue(changes["first_run"])
        self.assertEqual([item["id"] for item in changes["new"]], ["a", "b"])

    def test_detects_new_moved_and_dropped_ideas(self):
        db = lib.update_db(lib.empty_db(), self.ranked("a", "b", "c"), [], "2026-11-01")
        changes = lib.diff_against_db(self.ranked("b", "d", "a"), db)
        self.assertFalse(changes["first_run"])
        self.assertEqual([item["id"] for item in changes["new"]], ["d"])
        moved = {item["id"]: (item["from"], item["to"]) for item in changes["moved"]}
        self.assertEqual(moved, {"b": (2, 1), "a": (1, 3)})
        # "a" left the top 2; "b" stayed in it
        self.assertEqual([item["id"] for item in changes["dropped"]], ["a"])

    def test_update_keeps_first_seen_and_appends_history(self):
        db = lib.update_db(lib.empty_db(), self.ranked("a"), [], "2026-11-01")
        db = lib.update_db(db, self.ranked("a"), [{"id": "z", "title": "Z", "why": "killed"}], "2026-11-08")
        self.assertEqual(db["ideas"]["a"]["first_seen"], "2026-11-01")
        self.assertEqual(db["ideas"]["a"]["last_seen"], "2026-11-08")
        self.assertEqual(len(db["ideas"]["a"]["history"]), 2)
        self.assertEqual(db["ideas"]["z"]["history"][0]["status"], "excluded")
        self.assertEqual(db["runs"], ["2026-11-01", "2026-11-08"])


class RenderTest(unittest.TestCase):
    def report(self, **overrides):
        top = {"id": "offline-tickets", "title": "<script>alert(1)</script> Offline tickets", "score": 81.5,
               "rank": 1, "top": True, "regions": ["europe"], "gap_type": "missing_here",
               "patterns": {"global_pain": False, "arbitrage": None},
               "verdict": "survives", "checks": {}, "deepdive": make_deepdive()}
        report = {
            "run_id": "2026-11-07", "date_label": "7 November 2026", "theme": None,
            "quick": False, "stats": {"regions": 1, "cards": 2, "clusters": 1, "survivors": 1},
            "failed_regions": [], "top": [top], "others": [], "excluded": [],
            "changes": lib.diff_against_db([top], lib.empty_db()),
            "regions": [{"id": "europe", "name": "Europe", "summary": ["Mobile-first everywhere"], "card_count": 2}],
            "sources": [{"region": "Europe", "items": [
                {"title": "Good", "url": "https://example.com/a"},
                {"title": "Bad", "url": "javascript:alert(1)"}]}],
            "region_names": {"europe": "Europe"},
        }
        report.update(overrides)
        return report

    def test_safe_url(self):
        self.assertEqual(lib.safe_url("https://example.com"), "https://example.com")
        self.assertIsNone(lib.safe_url("javascript:alert(1)"))
        self.assertIsNone(lib.safe_url(None))

    def test_escapes_html_from_agents(self):
        html = lib.render_report_html(self.report())
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_unsafe_links_are_not_rendered_as_links(self):
        html = lib.render_report_html(self.report())
        self.assertIn('href="https://example.com/a"', html)
        self.assertNotIn('href="javascript:', html)

    def test_shows_first_run_and_deep_dive(self):
        html = lib.render_report_html(self.report())
        self.assertIn("First run", html)
        self.assertIn("Commuter group 10", html)
        self.assertIn("Missing in some countries", html)
        self.assertIn("9,000 paying users", html)
        self.assertNotIn("SAP", html)

    def test_explains_the_configured_weakened_penalty(self):
        html = lib.render_report_html(self.report(weakened_penalty=0.7))
        self.assertIn("lose 30%", html)

    def test_mentions_failed_regions(self):
        html = lib.render_report_html(self.report(failed_regions=["africa"]))
        self.assertIn("africa", html.lower())


@unittest.skipUnless(lib.find_browser(), "no Chrome-based browser installed")
class PdfTest(unittest.TestCase):
    def test_prints_html_to_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "r.html"
            html_path.write_text("<html><body><h1>Hello</h1></body></html>", encoding="utf-8")
            pdf_path = lib.print_pdf(html_path, Path(tmp) / "out" / "r.pdf", lib.find_browser())
            self.assertTrue(pdf_path.read_bytes().startswith(b"%PDF"))


class PdfHangTest(unittest.TestCase):
    """A headless browser sometimes hangs. Uses a fake browser, so no Chrome is needed."""
    HANGS_ONCE = ('#!/bin/sh\nmarker="$(dirname "$0")/called"\n'
                  'for arg in "$@"; do case "$arg" in --print-to-pdf=*) out="${arg#--print-to-pdf=}";; esac; done\n'
                  'if [ ! -e "$marker" ]; then : > "$marker"; exec sleep 30; fi\n'
                  "printf '%%PDF-1.4 fake' > \"$out\"\n")
    ALWAYS_HANGS = "#!/bin/sh\nexec sleep 30\n"

    def print_with(self, tmp, script):
        browser = Path(tmp) / "fake-browser"
        browser.write_text(script, encoding="utf-8")
        browser.chmod(0o755)
        html_path = Path(tmp) / "r.html"
        html_path.write_text("<html><body>Hello</body></html>", encoding="utf-8")
        return lib.print_pdf(html_path, Path(tmp) / "out" / "r.pdf", str(browser), timeout=1)

    def test_hung_browser_is_retried_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = self.print_with(tmp, self.HANGS_ONCE)
            self.assertTrue(pdf_path.read_bytes().startswith(b"%PDF"))

    def test_browser_that_always_hangs_gives_a_clean_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "did not finish within 1 second"):
                self.print_with(tmp, self.ALWAYS_HANGS)


@unittest.skipUnless(lib.find_browser(), "no Chrome-based browser installed")
class CliEndToEndTest(unittest.TestCase):
    """Runs the real CLI against a fake run (no agents), from new-run to PDF."""

    def run_cli(self, env, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "hunt.py"), *args],
                              capture_output=True, text=True, env=env, cwd=ROOT)

    def test_full_pipeline_produces_pdf_and_updates_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "BH_DATA_DIR": f"{tmp}/data", "BH_OUTPUT_DIR": f"{tmp}/Desktop"}
            out = self.run_cli(env, "new-run", "--raw", "--regions europe,latin_america --quick")
            self.assertEqual(out.returncode, 0, out.stderr)
            run = json.loads(out.stdout)
            run_dir = Path(run["run_dir"])
            self.assertEqual([r["id"] for r in run["regions"]], ["europe", "latin_america"])

            (run_dir / "cards" / "europe.json").write_text(json.dumps(make_cards_doc("europe", 2)))
            (run_dir / "cards" / "latin_america.json").write_text(json.dumps({"region": "latin_america"}))
            out = self.run_cli(env, "validate", "cards", str(run_dir))
            self.assertEqual(out.returncode, 1)
            self.assertIn("latin_america", out.stdout)
            out = self.run_cli(env, "validate", "cards", str(run_dir), "--skip-invalid")
            self.assertEqual(out.returncode, 0, out.stdout)

            clusters = [make_cluster("offline-tickets", refs=("europe/eu-01",)),
                        make_cluster("study-buddy", refs=("europe/eu-02",), title="Study buddy")]
            (run_dir / "clusters.json").write_text(json.dumps({"clusters": clusters}))
            self.assertEqual(self.run_cli(env, "validate", "clusters", str(run_dir)).returncode, 0)

            (run_dir / "scores.json").write_text(json.dumps(
                {"scores": [make_score("offline-tickets", 5), make_score("study-buddy", 2)]}))
            (run_dir / "skeptic.json").write_text(json.dumps(
                {"verdicts": [make_verdict("offline-tickets"), make_verdict("study-buddy", "weakened")]}))
            self.assertEqual(self.run_cli(env, "validate", "review", str(run_dir)).returncode, 0)

            out = self.run_cli(env, "rank", str(run_dir))
            self.assertEqual(out.returncode, 0, out.stderr)
            top_ids = json.loads(out.stdout)["top"]
            self.assertEqual(top_ids[0], "offline-tickets")

            (run_dir / "deepdives" / "offline-tickets.json").write_text(json.dumps(make_deepdive()))
            out = self.run_cli(env, "validate", "deepdives", str(run_dir))
            self.assertEqual(out.returncode, 1)  # study-buddy deep dive missing
            self.assertIn("study-buddy", out.stdout)

            out = self.run_cli(env, "finalize", str(run_dir))
            self.assertEqual(out.returncode, 0, out.stderr)
            pdf = Path(json.loads(out.stdout)["pdf"])
            self.assertEqual(pdf.parent, Path(tmp) / "Desktop")
            self.assertTrue(pdf.read_bytes().startswith(b"%PDF"))
            db = json.loads((Path(tmp) / "data" / "ideas.json").read_text())
            self.assertIn("offline-tickets", db["ideas"])


if __name__ == "__main__":
    unittest.main()
