# Launch Plan Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `/launch-plan`, which turns one ranked hunt idea into a staged Launch Plan PDF written by seven planning agents and checked by a script.

**Architecture:** Same shape as `/hunt`. A skill orchestrates agents; each agent writes one JSON file; `scripts/plan.py` validates each file, hands the critic's fixes back, and renders the PDF. Pure logic lives in `scripts/plan_lib.py` (arguments, lookup, validators) and `scripts/plan_report.py` (HTML); `plan.py` does the file work and reuses `hunt.py` / `hunt_lib.py` helpers.

**Tech Stack:** Python 3.11+ standard library, `unittest`, headless Chrome for PDF (existing `hunt_lib.print_pdf`), Claude Code skill and agent Markdown files.

**Spec:** `docs/superpowers/specs/2026-11-23-launch-plan-command-design.md`. Field names, counts and allowed values in "What each part contains" are binding; this plan does not repeat them.

## Global Constraints

- Python standard library only.
- Agents write JSON; the script validates; the orchestrator never edits agent JSON. The one file the orchestrator writes is `data/founder.json`.
- Runtime files under `data/` (`BH_DATA_DIR` overrides); PDFs in `~/Desktop/Business Hunter/` (`BH_OUTPUT_DIR` overrides).
- Reuse, do not copy: `hunt_lib._text/_list/_dict/_text_list/_links/_root/safe_url/SLUG/next_run_id/validate_deepdive/_e/_link/_bullets/find_browser/print_pdf` and `hunt.read_json/write_json/try_load/report_errors/date_label/DATA/OUTPUT/ROOT`.
- Validators return a list of error strings in the `hunt_lib` style (`"<path>.<key>: <what is wrong>"`) and never raise on malformed input.
- Report text is plain English; agent text is HTML-escaped; only `safe_url` links become links.
- Organisations, groups and places only; never a private person's name or contact details.
- `python3 -m unittest discover -s tests` passes after every task.
- `.claude/settings.json` is not changed by this plan. Allowing `python3 scripts/plan.py *` is offered to the owner at hand-over.
- Commits are local, on branch `launch-plan-command`. No push without the owner's word.

## Review Focus

1. The owner types the idea loosely (`[1]`, `#1`, `1.`, the whole text in brackets, notes with apostrophes). Expected: the idea and notes are still read. Test in Task 1.
2. An agent writes the wrong shape (a string where an object belongs, a number where text belongs, a list item that is not an object). Expected: an error line, never a crash. Test in Tasks 2 and 3.
3. Parts are missing at render time (no design, no money, no critic, no roadmap). Expected: a PDF with a warning, never a crash. Test in Task 4.
4. `finalize` runs twice for one plan, or two plans for one idea land on the same day. Expected: the first keeps one PDF name; the second gets its own. Test in Task 5.
5. The critic names a part that was left out, or there is no valid critic. Expected: `fixes` prints nothing for it and backs up nothing. Test in Task 5.

---

### Task 1: Arguments, idea lookup, earlier-plan lookup, PDF name

**Files:**
- Create: `scripts/plan_lib.py`
- Create: `tests/test_plan_lib.py`
- Modify: `tests/helpers.py` (add `make_ranked_item`, `make_run_entry`)

**Interfaces:**
- Produces:
  - `parse_plan_args(raw: str) -> dict` with keys `rank: int|None`, `idea_id: str|None`, `notes: str|None`, `fresh: bool`. Raises `ValueError` when the first word is neither a rank nor a slug.
  - Run entry (built by `plan.py`, consumed here): `{"run_id": str, "run_dir": str, "finished_at": str|None, "ranked": dict|None}` where `ranked` is the content of `ranked.json`.
  - `latest_run(runs: list[dict]) -> dict|None`: the entry with the greatest `finished_at` among those that have both `finished_at` and `ranked`.
  - `top_ideas(runs) -> dict|None`: `{"run_id": str, "ideas": [{"rank", "id", "title", "score"}]}` for the `top` items of the latest run.
  - `find_idea(runs, rank=None, idea_id=None) -> dict`: `{"run": <run entry>, "item": <ranked entry>}`. Raises `LookupError` with a one-line owner-readable message.
  - `previous_plan(plans: list[dict], idea_id: str) -> dict|None`: the `plan.json` dict with that `idea_id` and the greatest `finished_at`; plans without `finished_at` are ignored.
  - `pdf_name(date: str, title: str, taken) -> str`: `"<date> Launch Plan - <title>.pdf"`, title cleaned with `re.sub(r"[^\w \-]", "", title).strip()[:50]`; when that name is in `taken`, `" (2)"`, `" (3)"` ... goes before `.pdf`.
