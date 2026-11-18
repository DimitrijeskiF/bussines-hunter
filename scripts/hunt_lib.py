"""Deterministic parts of the Business Hunter pipeline.

Agents do the research and write JSON files. This module checks those files,
ranks the ideas, tracks them across runs and renders the PDF report.
Standard library only.
"""

import html
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

LENSES = {"wishes", "local_gaps", "trends", "paying_already"}
GAP_TYPES = {"missing_everywhere", "missing_here"}
GAP_LABELS = {"missing_everywhere": "Missing everywhere", "missing_here": "Missing in some countries"}
VERDICTS = {"survives", "weakened", "killed"}
RISK_LEVELS = {"low", "medium", "high"}
SCORER_CHECKS = ["pain_frequency", "audience_size", "willingness_to_pay", "competition_gap",
                 "buildability", "cheap_to_run", "cheap_reach"]
ALL_CHECKS = SCORER_CHECKS + ["multi_region"]
CHECK_LABELS = {
    "pain_frequency": "Needed every month",
    "audience_size": "Audience size",
    "willingness_to_pay": "Will pay $1-3",
    "competition_gap": "Competition gap",
    "buildability": "Small-team buildable",
    "cheap_to_run": "Cheap to run",
    "cheap_reach": "Users without ads",
    "multi_region": "Multi-region pull",
}
MIN_FIRST_USER_PLACES = 5
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
BROWSER_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


# ---------------------------------------------------------------- run setup

def next_run_id(runs_dir, date):
    """Return `date`, or `date-N` if earlier runs already used that date."""
    runs_dir = Path(runs_dir)
    if not (runs_dir / date).exists():
        return date
    n = 2
    while (runs_dir / f"{date}-{n}").exists():
        n += 1
    return f"{date}-{n}"


def parse_hunt_args(raw, known_regions):
    """Parse '/hunt' arguments: free-text theme, optional --regions a,b and --quick."""
    raw = (raw or "").strip()
    try:
        tokens = shlex.split(raw)
    except ValueError:  # e.g. an apostrophe in "kids' apps"
        tokens = raw.split()

    theme_words, regions, quick = [], None, False
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token == "--quick":
            quick = True
        elif token == "--regions" or token.startswith("--regions="):
            if "=" in token:
                value = token.split("=", 1)[1]
            else:
                i += 1
                value = tokens[i] if i < len(tokens) else ""
            regions = [_normalize_region(r) for r in value.split(",") if r.strip()]
        else:
            theme_words.append(token)
        i += 1

    if regions is None:
        regions = list(known_regions)
    unknown = [r for r in regions if r not in known_regions]
    if unknown:
        raise ValueError(f"Unknown region(s): {', '.join(unknown)}. "
                         f"Known regions: {', '.join(known_regions)}")
    if not regions:
        raise ValueError("No regions selected.")
    theme = " ".join(theme_words).strip() or None
    return {"theme": theme, "regions": regions, "quick": quick}


def _normalize_region(name):
    return name.strip().lower().replace("-", "_").replace(" ", "_")


# ---------------------------------------------------------------- validation helpers

def safe_url(url):
    """Return the URL if it is a plain http(s) link, else None."""
    if isinstance(url, str) and re.match(r"^https?://[^\s<>\"']+$", url.strip()):
        return url.strip()
    return None


def _is_text(value):
    return isinstance(value, str) and value.strip() != ""


def _text(obj, key, path, errors, nullable=False):
    value = obj.get(key) if isinstance(obj, dict) else None
    if value is None and nullable and isinstance(obj, dict) and key in obj:
        return None
    if not _is_text(value):
        errors.append(f"{path}.{key}: must be non-empty text" + (" or null" if nullable else ""))
        return None
    return value


def _list(obj, key, path, errors, min_len=0):
    value = obj.get(key) if isinstance(obj, dict) else None
    if not isinstance(value, list):
        errors.append(f"{path}.{key}: must be a list")
        return []
    if len(value) < min_len:
        errors.append(f"{path}.{key}: needs at least {min_len} item(s), has {len(value)}")
    return value


