#!/usr/bin/env python3
"""Business Hunter command line: the deterministic steps of a hunt.

  python3 scripts/hunt.py new-run --raw "<theme> [--regions a,b] [--quick]"
  python3 scripts/hunt.py validate cards|clusters|review|deepdives <run_dir> [--skip-invalid]
  python3 scripts/hunt.py rank <run_dir>
  python3 scripts/hunt.py finalize <run_dir>

Every command prints JSON or plain status lines and exits non-zero on problems.
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
import tomllib
from pathlib import Path

import hunt_lib as lib

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = Path(os.environ.get("BH_DATA_DIR") or ROOT / "data")
OUTPUT = Path(os.environ.get("BH_OUTPUT_DIR") or Path.home() / "Desktop" / "Business Hunter")
MAX_CLUSTERS = {"quick": 8, "full": 20}


def load_toml(name):
    with open(CONFIG / name, "rb") as f:
        return tomllib.load(f)


def regions_config():
    return load_toml("regions.toml")["region"]


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def load_run(run_dir):
    run_dir = Path(run_dir).resolve()
    if not (run_dir / "run.json").exists():
        sys.exit(f"ERROR: {run_dir} is not a run folder (no run.json)")
    return run_dir, read_json(run_dir / "run.json")


def active_regions(run):
    return [r for r in run["regions"] if r not in run.get("failed_regions", [])]


def try_load(path, errors, label):
    try:
        return read_json(path)
    except FileNotFoundError:
        errors.append(f"{label}: file missing ({path.name})")
    except json.JSONDecodeError as exc:
        errors.append(f"{label}: not valid JSON ({exc})")
    return None


def load_cards(run_dir, run):
    docs = {}
    for region in active_regions(run):
        path = run_dir / "cards" / f"{region}.json"
        if path.exists():
            docs[region] = read_json(path)
    return docs


# ---------------------------------------------------------------- commands

def cmd_new_run(args):
    regions = regions_config()
    ids = [r["id"] for r in regions]
    try:
        parsed = lib.parse_hunt_args(args.raw, ids)
    except ValueError as exc:
        sys.exit(f"ERROR: {exc}")
    today = dt.date.today().isoformat()
    run_id = lib.next_run_id(DATA / "runs", today)
    run_dir = DATA / "runs" / run_id
    (run_dir / "cards").mkdir(parents=True)
    (run_dir / "deepdives").mkdir()
    mode = "quick" if parsed["quick"] else "full"
    run = {"run_id": run_id, "date": today, "theme": parsed["theme"], "quick": parsed["quick"],
           "regions": parsed["regions"], "failed_regions": [], "failed_deepdives": [],
           "max_clusters": MAX_CLUSTERS[mode],
           "started_at": dt.datetime.now().isoformat(timespec="seconds")}
    write_json(run_dir / "run.json", run)
    names = {r["id"]: r["name"] for r in regions}
    print(json.dumps({"run_dir": str(run_dir), "run_id": run_id, "theme": parsed["theme"],
                      "quick": parsed["quick"], "max_clusters": run["max_clusters"],
                      "regions": [{"id": r, "name": names[r]} for r in parsed["regions"]]}, indent=2))


def cmd_validate(args):
    run_dir, run = load_run(args.run_dir)
    handler = {"cards": validate_cards, "clusters": validate_clusters,
               "review": validate_review, "deepdives": validate_deepdives}[args.stage]
    ok = handler(run_dir, run, args.skip_invalid)
    sys.exit(0 if ok else 1)


def report_errors(label, errors, limit=25):
    for err in errors[:limit]:
        print(f"ERROR {label}: {err}")
    if len(errors) > limit:
        print(f"ERROR {label}: ... and {len(errors) - limit} more")


def mark_failed(run_dir, run, key, item, path):
    if path.exists():
        path.rename(path.with_suffix(".invalid.json"))
    run.setdefault(key, [])
    if item not in run[key]:
        run[key].append(item)
    write_json(run_dir / "run.json", run)


def validate_cards(run_dir, run, skip_invalid):
    good, bad = 0, []
    for region in active_regions(run):
        path = run_dir / "cards" / f"{region}.json"
        errors = []
        doc = try_load(path, errors, region)
        if doc is not None:
            errors = lib.validate_cards(doc, region)
        if errors:
            report_errors(region, errors)
            bad.append((region, path))
        else:
            good += 1
            print(f"OK {region}: {len(doc['cards'])} findings")
    if skip_invalid:
        for region, path in bad:
            mark_failed(run_dir, run, "failed_regions", region, path)
            print(f"SKIPPED {region}: left out of this run")
        if good == 0:
            print("ERROR: no region produced valid findings")
            return False
        return True
    return not bad


def validate_clusters(run_dir, run, _skip):
    card_ids = {f"{region}/{card['id']}" for region, doc in load_cards(run_dir, run).items()
                for card in doc.get("cards", []) if isinstance(card, dict)}
    errors = []
    doc = try_load(run_dir / "clusters.json", errors, "clusters.json")
    if doc is not None:
        errors = lib.validate_clusters(doc, [r["id"] for r in regions_config()], card_ids,
                                       max_clusters=run.get("max_clusters"))
    if errors:
        report_errors("clusters.json", errors)
        return False
    print(f"OK clusters.json: {len(doc['clusters'])} ideas")
    return True


def cluster_ids(run_dir):
    return {c["id"] for c in read_json(run_dir / "clusters.json")["clusters"]}


def validate_review(run_dir, run, _skip):
    ids = cluster_ids(run_dir)
    ok = True
    for name, validator in (("scores.json", lib.validate_scores), ("skeptic.json", lib.validate_skeptic)):
        errors = []
        doc = try_load(run_dir / name, errors, name)
        if doc is not None:
            errors = validator(doc, ids)
        if errors:
            report_errors(name, errors)
            ok = False
        else:
            print(f"OK {name}")
    return ok


def validate_deepdives(run_dir, run, skip_invalid):
    ranked = read_json(run_dir / "ranked.json")
    ok = True
    for item in [i for i in ranked["ranked"] if i["top"]]:
        path = run_dir / "deepdives" / f"{item['id']}.json"
        errors = []
        doc = try_load(path, errors, item["id"])
        if doc is not None:
            errors = lib.validate_deepdive(doc, item["id"])
        if not errors:
            print(f"OK {item['id']}")
            continue
        report_errors(item["id"], errors)
        if skip_invalid:
            mark_failed(run_dir, run, "failed_deepdives", item["id"], path)
            print(f"SKIPPED {item['id']}: report will note the missing deep dive")
        else:
            ok = False
    return ok


def cmd_rank(args):
    run_dir, run = load_run(args.run_dir)
    clusters = read_json(run_dir / "clusters.json")["clusters"]
    scores = read_json(run_dir / "scores.json")["scores"]
    verdicts = read_json(run_dir / "skeptic.json")["verdicts"]
    rubric = load_toml("rubric.toml")
    if run.get("quick"):
        rubric["top_n"] = min(int(rubric.get("top_n", 5)), 2)
    try:
        result = lib.rank_ideas(clusters, scores, verdicts, rubric)
    except ValueError as exc:
        sys.exit(f"ERROR: {exc}")
    write_json(run_dir / "ranked.json", result)
    print(json.dumps({"top": [i["id"] for i in result["ranked"] if i["top"]],
                      "ranked": len(result["ranked"]), "cut": len(result["excluded"])}, indent=2))


def date_label(iso_date):
    d = dt.date.fromisoformat(iso_date)
    return f"{d.day} {d:%B %Y}"


def collect_sources(cards_by_region, names, deepdives):
    groups = []
    for region, doc in cards_by_region.items():
        seen, items = set(), []
        for card in doc.get("cards", []):
            for ev in card.get("evidence", []):
                url = ev.get("url")
                if url and url not in seen:
                    seen.add(url)
                    items.append({"title": ev.get("claim", url), "url": url})
        if items:
            groups.append({"region": names.get(region, region), "items": items})
    return groups


def pdf_name(run):
    name = f"{run['run_id']} Hunt Report"
    if run.get("theme"):
        theme = re.sub(r"[^\w \-]", "", run["theme"]).strip()[:40]
        if theme:
            name += f" - {theme}"
    return name + ".pdf"


def cmd_finalize(args):
    run_dir, run = load_run(args.run_dir)
    names = {r["id"]: r["name"] for r in regions_config()}
    cards = load_cards(run_dir, run)
    clusters = read_json(run_dir / "clusters.json")["clusters"]
    ranked = read_json(run_dir / "ranked.json")
    db_path = DATA / "ideas.json"
    db = read_json(db_path) if db_path.exists() else lib.empty_db()

    deepdives = {}
    for item in ranked["ranked"]:
        path = run_dir / "deepdives" / f"{item['id']}.json"
        if item["top"] and path.exists():
            doc = read_json(path)
            if not lib.validate_deepdive(doc, item["id"]):
                deepdives[item["id"]] = doc
    top = [{**i, "deepdive": deepdives.get(i["id"])} for i in ranked["ranked"] if i["top"]]

    report = {
        "run_id": run["run_id"], "date_label": date_label(run["date"]), "theme": run.get("theme"),
        "quick": run.get("quick", False),
        "weakened_penalty": ranked.get("weakened_penalty", 0.85),
        "stats": {"regions": len(cards), "cards": sum(len(d.get("cards", [])) for d in cards.values()),
                  "clusters": len(clusters), "survivors": len(ranked["ranked"])},
        "failed_regions": run.get("failed_regions", []),
        "top": top,
        "others": [i for i in ranked["ranked"] if not i["top"]],
        "excluded": ranked["excluded"],
        "changes": lib.diff_against_db(ranked["ranked"], db, current_run=run["run_id"]),
        "regions": [{"id": r, "name": names.get(r, r), "summary": cards[r].get("summary", []),
                     "card_count": len(cards[r].get("cards", []))} for r in run["regions"] if r in cards],
        "sources": collect_sources(cards, names, deepdives),
        "region_names": names,
    }
    html_path = run_dir / "report.html"
    html_path.write_text(lib.render_report_html(report), encoding="utf-8")
    try:
        pdf_path = lib.print_pdf(html_path, OUTPUT / pdf_name(run), lib.find_browser())
    except (RuntimeError, OSError) as exc:
        sys.exit(f"ERROR: could not create the PDF ({exc}). The HTML report is at {html_path}")

    write_json(db_path, lib.update_db(db, ranked["ranked"], ranked["excluded"], run["run_id"]))
    run["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
    run["pdf"] = str(pdf_path)
    write_json(run_dir / "run.json", run)
    print(json.dumps({"pdf": str(pdf_path),
                      "top": [{"rank": i["rank"], "title": i["title"], "score": i["score"]} for i in top]},
                     indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("new-run")
    p.add_argument("--raw", default="", help="the text typed after /hunt")
    p.set_defaults(func=cmd_new_run)
    p = sub.add_parser("validate")
    p.add_argument("stage", choices=["cards", "clusters", "review", "deepdives"])
    p.add_argument("run_dir")
    p.add_argument("--skip-invalid", action="store_true")
    p.set_defaults(func=cmd_validate)
    for name, func in (("rank", cmd_rank), ("finalize", cmd_finalize)):
        p = sub.add_parser(name)
        p.add_argument("run_dir")
        p.set_defaults(func=func)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