- `tests/helpers.py`: `make_ranked_item(idea_id="offline-tickets", rank=1, top=True, title="Offline bus tickets", score=81.5)`; `make_run_entry(run_id, finished_at, ranked=(), excluded=())` returning a run entry whose `ranked` is `{"ranked": [...], "excluded": [{"id", "title", "why"}]}`.

- [ ] **Step 1: Write the failing tests** in `tests/test_plan_lib.py` (header as in `tests/test_hunt_lib.py`, importing `plan_lib as plan`):

```python
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
```

- [ ] **Step 2: Run** `python3 -m unittest tests.test_plan_lib -v`. Expected: import error for `plan_lib`.
- [ ] **Step 3: Implement** the functions above in `scripts/plan_lib.py` and the two builders in `tests/helpers.py`. Parsing: strip one wrapping `[...]` pair from the whole text, split on whitespace, drop `--fresh`, clean the first word of `#`, `[`, `]` and a trailing `.`; all digits means a rank, a `hunt_lib.SLUG` match means an id, anything else raises `ValueError("Which idea should be planned? ...")`. `find_idea` by id walks finished runs newest first and stops at the first run that mentions the id in `ranked` or `excluded`.
- [ ] **Step 4: Run** the same command. Expected: all pass. Then `python3 -m unittest discover -s tests`: all pass.
- [ ] **Step 5: Commit** `git add scripts/plan_lib.py tests/test_plan_lib.py tests/helpers.py && git commit -m "plan: arguments, idea lookup, earlier-plan lookup"`

### Task 2: Validators for the profile and the five parts

**Files:**
- Modify: `scripts/plan_lib.py`, `tests/test_plan_lib.py`, `tests/helpers.py`

**Interfaces:**
- Produces:
  - `PARTS = ["product", "design", "build", "sales", "money"]`, `FIXABLE = ["design", "build", "sales", "money"]`, `SCREEN_KINDS = {"phone", "page", "document"}`.
  - `PROFILE_QUESTIONS`: ordered list of `(field, question)` for `builder`, `hours_per_week`, `budget_six_months`, `country`, `languages`, `goal`, with the six questions from the spec.
  - `validate_profile(doc) -> list[str]`: the six fields are text; `extra` is text, `null` or absent.
  - `validate_product(doc, idea_id) -> list[str]`; `stage_ids(product) -> list[str]` (ids in order, tolerant of malformed input).
  - `validate_design|validate_build|validate_sales|validate_money(doc, idea_id, stages: list[str]) -> list[str]`.
  - `PART_VALIDATORS = {"design": validate_design, "build": validate_build, "sales": validate_sales, "money": validate_money}`.
- `tests/helpers.py`: `PLAN_STAGES = ["prove-demand", "pilot", "paid-version"]`; `make_profile()`, `make_product(idea_id="offline-tickets", stages=PLAN_STAGES)`, `make_design`, `make_build`, `make_sales`, `make_money` (same two parameters), each returning a document that passes its validator with the minimum counts from the spec.

Rules beyond the spec's field list, all from the spec text:
- Every file: `id == idea_id`; `not_checked` is a list of text (may be empty); `sources`, when present, passes `hunt_lib._links`.
- Product: 3 to 5 stages, unique slug ids, first stage `needs_software is False`, every `needs_software` a real boolean.
- "Exactly one per product stage" (`build.per_stage`, `sales.per_stage`, `money.per_stage`): the list of `stage` values equals `stages`, same order.
- Any other `stage` / `when` field (`design.screens[].stage`, `sales.price_steps[].stage`, `money.start_costs[].stage`, `money.legal[].when`) is one of `stages`.
- `design.look.colors[].hex` matches `^#[0-9A-Fa-f]{6}$`; `budget_check.fits` is a real boolean.

- [ ] **Step 1: Write the failing tests**