def _dict(obj, key, path, errors):
    value = obj.get(key) if isinstance(obj, dict) else None
    if not isinstance(value, dict):
        errors.append(f"{path}.{key}: must be an object")
        return {}
    return value


def _text_list(obj, key, path, errors, min_len=0):
    items = _list(obj, key, path, errors, min_len)
    for i, item in enumerate(items):
        if not _is_text(item):
            errors.append(f"{path}.{key}[{i}]: must be non-empty text")
    return items


def _links(obj, key, path, errors, label_key, min_len=1):
    items = _list(obj, key, path, errors, min_len)
    for i, item in enumerate(items):
        item_path = f"{path}.{key}[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{item_path}: must be an object")
            continue
        _text(item, label_key, item_path, errors)
        if not safe_url(item.get("url")):
            errors.append(f"{item_path}.url: must be an http(s) link, got {item.get('url')!r}")
    return items


def _root(doc, errors):
    if not isinstance(doc, dict):
        errors.append("file: must contain a JSON object")
        return False
    return True


# ---------------------------------------------------------------- stage validators

def validate_cards(doc, expected_region):
    errors = []
    if not _root(doc, errors):
        return errors
    if doc.get("region") != expected_region:
        errors.append(f"region: expected {expected_region!r}, got {doc.get('region')!r}")
    _text_list(doc, "summary", "file", errors, min_len=1)
    seen = set()
    for i, card in enumerate(_list(doc, "cards", "file", errors, min_len=1)):
        path = f"cards[{i}]"
        if not isinstance(card, dict):
            errors.append(f"{path}: must be an object")
            continue
        card_id = _text(card, "id", path, errors)
        if card_id in seen:
            errors.append(f"{path}.id: duplicate id {card_id!r}")
        seen.add(card_id)
        for key in ("title", "problem", "subscription_case", "solution_idea"):
            _text(card, key, path, errors)
        _text(card, "why_now", path, errors, nullable=True)
        _gap_type(card, path, errors)
        who = _dict(card, "who_feels_it", path, errors)
        _text(who, "group", f"{path}.who_feels_it", errors)
        _text(who, "how_many", f"{path}.who_feels_it", errors)
        lenses = _list(card, "lens", path, errors, min_len=1)
        bad = [lens for lens in lenses if lens not in LENSES]
        if bad:
            errors.append(f"{path}.lens: unknown lens {bad}; use {sorted(LENSES)}")
        _links(card, "evidence", path, errors, "claim")
        for j, tool in enumerate(_list(card, "existing_tools", path, errors)):
            _text(tool, "name", f"{path}.existing_tools[{j}]", errors)
            _text(tool, "gap", f"{path}.existing_tools[{j}]", errors)
        _text_list(card, "countries", path, errors, min_len=1)
    return errors


def _gap_type(obj, path, errors):
    if obj.get("gap_type") not in GAP_TYPES:
        errors.append(f"{path}.gap_type: must be one of {sorted(GAP_TYPES)}, got {obj.get('gap_type')!r}")


def validate_clusters(doc, known_regions, card_ids, max_clusters=None):
    errors = []
    if not _root(doc, errors):
        return errors
    clusters = _list(doc, "clusters", "file", errors, min_len=1)
    if max_clusters and len(clusters) > max_clusters:
        errors.append(f"clusters: at most {max_clusters} allowed, got {len(clusters)}")
    seen = set()
    for i, cluster in enumerate(clusters):
        path = f"clusters[{i}]"
        if not isinstance(cluster, dict):
            errors.append(f"{path}: must be an object")
            continue
        cluster_id = cluster.get("id")
        if not (isinstance(cluster_id, str) and SLUG.match(cluster_id)):
            errors.append(f"{path}.id: must be a lowercase slug like 'offline-bus-tickets', got {cluster_id!r}")
        elif cluster_id in seen:
            errors.append(f"{path}.id: duplicate id {cluster_id!r}")
        seen.add(cluster_id)
        for key in ("title", "problem", "solution_idea", "customer", "subscription_case"):
            _text(cluster, key, path, errors)
        _text(cluster, "why_now", path, errors, nullable=True)
        _gap_type(cluster, path, errors)
        _check_regions(_list(cluster, "regions", path, errors, min_len=1),
                       f"{path}.regions", known_regions, errors)
        patterns = _dict(cluster, "patterns", path, errors)
        if not isinstance(patterns.get("global_pain"), bool):
            errors.append(f"{path}.patterns.global_pain: must be true or false")
        arbitrage = patterns.get("arbitrage")
        if arbitrage is not None:
            arb_path = f"{path}.patterns.arbitrage"
            if not isinstance(arbitrage, dict):
                errors.append(f"{arb_path}: must be null or an object")
            else:
                _check_regions(_list(arbitrage, "solved_in", arb_path, errors, min_len=1),
                               f"{arb_path}.solved_in", known_regions, errors)
                _check_regions(_list(arbitrage, "open_in", arb_path, errors, min_len=1),
                               f"{arb_path}.open_in", known_regions, errors)
                _text(arbitrage, "note", arb_path, errors)
        for ref in _list(cluster, "card_refs", path, errors, min_len=1):
            if ref not in card_ids:
                errors.append(f"{path}.card_refs: {ref!r} is not a card id (use 'region/card-id')")
        _links(cluster, "evidence", path, errors, "claim")
    return errors


