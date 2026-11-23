#!/usr/bin/env python3
"""Launch Plan command line: the deterministic steps of /launch-plan.

  python3 scripts/plan.py start --raw "<rank or idea id> [notes] [--fresh]"
  python3 scripts/plan.py validate-profile
  python3 scripts/plan.py validate product|parts|money|critic|roadmap <plan_dir> [--skip-invalid]
  python3 scripts/plan.py fixes <plan_dir>
  python3 scripts/plan.py finalize <plan_dir>

Every command prints JSON or plain status lines and exits non-zero on problems.
"""

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

import hunt
import hunt_lib as lib
import plan_lib as plan
import plan_report

PLANS = hunt.DATA / "plans"
PROFILE = hunt.DATA / "founder.json"
STAGE_FILES = {"parts": ["design", "build", "sales"], "money": ["money"],
               "critic": ["critic"], "roadmap": ["roadmap"]}


def show(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def read_doc(path):
    """Return (doc, errors) for a JSON file written by an agent or the orchestrator."""
    try:
        return hunt.read_json(path), []
    except FileNotFoundError:
        return None, [f"file missing ({path.name})"]
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, [f"not valid JSON ({exc})"]


def load_runs():
    runs = []
    for run_json in sorted((hunt.DATA / "runs").glob("*/run.json")):
        run, _ = read_doc(run_json)
        if not isinstance(run, dict):
            continue
        ranked, _ = read_doc(run_json.parent / "ranked.json")
        runs.append({"run_id": run.get("run_id") or run_json.parent.name, "run_dir": str(run_json.parent),
                     "finished_at": run.get("finished_at"),
                     "ranked": ranked if isinstance(ranked, dict) else None})
    return runs


def load_plans():
    plans = []
    for path in sorted(PLANS.glob("*/plan.json")):
        state, _ = read_doc(path)
        if isinstance(state, dict):
            plans.append({**state, "plan_dir": str(path.parent)})
    return plans


def load_plan(plan_dir):
    plan_dir = Path(plan_dir).resolve()
    state, errors = read_doc(plan_dir / "plan.json")
    if errors or not isinstance(state, dict):
        sys.exit(f"ERROR: {plan_dir} is not a plan folder (no readable plan.json)")
    return plan_dir, state


def part_path(plan_dir, name):
    if name in ("critic", "roadmap"):
        return plan_dir / f"{name}.json"
    return plan_dir / "parts" / f"{name}.json"


def backup_path(plan_dir, name):
    return plan_dir / "parts" / f"{name}.before-fix.json"


def check(plan_dir, state, name, stages=None, critic=None, money=None):
    """Return (doc, errors) for one plan file."""
    doc, errors = read_doc(part_path(plan_dir, name))
    if errors:
        return None, errors
    idea_id = state.get("idea_id")
    if name == "product":
        return doc, plan.validate_product(doc, idea_id)
    if name in plan.PART_VALIDATORS:
        return doc, plan.PART_VALIDATORS[name](doc, idea_id, stages)
    if name == "critic":
        return doc, plan.validate_critic(doc, idea_id)
    return doc, plan.validate_roadmap(doc, idea_id, stages, critic=critic, money=money)


def valid(plan_dir, state, name, stages=None, **context):
    """The document when it is present, not left out and passes its checks; else None."""
    if name in state.get("left_out", []):
        return None
    doc, errors = check(plan_dir, state, name, stages, **context)
    return None if errors else doc


def load_stages(plan_dir, state):
    """Stage ids of a valid product part. Prints the errors and exits when it is not valid."""
    product, errors = check(plan_dir, state, "product")
    if errors:
        hunt.report_errors("product", errors)
        sys.exit(1)
    return plan.stage_ids(product)


def load_previous(earlier):
    """What the planners may build on: the still-valid files of an earlier plan."""
    plan_dir = Path(earlier["plan_dir"])
    product = valid(plan_dir, earlier, "product")
    if product is None:
        return None
    stages = plan.stage_ids(product)
    parts = {"product": product}
    for name in plan.FIXABLE:
        doc = valid(plan_dir, earlier, name, stages)
        if doc is not None:
            parts[name] = doc
    critic = valid(plan_dir, earlier, "critic", stages)
    roadmap = valid(plan_dir, earlier, "roadmap", stages, critic=critic, money=parts.get("money"))
    return {"plan_id": earlier.get("plan_id"), "date": earlier.get("date"),
            "parts": parts, "critic": critic, "roadmap": roadmap}


# ---------------------------------------------------------------- commands

def cmd_start(args):
    try:
        asked = plan.parse_plan_args(args.raw)
    except ValueError as exc:
        sys.exit(f"ERROR: {exc}")
    runs = load_runs()
    if asked["rank"] is None and asked["idea_id"] is None:
        top = plan.top_ideas(runs)
        if not top:
            sys.exit("ERROR: No finished hunt found. Run /hunt first, then plan one of its ideas.")
        show({"status": "pick_idea", **top})
        return
    try:
        found = plan.find_idea(runs, rank=asked["rank"], idea_id=asked["idea_id"])
    except LookupError as exc:
        sys.exit(f"ERROR: {exc}")
    item, run = found["item"], found["run"]
    idea_id = item["id"]

    profile, errors = read_doc(PROFILE)
    if not errors:
        errors = plan.validate_profile(profile)
    if errors:
        show({"status": "profile_missing", "profile_path": str(PROFILE),
              "questions": [{"field": field, "question": question} for field, question in plan.PROFILE_QUESTIONS],
              "errors": errors})
        return

    deepdive, errors = read_doc(Path(run["run_dir"]) / "deepdives" / f"{idea_id}.json")
    if not errors:
        errors = lib.validate_deepdive(deepdive, idea_id)
    if errors:
        show({"status": "needs_deepdive", "idea_id": idea_id, "run_dir": run["run_dir"], "errors": errors})
        return

    earlier = None if asked["fresh"] else plan.previous_plan(load_plans(), idea_id)
    previous = load_previous(earlier) if earlier else None
    today = dt.date.today().isoformat()
    plan_id = lib.next_run_id(PLANS, f"{today}-{idea_id}")
    plan_dir = PLANS / plan_id
    (plan_dir / "parts").mkdir(parents=True)
    hunt.write_json(plan_dir / "plan.json", {
        "plan_id": plan_id, "idea_id": idea_id, "title": item.get("title"), "source_run": run["run_id"],
        "run_dir": run["run_dir"], "notes": asked["notes"], "fresh": asked["fresh"], "date": today,
        "started_at": dt.datetime.now().isoformat(timespec="seconds"),
        "previous_plan": previous["plan_id"] if previous else None, "left_out": [], "kept_earlier": []})
    hunt.write_json(plan_dir / "input.json", {
        "plan_id": plan_id, "date": today, "idea": item, "deepdive": deepdive, "founder": profile,
        "notes": asked["notes"], "source_run": run["run_id"], "previous": previous})
    show({"status": "ready", "plan_dir": str(plan_dir), "plan_id": plan_id, "idea_id": idea_id,
          "title": item.get("title"), "builds_on": previous["plan_id"] if previous else None})


def cmd_validate_profile(_args):
    profile, errors = read_doc(PROFILE)
    if not errors:
        errors = plan.validate_profile(profile)
    if errors:
        hunt.report_errors("profile", errors)
        sys.exit(1)
    print("OK profile")


def cmd_validate(args):
    plan_dir, state = load_plan(args.plan_dir)
    if args.stage == "product":  # nothing can be planned without the stages, so it is never skipped
        product, errors = check(plan_dir, state, "product")
        if errors:
            hunt.report_errors("product", errors)
            sys.exit(1)
        print(f"OK product: {len(plan.stage_ids(product))} stages")
        return

    stages = load_stages(plan_dir, state)
    ok = True
    for name in STAGE_FILES[args.stage]:
        if name in state.get("left_out", []):
            print(f"SKIPPED {name}: already left out of this plan")
            continue
        context = {}
        if name == "roadmap":
            context = {"critic": valid(plan_dir, state, "critic", stages),
                       "money": valid(plan_dir, state, "money", stages)}
        _doc, errors = check(plan_dir, state, name, stages, **context)
        if not errors:
            print(f"OK {name}")
            continue
        hunt.report_errors(name, errors)
        if not args.skip_invalid:
            ok = False
            continue
        path, backup = part_path(plan_dir, name), backup_path(plan_dir, name)
        if backup.exists():  # the critic's fix broke a part that was valid: keep the earlier version
            shutil.copyfile(backup, path)
            if name not in state.setdefault("kept_earlier", []):
                state["kept_earlier"].append(name)
            print(f"KEPT {name}: the version from before the critic's fixes")
        else:
            if path.exists():
                path.replace(path.with_suffix(".invalid.json"))
            state.setdefault("left_out", []).append(name)
            print(f"SKIPPED {name}: left out of this plan")
        hunt.write_json(plan_dir / "plan.json", state)
    sys.exit(0 if ok else 1)


def cmd_fixes(args):
    plan_dir, state = load_plan(args.plan_dir)
    stages = load_stages(plan_dir, state)
    critic = valid(plan_dir, state, "critic", stages)
    available = [name for name in plan.FIXABLE
                 if name not in state.get("left_out", []) and part_path(plan_dir, name).exists()]
    fixes = plan.critic_fixes(critic, available)
    for name in fixes:
        if not backup_path(plan_dir, name).exists():  # never overwrite the pre-fix version
            shutil.copyfile(part_path(plan_dir, name), backup_path(plan_dir, name))
    first = [name for name in STAGE_FILES["parts"] if name in fixes]
    second = ["money"] if "money" in fixes else []
    show({"fixes": fixes, "order": [batch for batch in (first, second) if batch]})


def cmd_finalize(args):
    plan_dir, state = load_plan(args.plan_dir)
    product, errors = check(plan_dir, state, "product")
    if errors:
        hunt.report_errors("product", errors)
        sys.exit("ERROR: the product part is missing or invalid, so there is no plan to print")
    stages = plan.stage_ids(product)
    docs = {name: valid(plan_dir, state, name, stages) for name in plan.FIXABLE}
    docs["critic"] = valid(plan_dir, state, "critic", stages)
    docs["roadmap"] = valid(plan_dir, state, "roadmap", stages, critic=docs["critic"], money=docs["money"])
    left_out = [name for name, doc in docs.items() if doc is None]
    kept_earlier = [name for name in state.get("kept_earlier", []) if docs.get(name) is not None]

    given, _ = read_doc(plan_dir / "input.json")
    given = given if isinstance(given, dict) else {}
    previous = given.get("previous") if isinstance(given.get("previous"), dict) else None
    deepdive = given.get("deepdive") if isinstance(given.get("deepdive"), dict) else {}
    report = {
        "plan_id": state.get("plan_id"), "date_label": hunt.date_label(state["date"]),
        "title": state.get("title"), "one_liner": deepdive.get("one_liner"),
        "source_run": state.get("source_run"),
        "previous": ({"plan_id": previous.get("plan_id"), "date_label": hunt.date_label(previous["date"])}
                     if previous and previous.get("date") else None),
        "notes": state.get("notes"), "founder": given.get("founder"),
        "product": product, **docs, "left_out": left_out, "kept_earlier": kept_earlier,
    }
    html_path = plan_dir / "report.html"
    html_path.write_text(plan_report.render_plan_html(report), encoding="utf-8")

    if state.get("pdf"):  # printing the same plan again keeps its file name
        name = Path(state["pdf"]).name
    else:
        taken = {p.name for p in hunt.OUTPUT.glob("*.pdf")} if hunt.OUTPUT.exists() else set()
        name = plan.pdf_name(state["date"], state.get("title"), taken)
    try:
        pdf_path = lib.print_pdf(html_path, hunt.OUTPUT / name, lib.find_browser())
    except (RuntimeError, OSError) as exc:
        sys.exit(f"ERROR: could not create the PDF ({exc}). The HTML report is at {html_path}")

    state["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
    state["pdf"] = str(pdf_path)
    hunt.write_json(plan_dir / "plan.json", state)
    roadmap = docs["roadmap"] or {}
    all_docs = {"product": product, **docs}
    show({"pdf": str(pdf_path), "verdict": roadmap.get("verdict"),
          "stages": [stage.get("name") for stage in product["stages"]],
          "this_week": roadmap.get("this_week", [])[:3],
          "left_out": left_out, "kept_earlier": kept_earlier,
          "not_checked_in": [name for name, doc in all_docs.items() if doc and doc.get("not_checked")]})


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("start")
    p.add_argument("--raw", default="", help="the text typed after /launch-plan")
    p.set_defaults(func=cmd_start)
    p = sub.add_parser("validate-profile")
    p.set_defaults(func=cmd_validate_profile)
    p = sub.add_parser("validate")
    p.add_argument("stage", choices=["product", *STAGE_FILES])
    p.add_argument("plan_dir")
    p.add_argument("--skip-invalid", action="store_true")
    p.set_defaults(func=cmd_validate)
    for name, func in (("fixes", cmd_fixes), ("finalize", cmd_finalize)):
        p = sub.add_parser(name)
        p.add_argument("plan_dir")
        p.set_defaults(func=func)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