```python
class ValidateProfileTest(unittest.TestCase):
    def test_valid_profile(self):
        self.assertEqual(plan.validate_profile(make_profile()), [])

    def test_missing_answer_and_number_are_reported(self):
        doc = make_profile(); del doc["goal"]; doc["hours_per_week"] = 10
        errors = "\n".join(plan.validate_profile(doc))
        self.assertIn("goal", errors); self.assertIn("hours_per_week", errors)

    def test_extra_is_optional(self):
        doc = make_profile(); doc["extra"] = None
        self.assertEqual(plan.validate_profile(doc), [])


class ValidateProductTest(unittest.TestCase):
    def test_valid_product(self):
        doc = make_product()
        self.assertEqual(plan.validate_product(doc, "offline-tickets"), [])
        self.assertEqual(plan.stage_ids(doc), PLAN_STAGES)

    def test_first_stage_must_not_build_software(self):
        doc = make_product(); doc["stages"][0]["needs_software"] = True
        self.assertRegex("\n".join(plan.validate_product(doc, "offline-tickets")), "prove demand")

    def test_stage_count_ids_and_booleans(self):
        doc = make_product(stages=["a", "b"])
        self.assertTrue(plan.validate_product(doc, "offline-tickets"))
        doc = make_product(); doc["stages"][1]["id"] = doc["stages"][0]["id"]
        self.assertRegex("\n".join(plan.validate_product(doc, "offline-tickets")), "duplicate")
        doc = make_product(); doc["stages"][1]["needs_software"] = "yes"
        self.assertTrue(plan.validate_product(doc, "offline-tickets"))

    def test_wrong_id_and_missing_not_checked(self):
        doc = make_product(); del doc["not_checked"]
        errors = "\n".join(plan.validate_product(doc, "other-idea"))
        self.assertIn("other-idea", errors); self.assertIn("not_checked", errors)


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
            doc = self.MAKERS[name](); doc["per_stage"].pop()
            self.assertRegex("\n".join(plan.PART_VALIDATORS[name](doc, "offline-tickets", PLAN_STAGES)),
                             "per_stage", name)

    def test_design_rules(self):
        doc = make_design(); doc["look"]["colors"][0]["hex"] = "blue"; doc["screens"][0]["kind"] = "tablet"
        errors = "\n".join(plan.validate_design(doc, "offline-tickets", PLAN_STAGES))
        self.assertIn("hex", errors); self.assertIn("kind", errors)
        doc = make_design(); doc["screens"] = doc["screens"][:3]
        self.assertTrue(plan.validate_design(doc, "offline-tickets", PLAN_STAGES))

    def test_sales_needs_support_and_keeping_customers(self):
        doc = make_sales(); del doc["support"]; doc["keeping_customers"] = doc["keeping_customers"][:1]
        errors = "\n".join(plan.validate_sales(doc, "offline-tickets", PLAN_STAGES))
        self.assertIn("support", errors); self.assertIn("keeping_customers", errors)

    def test_money_rules(self):
        doc = make_money(); doc["budget_check"]["fits"] = "yes"; doc["legal"] = doc["legal"][:2]
        errors = "\n".join(plan.validate_money(doc, "offline-tickets", PLAN_STAGES))
        self.assertIn("fits", errors); self.assertIn("legal", errors)

    def test_unsafe_source_link_is_reported(self):
        doc = make_build(); doc["sources"] = [{"title": "x", "url": "javascript:alert(1)"}]
        self.assertTrue(plan.validate_build(doc, "offline-tickets", PLAN_STAGES))

    def test_wrong_shapes_give_errors_not_crashes(self):
        for bad in (None, [], "text", 7, {"stages": "x", "screens": [1, "a"], "per_stage": {"a": 1},
                                          "look": [], "budget_check": 3, "tools": [None]}):
            self.assertTrue(plan.validate_profile(bad))
            self.assertTrue(plan.validate_product(bad, "offline-tickets"))
            self.assertEqual(plan.stage_ids(bad), [])
            for name, validator in plan.PART_VALIDATORS.items():
                self.assertTrue(validator(bad, "offline-tickets", PLAN_STAGES), name)
```

- [ ] **Step 2: Run** `python3 -m unittest tests.test_plan_lib -v`. Expected: the new classes fail.
- [ ] **Step 3: Implement** the validators and builders. Use small shared helpers in `plan_lib.py` for the repeated rules (`_common(doc, idea_id, errors)` for `id`, `not_checked`, `sources`; `_objects(obj, key, path, errors, text_keys, min_len)` returning only the dict items; `_per_stage(...)`; `_stage_ref(...)`).
- [ ] **Step 4: Run** the full suite. Expected: all pass.
- [ ] **Step 5: Commit** `git commit -am "plan: validators for the profile and the five parts"`

### Task 3: Critic and roadmap validators, verdict limits, fix lines

**Files:**
- Modify: `scripts/plan_lib.py`, `tests/test_plan_lib.py`, `tests/helpers.py`