def _check_regions(regions, path, known_regions, errors):
    unknown = [r for r in regions if r not in known_regions]
    if unknown:
        errors.append(f"{path}: unknown region(s) {unknown}")


def _coverage(entries, cluster_ids, label, errors):
    ids = [e.get("id") for e in entries if isinstance(e, dict)]
    for dup in sorted({i for i in ids if ids.count(i) > 1}, key=str):
        errors.append(f"{label}: duplicate entry for {dup!r}")
    for missing in sorted(cluster_ids - set(ids)):
        errors.append(f"{label}: missing entry for idea {missing!r}")
    for extra in sorted(set(ids) - cluster_ids, key=str):
        errors.append(f"{label}: {extra!r} is not an idea id from clusters.json")


def validate_scores(doc, cluster_ids):
    errors = []
    if not _root(doc, errors):
        return errors
    entries = _list(doc, "scores", "file", errors, min_len=1)
    _coverage(entries, set(cluster_ids), "scores", errors)
    for i, entry in enumerate(entries):
        path = f"scores[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{path}: must be an object")
            continue
        hard = _dict(entry, "hard_filter", path, errors)
        rejected = hard.get("rejected")
        if not isinstance(rejected, bool):
            errors.append(f"{path}.hard_filter.rejected: must be true or false")
        if rejected:
            _text(hard, "reason", f"{path}.hard_filter", errors)
            continue
        checks = _dict(entry, "checks", path, errors)
        for key in SCORER_CHECKS:
            check = checks.get(key)
            check_path = f"{path}.checks.{key}"
            if not isinstance(check, dict):
                errors.append(f"{check_path}: missing")
                continue
            score = check.get("score")
            if not (isinstance(score, int) and not isinstance(score, bool) and 1 <= score <= 5):
                errors.append(f"{check_path}.score: must be a whole number 1-5, got {score!r}")
            _text(check, "why", check_path, errors)
    return errors


def validate_skeptic(doc, cluster_ids):
    errors = []
    if not _root(doc, errors):
        return errors
    entries = _list(doc, "verdicts", "file", errors, min_len=1)
    _coverage(entries, set(cluster_ids), "verdicts", errors)
    for i, entry in enumerate(entries):
        path = f"verdicts[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{path}: must be an object")
            continue
        if entry.get("verdict") not in VERDICTS:
            errors.append(f"{path}.verdict: must be one of {sorted(VERDICTS)}, got {entry.get('verdict')!r}")
        if entry.get("big_tech_risk") not in RISK_LEVELS:
            errors.append(f"{path}.big_tech_risk: must be one of {sorted(RISK_LEVELS)}")
        _text_list(entry, "incumbents", path, errors)
        _text_list(entry, "reasons", path, errors, min_len=1)
        _text(entry, "what_would_change_my_mind", path, errors)
    return errors