**Interfaces:**
- Produces:
  - `CRITIC_VERDICTS = {"holds", "needs_fixes", "broken"}`, `ROADMAP_VERDICTS = {"start", "caution", "stop"}`.
  - `validate_critic(doc, idea_id) -> list[str]`: problem ids match `^c[1-9][0-9]*$` and are unique; `parts` is at least 1 of `PARTS`; `fix_in` is a list drawn from `FIXABLE`.
  - `validate_roadmap(doc, idea_id, stages, critic=None, money=None) -> list[str]`. `critic` and `money` are passed only when their files are valid.
  - `critic_fixes(critic, available=FIXABLE) -> dict[str, list[str]]`: for each part in `available` that some problem names in `fix_in`, the lines `"<id>: <problem> Fix: <fix>"` in problem order. Parts with no lines are absent.
- `tests/helpers.py`: `make_critic(idea_id="offline-tickets", verdict="needs_fixes", problems=None)` (default: `c1` in `build` and `sales` with `fix_in ["build"]`, `c2` in `product` with `fix_in []`); `make_roadmap(idea_id="offline-tickets", stages=PLAN_STAGES, verdict="caution", resolved=("c1", "c2"))`, which for `verdict="stop"` returns empty `stages` and `this_week` and one `what_would_change_this` item.

Roadmap rules: verdict `start`/`caution` needs `stages` equal to `stages` in order and at least 3 `this_week`; verdict `stop` needs both lists empty and at least 1 `what_would_change_this`; `what_would_change_this` is always a list; with `critic`, every problem id appears in `resolved[].problem_id`; `start` is refused when `critic["verdict"] == "broken"` or `money["budget_check"]["fits"] is False`.

- [ ] **Step 1: Write the failing tests**

```python
class ValidateCriticTest(unittest.TestCase):
    def test_valid_critic(self):
        self.assertEqual(plan.validate_critic(make_critic(), "offline-tickets"), [])

    def test_product_cannot_be_sent_back_for_fixes(self):
        doc = make_critic(); doc["problems"][1]["fix_in"] = ["product"]
        self.assertRegex("\n".join(plan.validate_critic(doc, "offline-tickets")), "fix_in")

    def test_bad_verdict_ids_and_parts(self):
        doc = make_critic(verdict="fine"); doc["problems"][1]["id"] = "c1"; doc["problems"][0]["parts"] = ["marketing"]
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
        doc = make_roadmap(); doc["stages"].reverse()
        self.assertIn("stages", self.check(doc))

    def test_stop_has_no_roadmap_and_says_what_would_change_it(self):
        self.assertEqual(self.check(make_roadmap(verdict="stop")), "")
        doc = make_roadmap(verdict="stop"); doc["this_week"] = ["Call three managers"]
        self.assertIn("this_week", self.check(doc))
        doc = make_roadmap(verdict="stop"); doc["what_would_change_this"] = []
        self.assertIn("what_would_change_this", self.check(doc))

    def test_start_is_blocked_by_broken_critic_or_budget(self):
        doc = make_roadmap(verdict="start")
        self.assertIn("broken", self.check(doc, critic=make_critic(verdict="broken")))
        money = make_money(); money["budget_check"]["fits"] = False
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
```

- [ ] **Step 2: Run** `python3 -m unittest tests.test_plan_lib -v`. Expected: the new classes fail.
- [ ] **Step 3: Implement** the three functions and the two builders.
- [ ] **Step 4: Run** the full suite. Expected: all pass.
- [ ] **Step 5: Commit** `git commit -am "plan: critic and roadmap validators, verdict limits, fix lines"`

### Task 4: The Launch Plan HTML

**Files:**
- Create: `scripts/plan_report.py`
- Modify: `scripts/report.css` (append; existing rules untouched), `tests/test_plan_lib.py`

**Interfaces:**
- Consumes: `hunt_lib._e/_link/_bullets/safe_url`; the document shapes from Tasks 2 and 3.
- Produces:
  - `VERDICT_LABELS = {"start": "Start", "caution": "Start, with caution", "stop": "Do not start"}`.
  - `render_plan_html(report: dict) -> str`. `report` keys: `plan_id`, `date_label`, `title`, `one_liner`, `source_run`, `previous` (`{"plan_id", "date_label"}` or `None`), `notes` (text or `None`), `founder` (profile), `product` (always present), `design`, `build`, `sales`, `money`, `critic`, `roadmap` (each a valid document or `None`), `left_out` (names of parts that failed), `kept_earlier` (names of parts restored after the fix round).
- Section headings, in order, exactly: `Summary`, `Roadmap`, `Decisions for you`, `Product`, `Design`, `Build`, `Sales`, `Money and legal`, `What the critic found`, `Your profile and sources`. For verdict `stop`: no `Roadmap`, `Summary` shows `What would change this`, and a line `What the planners worked out, for reference` precedes `Product`. With no roadmap: verdict box text `No verdict: the plan lead did not finish`, followed by `The critic's verdict: <verdict>` when there is a critic, and `Summary`, `Roadmap`, `Decisions for you` are left out.
- Warning boxes at the top (`.callout.warn`): `Left out of this plan: ...` when `left_out` is not empty; `Kept from before the critic's fixes: ...` when `kept_earlier` is not empty; `Some points could not be checked in: ...` naming every section whose document has `not_checked` items. Each such section also prints a box headed `Not checked`.
- Section names shown to the reader: `product` Product, `design` Design, `build` Build, `sales` Sales, `money` Money and legal, `critic` Critic, `roadmap` Roadmap.
- Screens: `<div class="screen phone">` for `phone`, `<div class="screen wide">` for `page` and `document`. Swatches: `<span class="swatch" style="background:#RRGGBB">` only when the hex matches the Task 2 pattern.
- Stage names: roadmap and per-stage tables show the product stage `name`, not the id.
- Closing note, exact: `This is desk research by AI agents. Confirm legal and tax points with a local professional, and talk to real customers before you spend money.`
- New CSS classes: `.verdict` with `.start`, `.caution`, `.stop`, `.none`; `.stage`; `.checklist`; `.swatch`; `.screens`; `.screen` with `.phone`, `.wide`; `.notchecked`.

- [ ] **Step 1: Write the failing tests** (`import plan_report as report_lib`)

```python
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
        build = make_build(); build["sources"] = [{"title": "Bad", "url": "javascript:alert(1)"}]
        html = report_lib.render_plan_html(self.report(build=build))
        self.assertNotIn("<script>", html); self.assertNotIn('href="javascript:', html)

    def test_stop_verdict_has_no_roadmap_or_checklist(self):
        html = report_lib.render_plan_html(self.report(roadmap=make_roadmap(verdict="stop")))
        self.assertIn("Do not start", html); self.assertIn("What would change this", html)
        self.assertNotIn(">Roadmap<", html); self.assertNotIn('class="checklist"', html)
        self.assertIn("What the planners worked out, for reference", html)

    def test_missing_roadmap_shows_no_verdict(self):
        html = report_lib.render_plan_html(self.report(roadmap=None, left_out=["roadmap"]))
        self.assertIn("No verdict: the plan lead did not finish", html)
        self.assertIn("The critic's verdict", html)
        self.assertNotIn(">Roadmap<", html)

    def test_missing_parts_do_not_crash_and_are_named(self):
        html = report_lib.render_plan_html(self.report(
            design=None, money=None, critic=None, roadmap=None, left_out=["design", "money", "critic", "roadmap"]))
        self.assertIn("Left out of this plan", html); self.assertIn("Money and legal", html)

    def test_not_checked_is_printed_and_summarised(self):
        sales = make_sales(); sales["not_checked"] = ["Prices of two rivals"]
        html = report_lib.render_plan_html(self.report(sales=sales))
        self.assertIn("Some points could not be checked in: Sales", html)
        self.assertIn("Prices of two rivals", html)

    def test_kept_earlier_and_previous_plan_are_mentioned(self):
        html = report_lib.render_plan_html(self.report(
            kept_earlier=["build"], previous={"plan_id": "2026-11-23-offline-tickets", "date_label": "23 November 2026"}))
        self.assertIn("Kept from before the critic", html); self.assertIn("23 November 2026", html)

    def test_screens_and_swatches(self):
        html = report_lib.render_plan_html(self.report())
        self.assertIn('class="screen phone"', html); self.assertIn('class="swatch"', html)
```

- [ ] **Step 2: Run** `python3 -m unittest tests.test_plan_lib -v`. Expected: import error for `plan_report`.
- [ ] **Step 3: Implement** `render_plan_html` as one small function per section, each returning `""` when its document is `None`; read every field with `.get` so a document that is valid but lean cannot break the page. Append the CSS.
- [ ] **Step 4: Run** the full suite. Expected: all pass.
- [ ] **Step 5: Commit** `git add scripts/plan_report.py scripts/report.css tests/test_plan_lib.py && git commit -m "plan: Launch Plan HTML"`

### Task 5: The command line

**Files:**
- Create: `scripts/plan.py`
- Modify: `tests/test_plan_lib.py`