def validate_deepdive(doc, expected_id):
    errors = []
    if not _root(doc, errors):
        return errors
    if doc.get("id") != expected_id:
        errors.append(f"id: expected {expected_id!r}, got {doc.get('id')!r}")
    for key in ("title", "one_liner", "how_to_get_users"):
        _text(doc, key, "file", errors)
    for i, comp in enumerate(_list(doc, "competitors", "file", errors, min_len=1)):
        path = f"competitors[{i}]"
        for key in ("name", "what_they_do", "weakness"):
            _text(comp, key, path, errors)
        if isinstance(comp, dict) and comp.get("url") is not None and not safe_url(comp.get("url")):
            errors.append(f"{path}.url: must be an http(s) link or omitted")
    customer = _dict(doc, "customer", "file", errors)
    for key in ("who", "where", "pain_in_their_words"):
        _text(customer, key, "customer", errors)
    mvp = _dict(doc, "mvp", "file", errors)
    _text_list(mvp, "scope", "mvp", errors, min_len=1)
    _text(mvp, "time_to_build", "mvp", errors)
    _text(mvp, "team", "mvp", errors)
    pricing = _dict(doc, "pricing", "file", errors)
    for key in ("model", "price", "rationale"):
        _text(pricing, key, "pricing", errors)
    economics = _dict(doc, "unit_economics", "file", errors)
    for key in ("cost_per_user", "users_needed"):
        _text(economics, key, "unit_economics", errors)
    places = _list(doc, "first_users", "file", errors, min_len=MIN_FIRST_USER_PLACES)
    for i, place in enumerate(places):
        for key in ("name", "where", "why"):
            _text(place, key, f"first_users[{i}]", errors)
        if isinstance(place, dict) and place.get("url") is not None and not safe_url(place.get("url")):
            errors.append(f"first_users[{i}].url: must be an http(s) link or omitted")
    _text_list(doc, "risks", "file", errors, min_len=1)
    _links(doc, "sources", "file", errors, "title")
    return errors


# ---------------------------------------------------------------- ranking

def multi_region_score(region_count):
    if region_count >= 6:
        return 5
    if region_count >= 4:
        return 4
    return max(1, min(region_count, 3))


def rank_ideas(clusters, scores, verdicts, rubric):
    weights = rubric.get("weights") or {}
    missing = [k for k in ALL_CHECKS if k not in weights]
    if missing:
        raise ValueError(f"rubric weights are missing for: {', '.join(missing)}")
    penalty = float(rubric.get("weakened_penalty", 0.85))
    top_n = int(rubric.get("top_n", 5))
    score_by_id = {s["id"]: s for s in scores}
    verdict_by_id = {v["id"]: v for v in verdicts}

    ranked, excluded = [], []
    for cluster in clusters:
        cid = cluster["id"]
        score, verdict = score_by_id.get(cid), verdict_by_id.get(cid)
        if score is None or verdict is None:
            excluded.append(_excluded(cluster, "Not reviewed by both the scorer and the skeptic."))
            continue
        if score["hard_filter"]["rejected"]:
            excluded.append(_excluded(cluster, f"Hard filter: {score['hard_filter']['reason']}"))
            continue
        if verdict["verdict"] == "killed":
            excluded.append(_excluded(cluster, "Killed by the skeptic: " + " ".join(verdict["reasons"])))
            continue
        checks = dict(score["checks"])
        region_count = len(set(cluster.get("regions", [])))
        checks["multi_region"] = {"score": multi_region_score(region_count),
                                  "why": f"Seen in {region_count} region(s)."}
        total_weight = sum(float(weights.get(k, 0)) for k in ALL_CHECKS)
        average = sum(float(weights.get(k, 0)) * checks[k]["score"] for k in ALL_CHECKS) / total_weight
        value = (average - 1) / 4 * 100
        if verdict["verdict"] == "weakened":
            value *= penalty
        ranked.append({**cluster, "score": round(value, 1), "checks": checks,
                       "verdict": verdict["verdict"], "skeptic": verdict})

    ranked.sort(key=lambda item: (-item["score"], -item["checks"]["multi_region"]["score"], item["title"]))
    for position, item in enumerate(ranked, start=1):
        item["rank"] = position
        item["top"] = position <= top_n
    return {"top_n": top_n, "weakened_penalty": penalty, "ranked": ranked, "excluded": excluded}


def _excluded(cluster, why):
    return {"id": cluster["id"], "title": cluster.get("title", cluster["id"]), "why": why}


# ---------------------------------------------------------------- idea database

def empty_db():
    return {"runs": [], "ideas": {}}


def _previous_run(db, current_run=None):
    runs = [r for r in db.get("runs", []) if r != current_run]
    return runs[-1] if runs else None


def _entry_for(db, idea_id, run_id):
    for entry in db.get("ideas", {}).get(idea_id, {}).get("history", []):
        if entry.get("run") == run_id:
            return entry
    return None


def diff_against_db(ranked, db, current_run=None):
    previous = _previous_run(db, current_run)
    if previous is None:
        return {"first_run": True, "previous_run": None,
                "new": [_brief(i) for i in ranked], "moved": [], "dropped": []}

    new, moved = [], []
    for item in ranked:
        before = _entry_for(db, item["id"], previous)
        if item["id"] not in db.get("ideas", {}):
            new.append(_brief(item))
        elif before and before.get("rank") and before["rank"] != item["rank"]:
            moved.append({**_brief(item), "from": before["rank"], "to": item["rank"]})

    top_now = {i["id"] for i in ranked if i.get("top")}
    dropped = []
    for idea_id, idea in db.get("ideas", {}).items():
        before = _entry_for(db, idea_id, previous)
        if before and before.get("status") == "top" and idea_id not in top_now:
            dropped.append({"id": idea_id, "title": idea.get("title", idea_id),
                            "was_rank": before.get("rank")})
    return {"first_run": False, "previous_run": previous, "new": new, "moved": moved, "dropped": dropped}


def _brief(item):
    return {"id": item["id"], "title": item.get("title", item["id"]),
            "score": item.get("score"), "rank": item.get("rank")}


def update_db(db, ranked, excluded, run_id):
    """Record this run's results. Re-running the same run replaces its entries."""
    db = {"runs": [r for r in db.get("runs", []) if r != run_id],
          "ideas": {k: {**v, "history": [h for h in v.get("history", []) if h.get("run") != run_id]}
                    for k, v in db.get("ideas", {}).items()}}
    db["runs"].append(run_id)

    def touch(idea_id, title, entry):
        idea = db["ideas"].setdefault(idea_id, {"title": title, "first_seen": run_id, "history": []})
        idea["title"] = title
        idea["last_seen"] = run_id
        idea["history"].append({"run": run_id, **entry})

    for item in ranked:
        touch(item["id"], item.get("title", item["id"]),
              {"score": item["score"], "rank": item["rank"], "status": "top" if item.get("top") else "candidate"})
    for item in excluded:
        touch(item["id"], item.get("title", item["id"]), {"status": "excluded", "why": item.get("why")})
    return db


# ---------------------------------------------------------------- rendering

def _e(value):
    return html.escape("" if value is None else str(value))


def _link(label, url):
    href = safe_url(url)
    if href:
        return f'<a href="{_e(href)}">{_e(label)}</a>'
    return _e(label)


def _region_list(ids, names):
    return ", ".join(names.get(r, r) for r in ids)


def _tags(item):
    tags = []
    if item.get("gap_type") in GAP_LABELS:
        tags.append(f'<span class="tag gap">{_e(GAP_LABELS[item["gap_type"]])}</span>')
    patterns = item.get("patterns") or {}
    if patterns.get("global_pain"):
        tags.append('<span class="tag global">Global pain</span>')
    if patterns.get("arbitrage"):
        tags.append('<span class="tag arb">Arbitrage</span>')
    if item.get("verdict") == "weakened":
        tags.append('<span class="tag weak">Weakened</span>')
    return " ".join(tags)


def _bullets(items):
    if not items:
        return ""
    return "<ul>" + "".join(f"<li>{_e(i)}</li>" for i in items) + "</ul>"