**Interfaces:**
- Consumes: everything from Tasks 1 to 4; `import hunt` for `read_json`, `write_json`, `try_load`, `report_errors`, `date_label`, `DATA`, `OUTPUT`.
- Produces these commands. All print JSON or plain status lines and exit non-zero on problems.
  - `start --raw "<text>"` prints `{"status": ...}`:
    - `pick_idea`: plus `run_id` and `ideas` from `top_ideas`. When no run is finished: exit 1, `ERROR: ...`.
    - `profile_missing`: plus `profile_path`, `questions` (`[{"field", "question"}]`) and `errors`.
    - `needs_deepdive`: plus `idea_id`, `run_dir`, `errors`.
    - `ready`: plus `plan_dir`, `plan_id`, `idea_id`, `title`, `builds_on` (earlier plan id or `null`).
    - Order of checks: arguments, idea lookup (`ERROR: <message>`, exit 1), profile, deep dive. Nothing is written until `ready`.
    - On `ready` it creates `data/plans/<plan_id>/parts/`, writes `plan.json` (`plan_id`, `idea_id`, `title`, `source_run`, `run_dir`, `notes`, `fresh`, `date`, `started_at`, `previous_plan`, `left_out: []`, `kept_earlier: []`) and `input.json` (`plan_id`, `date`, `idea`, `deepdive`, `founder`, `notes`, `source_run`, `previous`). `plan_id` is `hunt_lib.next_run_id(DATA / "plans", f"{date}-{idea_id}")`. `previous` is `{"plan_id", "date", "parts": {name: doc}, "critic", "roadmap"}` built from the earlier plan's files that still validate, or `null`.
  - `validate-profile`: `OK profile` or `ERROR profile: ...` lines for `DATA / "founder.json"`.
  - `validate <stage> <plan_dir> [--skip-invalid]`, stage in `product`, `parts`, `money`, `critic`, `roadmap`. `parts` means design, build and sales. Lines: `OK <name>`, `ERROR <name>: ...`, and with `--skip-invalid` either `KEPT <name>: the version from before the critic's fixes` (when `parts/<name>.before-fix.json` exists: it replaces the invalid file and the name is added to `kept_earlier`) or `SKIPPED <name>: left out of this plan` (the file is renamed to `.invalid.json` and the name is added to `left_out`). Names already in `left_out` are not checked again. `product` ignores `--skip-invalid` and always exits 1 on errors. A missing or invalid `product.json` makes every other stage exit 1 with `ERROR product: ...`.
  - `fixes <plan_dir>`: prints `{"fixes": {part: [lines]}, "order": [[first batch], [second batch]]}` where the first batch is the named parts among design, build, sales and the second is `["money"]` when named; empty batches are dropped. Only parts that are present and not in `left_out` count. Each named part's file is copied to `parts/<name>.before-fix.json`. No valid critic: `{"fixes": {}, "order": []}`.
  - `finalize <plan_dir>`: loads every document that validates, renders `report.html`, prints the PDF, sets `finished_at` and `pdf` in `plan.json`, and prints `{"pdf", "verdict", "stages", "this_week", "left_out", "kept_earlier", "not_checked_in"}` (`verdict` is `null` without a valid roadmap; `stages` are product stage names; `this_week` is the first 3). A plan that already has `pdf` reuses that file name; otherwise `pdf_name` with the names already in the output folder.

- [ ] **Step 1: Write the failing test**: a `PlanCliEndToEndTest` class, skipped without a browser like `CliEndToEndTest`, with a `run_cli(env, *args)` helper for `scripts/plan.py` and a `setUp` that builds, under a temporary `BH_DATA_DIR`, one finished run `2026-11-23` (`run.json` with `finished_at`, `ranked.json` with `offline-tickets` ranked 1 and top, `study-buddy` ranked 2 and not top, `old-idea` excluded) and `deepdives/offline-tickets.json` from `make_deepdive()`. Tests:

  - `test_start_statuses`: `start --raw ""` gives `pick_idea` listing `offline-tickets`; `start --raw "1"` gives `profile_missing` with 6 questions and no `data/plans` folder; after writing `founder.json` from `make_profile()`, `validate-profile` exits 0; `start --raw "study-buddy"` gives `needs_deepdive`; `start --raw "old-idea"` exits 1 and names the cut; `start --raw "[1] web only"` gives `ready`, and `input.json` has `notes == "web only"`, `previous is None`, `deepdive["id"] == "offline-tickets"`.
  - `test_full_plan_produces_pdf`: after `ready`, write `parts/product.json`; `validate product` exits 0. Write valid design and sales and an invalid build (`{"id": "offline-tickets"}`); `validate parts` exits 1 naming `build`; `validate parts --skip-invalid` exits 0 with `SKIPPED build`. Write money, critic (`fix_in ["build"]` for `c1`), roadmap; each validates. `fixes` prints `{"fixes": {}, "order": []}` because build was left out, and no `.before-fix.json` exists. `finalize` exits 0; the PDF starts with `%PDF`; output `verdict == "caution"`, `left_out == ["build"]`, 3 stage names. A second `finalize` prints the same `pdf` path and the output folder holds exactly one PDF.
  - `test_fix_round_keeps_earlier_version`: with valid product, design, build, sales and a critic naming `build` and `money` (money valid too): `fixes` prints `order == [["build"], ["money"]]` and `parts/build.before-fix.json` exists. Overwrite `parts/build.json` with `{"id": "offline-tickets"}`; `validate parts --skip-invalid` prints `KEPT build`, `parts/build.json` validates again, and `plan.json` has `kept_earlier == ["build"]` and `left_out == []`.
  - `test_second_plan_builds_on_first_unless_fresh`: finish one plan; `start --raw "1"` again gives a different `plan_id` ending `-2`, `builds_on` equal to the first plan id, and `input.json["previous"]["parts"]["product"]["id"] == "offline-tickets"`; its `finalize` gives a PDF name ending ` (2).pdf`; `start --raw "1 --fresh"` gives `builds_on is None`.
  - `test_stop_plan_and_missing_roadmap`: a roadmap from `make_roadmap(verdict="stop")` finalizes with `verdict == "stop"` and `this_week == []`; a plan where `validate roadmap --skip-invalid` skipped an invalid roadmap finalizes with `verdict is None` and `"roadmap" in left_out`.
  - `test_roadmap_start_blocked_by_budget`: money with `fits` false and a roadmap with verdict `start`: `validate roadmap` exits 1 and mentions `budget`.

- [ ] **Step 2: Run** `python3 -m unittest tests.test_plan_lib.PlanCliEndToEndTest -v`. Expected: fails, `plan.py` missing.
- [ ] **Step 3: Implement** `scripts/plan.py` (`chmod +x`, module docstring listing the commands as in `hunt.py`). Runs are loaded from every `data/runs/*/run.json`; plans from every `data/plans/*/plan.json`.
- [ ] **Step 4: Run** the full suite. Expected: all pass.
- [ ] **Step 5: Commit** `git add scripts/plan.py tests/test_plan_lib.py && git commit -m "plan: command line from start to PDF"`

### Task 6: Agents, skill and project notes

**Files:**
- Create: `.claude/agents/product-planner.md`, `design-planner.md`, `build-planner.md`, `sales-planner.md`, `money-planner.md`, `plan-critic.md`, `plan-lead.md`
- Create: `.claude/skills/launch-plan/SKILL.md`
- Modify: `.claude/skills/hunt/SKILL.md` (Step 8), `CLAUDE.md` (Running, Layout), `tests/test_plan_lib.py`