def _render_changes(changes):
    if changes["first_run"]:
        return "<p>First run: every idea below is new. From the next run on, this section shows what changed.</p>"
    parts = [f'<p class="note">Compared with the run of {_e(changes["previous_run"])}.</p>']
    if changes["new"]:
        parts.append("<h3>New ideas</h3><ul>" + "".join(
            f"<li>#{_e(i['rank'])} {_e(i['title'])} ({_e(i['score'])})</li>" for i in changes["new"]) + "</ul>")
    if changes["moved"]:
        parts.append("<h3>Moved</h3><ul>" + "".join(
            f"<li>{_e(i['title'])}: #{_e(i['from'])} → #{_e(i['to'])}</li>" for i in changes["moved"]) + "</ul>")
    if changes["dropped"]:
        parts.append("<h3>Left the top list</h3><ul>" + "".join(
            f"<li>{_e(i['title'])} (was #{_e(i['was_rank'])})</li>" for i in changes["dropped"]) + "</ul>")
    if len(parts) == 1:
        parts.append("<p>No changes in the ranking since the last run.</p>")
    return "".join(parts)


def _render_scorecard(item):
    rows = []
    for key in ALL_CHECKS:
        check = item.get("checks", {}).get(key)
        if not check:
            continue
        filled = "●" * check["score"] + "○" * (5 - check["score"])
        rows.append(f"<tr><td>{_e(CHECK_LABELS[key])}</td><td class=\"dots\">{filled}</td>"
                    f"<td>{_e(check.get('why'))}</td></tr>")
    return '<table class="scorecard"><tbody>' + "".join(rows) + "</tbody></table>"


def _render_deepdive(item, names):
    dd = item.get("deepdive")
    skeptic = item.get("skeptic") or {}
    arbitrage = (item.get("patterns") or {}).get("arbitrage")
    out = [f'<section class="idea"><div class="idea-head"><span class="rank">#{_e(item["rank"])}</span>'
           f'<h2>{_e(item.get("title"))}</h2><span class="score">{_e(item.get("score"))}</span></div>',
           f'<p class="meta">{_e(_region_list(item.get("regions", []), names))} {_tags(item)}</p>']
    if dd:
        out.append(f'<p class="lead">{_e(dd.get("one_liner"))}</p>')
    out.append('<div class="grid2">'
               f'<div class="box"><h4>Problem</h4><p>{_e(item.get("problem"))}</p></div>'
               f'<div class="box"><h4>What to build</h4><p>{_e(item.get("solution_idea"))}</p></div>'
               f'<div class="box"><h4>Who has the problem</h4><p>{_e(item.get("customer"))}</p></div>'
               f'<div class="box"><h4>Why they would pay every month</h4><p>{_e(item.get("subscription_case"))}</p>'
               f'<p class="note">Why now: {_e(item.get("why_now") or "nothing specific found")}</p></div>'
               "</div>")
    if arbitrage:
        out.append(f'<p><span class="tag arb">Arbitrage</span> Solved in '
                   f'{_e(_region_list(arbitrage.get("solved_in", []), names))}, still open in '
                   f'{_e(_region_list(arbitrage.get("open_in", []), names))}. {_e(arbitrage.get("note"))}</p>')
    out.append("<h3>Scorecard</h3>" + _render_scorecard(item))
    out.append(f'<h3>Skeptic: {_e(item.get("verdict"))}</h3>'
               f'<p class="note">Risk that a big tech company gives it away free: {_e(skeptic.get("big_tech_risk"))}. '
               f'Incumbents: {_e(", ".join(skeptic.get("incumbents", [])) or "none found")}.</p>'
               + _bullets(skeptic.get("reasons"))
               + f'<p class="note">What would change the verdict: {_e(skeptic.get("what_would_change_my_mind"))}</p>')

    if not dd:
        out.append('<div class="callout warn">The deep dive for this idea did not complete in this run.</div>')
        out.append("</section>")
        return "".join(out)

    customer, mvp, pricing = dd.get("customer", {}), dd.get("mvp", {}), dd.get("pricing", {})
    economics = dd.get("unit_economics", {})
    out.append('<div class="grid2">'
               f'<div class="box"><h4>Customer</h4><p><strong>{_e(customer.get("who"))}</strong>; where: '
               f'{_e(customer.get("where"))}</p><p class="quote">“{_e(customer.get("pain_in_their_words"))}”</p></div>'
               f'<div class="box"><h4>Price</h4><p><strong>{_e(pricing.get("price"))}</strong>, '
               f'{_e(pricing.get("model"))}</p><p>{_e(pricing.get("rationale"))}</p></div>'
               f'<div class="box"><h4>First version (MVP)</h4>{_bullets(mvp.get("scope"))}'
               f'<p class="note">{_e(mvp.get("time_to_build"))} · {_e(mvp.get("team"))}</p></div>'
               f'<div class="box"><h4>The numbers</h4><p>Running cost per user: {_e(economics.get("cost_per_user"))}</p>'
               f'<p>{_e(economics.get("users_needed"))}</p></div>'
               "</div>")
    out.append(f'<h3>How to get users</h3><p>{_e(dd.get("how_to_get_users"))}</p>')
    out.append("<h3>Competitors</h3><table><thead><tr><th>Name</th><th>What they do</th><th>Weakness</th></tr></thead><tbody>"
               + "".join(f"<tr><td>{_link(c.get('name'), c.get('url'))}</td><td>{_e(c.get('what_they_do'))}</td>"
                         f"<td>{_e(c.get('weakness'))}</td></tr>" for c in dd.get("competitors", []))
               + "</tbody></table>")
    out.append("<h3>Where to find the first users</h3><table><thead><tr><th>Place</th><th>Where</th>"
               "<th>Why there</th></tr></thead><tbody>"
               + "".join(f"<tr><td>{_link(p.get('name'), p.get('url'))}</td><td>{_e(p.get('where'))}</td>"
                         f"<td>{_e(p.get('why'))}</td></tr>" for p in dd.get("first_users", []))
               + "</tbody></table>")
    out.append("<h3>Risks</h3>" + _bullets(dd.get("risks")))
    out.append('<h3>Sources</h3><ul class="sources">' + "".join(
        f"<li>{_link(s.get('title'), s.get('url'))}</li>" for s in dd.get("sources", [])) + "</ul>")
    out.append("</section>")
    return "".join(out)


def render_report_html(report):
    names = report.get("region_names", {})
    stats = report["stats"]
    css = (Path(__file__).with_name("report.css")).read_text(encoding="utf-8")
    subtitle = [report["date_label"]]
    if report.get("theme"):
        subtitle.append(f"Theme: {report['theme']}")
    if report.get("quick"):
        subtitle.append("Quick run")

    parts = [f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>Business Hunt Report "
             f"{_e(report['run_id'])}</title><style>{css}</style></head><body>",
             f"<header><h1>Business Hunt Report</h1><p class=\"sub\">{_e(' · '.join(subtitle))}</p></header>",
             '<div class="stats">'
             f'<div><b>{_e(stats["regions"])}</b><span>regions searched</span></div>'
             f'<div><b>{_e(stats["cards"])}</b><span>findings</span></div>'
             f'<div><b>{_e(stats["clusters"])}</b><span>ideas after merging</span></div>'
             f'<div><b>{_e(stats["survivors"])}</b><span>survived the skeptic</span></div></div>']
    if report.get("failed_regions"):
        parts.append('<div class="callout warn">These regions failed in this run and are missing from the results: '
                     f'{_e(_region_list(report["failed_regions"], names))}.</div>')

    parts.append('<h2 class="section"><span class="num">1</span>Top ideas</h2>')
    if report["top"]:
        parts.append("<table><thead><tr><th>#</th><th>Idea</th><th>Score</th><th>Regions</th></tr></thead><tbody>"
                     + "".join(
                         f"<tr><td>{_e(i['rank'])}</td><td><strong>{_e(i.get('title'))}</strong> {_tags(i)}"
                         f"<br><span class=\"note\">{_e((i.get('deepdive') or {}).get('one_liner') or i.get('solution_idea'))}</span></td>"
                         f"<td class=\"num-cell\">{_e(i.get('score'))}</td>"
                         f"<td>{_e(_region_list(i.get('regions', []), names))}</td></tr>" for i in report["top"])
                     + "</tbody></table>")
    else:
        parts.append("<p>No idea survived scoring and the skeptic in this run.</p>")
    parts.append('<p class="note">Score is 0–100 across 8 checks. See “How this was scored” at the end.</p>')

    parts.append('<h2 class="section"><span class="num">2</span>What\'s new</h2>' + _render_changes(report["changes"]))

    for item in report["top"]:
        parts.append('<div class="pagebreak"></div>' + _render_deepdive(item, names))

    parts.append('<div class="pagebreak"></div><h2 class="section"><span class="num">3</span>Other candidates</h2>')
    if report["others"]:
        parts.append("<table><thead><tr><th>#</th><th>Idea</th><th>Score</th><th>Regions</th></tr></thead><tbody>"
                     + "".join(f"<tr><td>{_e(i['rank'])}</td><td>{_e(i.get('title'))} {_tags(i)}<br>"
                               f"<span class=\"note\">{_e(i.get('solution_idea'))}</span></td>"
                               f"<td class=\"num-cell\">{_e(i.get('score'))}</td>"
                               f"<td>{_e(_region_list(i.get('regions', []), names))}</td></tr>" for i in report["others"])
                     + "</tbody></table>")
    else:
        parts.append("<p>None.</p>")

    parts.append('<h2 class="section"><span class="num">4</span>Ideas that were cut</h2>')
    if report["excluded"]:
        parts.append("<table><thead><tr><th>Idea</th><th>Why it was cut</th></tr></thead><tbody>"
                     + "".join(f"<tr><td>{_e(i['title'])}</td><td>{_e(i['why'])}</td></tr>" for i in report["excluded"])
                     + "</tbody></table>")
    else:
        parts.append("<p>None.</p>")

    parts.append('<h2 class="section"><span class="num">5</span>Regional highlights</h2>')
    for region in report["regions"]:
        parts.append(f'<div class="region"><h3>{_e(region["name"])} <span class="note">'
                     f'({_e(region["card_count"])} findings)</span></h3>{_bullets(region.get("summary"))}</div>')

    parts.append('<h2 class="section"><span class="num">6</span>Sources</h2>')
    for group in report["sources"]:
        parts.append(f"<h3>{_e(group['region'])}</h3><ul class=\"sources\">" + "".join(
            f"<li>{_link(s.get('title'), s.get('url'))}</li>" for s in group["items"]) + "</ul>")

    parts.append('<h2 class="section"><span class="num">7</span>How this was scored</h2>'
                 "<p>Each idea is a digital subscription for $1–3 a month, for ordinary people or tiny "
                 "businesses anywhere in the world. It gets 1–5 on eight checks: needed every month, audience "
                 "size, proof people pay $1–3, competition gap, small-team buildability, cheap to run per user, "
                 "can find users without paid ads, and multi-region pull. The checks are weighted and turned "
                 "into a 0–100 score. "
                 f"Ideas the skeptic marks as weakened lose {round((1 - report.get('weakened_penalty', 0.85)) * 100)}%; "
                 "ideas it kills, and ideas that break a hard rule "
                 "(big-company software, good free tools already exist, hardware, licence-heavy, too costly to run "
                 "at $1–3), are cut.</p>"
                 '<p class="note">This is desk research by AI agents. Verify the key facts and talk to real users '
                 "in the places listed before you commit to an idea.</p>")
    parts.append("</body></html>")
    return "".join(parts)


# ---------------------------------------------------------------- PDF

def find_browser():
    override = os.environ.get("BH_BROWSER")
    if override and Path(override).exists():
        return override
    for candidate in BROWSER_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    for name in ("google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    return None


def print_pdf(html_path, pdf_path, browser):
    if not browser:
        raise RuntimeError("No Chrome-based browser found; install Google Chrome to create PDFs.")
    html_path, pdf_path = Path(html_path).resolve(), Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as profile:
        result = subprocess.run(
            [browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
             "--no-pdf-header-footer", f"--user-data-dir={profile}",
             f"--print-to-pdf={pdf_path}", html_path.as_uri()],
            capture_output=True, text=True, timeout=180)
    if not pdf_path.exists() or not pdf_path.read_bytes()[:4] == b"%PDF":
        raise RuntimeError(f"PDF was not created. Browser output:\n{result.stderr[-2000:]}")
    return pdf_path