**Interfaces:**
- Consumes: the validators (Tasks 2, 3) and the command lines (Task 5).
- Each agent file: front matter as in `.claude/agents/deep-diver.md` (`name`, `description` ending "Used by the /launch-plan pipeline.", `tools`, `model: inherit`); `tools: Read, Write, WebSearch, WebFetch`, and `Read, Write` for `plan-lead`. Body sections: role; `## Input` (the prompt gives `plan_dir`; read `<plan_dir>/input.json` and the listed earlier files, noting which may be missing); `## What to work out`; `## Rules` (the shared rules from the spec, the search budget from the spec's table); `## Output` (the file path and exactly one fenced `json` example that passes the validator, using idea id `offline-bus-tickets` and stage ids `prove-demand`, `pilot`, `paid-version`); a closing line format: `<part>: <one fact>; searches: <n>; search refused: yes|no`, and "If you are given validation errors or critic fixes, fix exactly those problems and write the file again."
- Earlier files each agent reads: design, build, sales read `parts/product.json`; money reads product, build, sales; critic reads all five parts; plan-lead reads all five parts and `critic.json`.
- Part-specific content the prompts must carry:
  - `product-planner`: the first stage proves demand without software; the stages are the spine every other planner follows; the hunt skeptic's reasons in `input.json` must be answered or carried forward.
  - `design-planner`: design the no-software stage too (offer page, sample document); the user is the customer named in the deep dive, on the device they really use.
  - `build-planner`: fit the founder's `builder`, `hours_per_week` and `budget_six_months`; prefer the cheapest route that works; the developer brief must stand on its own.
  - `sales-planner`: no paid ads unless the numbers carry them; local-language texts for the first market; support and keeping customers.
  - `money-planner`: every number traces to build or sales or is listed in `assumptions`; `budget_check` compares with the founder's answers; legal items say who to ask.
  - `plan-critic`: look for contradictions between parts, numbers that do not add up, and a first stage that does not test the real doubt; send a problem to `fix_in` only when one planner can fix it alone; product problems get `fix_in: []`.
  - `plan-lead`: the verdict rules from the spec's "The verdict", word for word in substance; the roadmap shape for `stop`; resolve every critic problem id; `decisions_for_you` holds only what the owner alone can decide.
- `SKILL.md`: the nine steps of the spec's "The run, step by step" and "When web search is refused", in the `/hunt` skill's style, with the same closing Rules section adapted (never edit agent JSON; the one exception is writing `data/founder.json` from the owner's answers, every answer as text; never skip a validation; if something fails twice, leave it out and say so). Profile questions come from the `questions` in the `profile_missing` output, asked in one message. The fix-round prompt: the agent's usual prompt plus "The critic found these problems in your part. Read your file, fix exactly these and write it again:" and the lines.
- `/hunt` Step 8 gains: "End with one line: to plan one of these, open a new session and type /launch-plan and its rank."
- `CLAUDE.md`: Running gains `/launch-plan [rank or idea id] [notes] [--fresh]`; Layout gains the seven agents, `scripts/plan.py` with `plan_lib.py` and `plan_report.py`, `data/plans/<plan_id>/` and `data/founder.json`.

- [ ] **Step 1: Write the failing test**

```python
class AgentExamplesTest(unittest.TestCase):
    """The JSON example in each planning agent's file must pass the script's own checks."""
    AGENTS = ROOT / ".claude" / "agents"

    def example(self, name):
        text = (self.AGENTS / f"{name}.md").read_text(encoding="utf-8")
        blocks = re.findall(r"```json\n(.*?)```", text, re.S)
        self.assertEqual(len(blocks), 1, name)
        return json.loads(blocks[0])

    def test_examples_validate(self):
        idea = "offline-bus-tickets"
        product = self.example("product-planner")
        self.assertEqual(plan.validate_product(product, idea), [])
        stages = plan.stage_ids(product)
        parts = {"design": "design-planner", "build": "build-planner", "sales": "sales-planner", "money": "money-planner"}
        docs = {name: self.example(agent) for name, agent in parts.items()}
        for name, doc in docs.items():
            self.assertEqual(plan.PART_VALIDATORS[name](doc, idea, stages), [], name)
        critic = self.example("plan-critic")
        self.assertEqual(plan.validate_critic(critic, idea), [])
        self.assertEqual(plan.validate_roadmap(self.example("plan-lead"), idea, stages,
                                               critic=critic, money=docs["money"]), [])

    def test_front_matter(self):
        for name in ("product-planner", "design-planner", "build-planner", "sales-planner",
                     "money-planner", "plan-critic", "plan-lead"):
            text = (self.AGENTS / f"{name}.md").read_text(encoding="utf-8")
            self.assertIn(f"name: {name}\n", text)
            self.assertIn("model: inherit", text)
            self.assertIn("search refused: yes|no", text)
        self.assertIn("tools: Read, Write\n", (self.AGENTS / "plan-lead.md").read_text(encoding="utf-8"))

    def test_skill_runs_every_command(self):
        skill = (ROOT / ".claude" / "skills" / "launch-plan" / "SKILL.md").read_text(encoding="utf-8")
        for needle in ("plan.py start --raw", "validate-profile", "validate product", "validate parts",
                       "validate money", "validate critic", "plan.py fixes", "validate roadmap",
                       "plan.py finalize", "--skip-invalid", "new session"):
            self.assertIn(needle, skill)
```

- [ ] **Step 2: Run** `python3 -m unittest tests.test_plan_lib.AgentExamplesTest -v`. Expected: fails, files missing.
- [ ] **Step 3: Write** the seven agent files, the skill, and the two edits.
- [ ] **Step 4: Run** the full suite. Expected: all pass.
- [ ] **Step 5: Commit** `git add .claude CLAUDE.md tests/test_plan_lib.py docs && git commit -m "plan: planning agents, /launch-plan skill, project notes"`
