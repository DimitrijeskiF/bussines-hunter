"""Deterministic parts of the Launch Plan command.

Planning agents write JSON files. This module reads the owner's arguments, finds the
idea in past hunts and checks the agents' files. `plan_report.py` renders the PDF and
`plan.py` is the command line. Standard library only.
"""

import re

import hunt_lib as lib

PARTS = ["product", "design", "build", "sales", "money"]
FIXABLE = ["design", "build", "sales", "money"]  # parts the critic may send back for fixes
SCREEN_KINDS = {"phone", "page", "document"}
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
PROFILE_QUESTIONS = [
    ("builder", "Who will build the product? (you, and can you code; developers you can use; "
                "someone you would hire or partner with)"),
    ("hours_per_week", "How many hours a week can you give it?"),
    ("budget_six_months", "How much money can you put in during the first six months?"),
    ("country", "Which country are you in?"),
    ("languages", "Which languages do you speak?"),
    ("goal", "What do you want from it: side income, a full-time business, or to build and sell?"),
]


# ---------------------------------------------------------------- arguments

def parse_plan_args(raw):
    """Parse '/launch-plan' arguments: a rank or idea id, free-text notes, optional --fresh."""
    text = (raw or "").strip()
    if text.startswith("[") and text.endswith("]") and not re.search(r"[\[\]]", text[1:-1]):
        text = text[1:-1].strip()
    words = text.split()
    result = {"rank": None, "idea_id": None, "notes": None, "fresh": "--fresh" in words}
    words = [w for w in words if w != "--fresh"]
    if not words:
        return result
    ref = words[0].strip("#[]").rstrip(".")
    if ref.isascii() and ref.isdigit():
        result["rank"] = int(ref)
    elif lib.SLUG.match(ref):
        result["idea_id"] = ref
    else:
        raise ValueError(f"Which idea should be planned? Give its rank (for example 1) or its id, "
                         f"not {words[0]!r}.")
    result["notes"] = " ".join(words[1:]).strip() or None
    return result


# ---------------------------------------------------------------- finding the idea

def _finished(runs):
    """Finished runs, newest first."""
    done = [r for r in runs if r.get("finished_at") and isinstance(r.get("ranked"), dict)]
    return sorted(done, key=lambda r: r["finished_at"], reverse=True)


def latest_run(runs):
    done = _finished(runs)
    return done[0] if done else None


def top_ideas(runs):
    """The top ideas of the latest finished run, for the owner to pick from."""
    run = latest_run(runs)
    if not run:
        return None
    return {"run_id": run["run_id"],
            "ideas": [{"rank": i.get("rank"), "id": i.get("id"), "title": i.get("title"), "score": i.get("score")}
                      for i in run["ranked"].get("ranked", []) if i.get("top")]}


def find_idea(runs, rank=None, idea_id=None):
    """Return {"run", "item"} for a rank in the latest run or an id in the newest run that mentions it."""
    done = _finished(runs)
    if not done:
        raise LookupError("No finished hunt found. Run /hunt first, then plan one of its ideas.")
    if rank is not None:
        run = done[0]
        items = run["ranked"].get("ranked", [])
        for item in items:
            if item.get("rank") == rank:
                return {"run": run, "item": item}
        raise LookupError(f"The latest hunt ({run['run_id']}) has no idea ranked #{rank}; "
                          f"it ranked {len(items)} ideas.")
    for run in done:
        for item in run["ranked"].get("ranked", []):
            if item.get("id") == idea_id:
                return {"run": run, "item": item}
        for item in run["ranked"].get("excluded", []):
            if item.get("id") == idea_id:
                raise LookupError(f"The hunt of {run['run_id']} cut this idea ({idea_id}): {item.get('why')}")
    raise LookupError(f"No finished hunt has an idea with the id {idea_id!r}.")


def previous_plan(plans, idea_id):
    """The newest finished plan for the same idea, or None."""
    done = [p for p in plans if p.get("idea_id") == idea_id and p.get("finished_at")]
    return max(done, key=lambda p: p["finished_at"]) if done else None


def pdf_name(date, title, taken):
    """'<date> Launch Plan - <title>.pdf', numbered when that name is already used."""
    clean = re.sub(r"[^\w \-]", "", title or "").strip()[:50].strip()
    base = f"{date} Launch Plan - {clean}" if clean else f"{date} Launch Plan"
    name, n = f"{base}.pdf", 2
    while name in taken:
        name, n = f"{base} ({n}).pdf", n + 1
    return name


# ---------------------------------------------------------------- validation helpers

def _common(doc, idea_id, errors):
    """Checks shared by every plan file. Returns False when the file is not an object."""
    if not lib._root(doc, errors):
        return False
    if doc.get("id") != idea_id:
        errors.append(f"id: expected {idea_id!r}, got {doc.get('id')!r}")
    lib._text_list(doc, "not_checked", "file", errors)
    if doc.get("sources") is not None:
        lib._links(doc, "sources", "file", errors, "title", min_len=0)
    return True


def _objects(obj, key, path, errors, text_keys=(), min_len=0, max_len=None):
    """Check a list of objects. Returns (path, item) for every item that is an object."""
    items = lib._list(obj, key, path, errors, min_len)
    if max_len is not None and len(items) > max_len:
        errors.append(f"{path}.{key}: allows at most {max_len} item(s), has {len(items)}")
    prefix = key if path == "file" else f"{path}.{key}"
    good = []
    for i, item in enumerate(items):
        item_path = f"{prefix}[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{item_path}: must be an object")
            continue
        for text_key in text_keys:
            lib._text(item, text_key, item_path, errors)
        good.append((item_path, item))
    return good


def _optional_url(item, path, errors):
    if item.get("url") is not None and not lib.safe_url(item.get("url")):
        errors.append(f"{path}.url: must be an http(s) link or omitted")


def _stage_ref(item, key, path, stages, errors):
    if item.get(key) not in stages:
        errors.append(f"{path}.{key}: must be one of the product stages ({', '.join(stages)}), "
                      f"got {item.get(key)!r}")


def _per_stage(doc, stages, errors, text_keys):
    """`per_stage` must hold exactly one entry per product stage, in the same order."""
    rows = _objects(doc, "per_stage", "file", errors, text_keys)
    got = [item.get("stage") for _, item in rows]
    if got != list(stages):
        errors.append(f"file.per_stage: needs exactly one entry per product stage, in order "
                      f"({', '.join(stages)}); got {got!r}")
    return rows


# ---------------------------------------------------------------- profile and part validators

def validate_profile(doc):
    errors = []
    if not lib._root(doc, errors):
        return errors
    for field, _question in PROFILE_QUESTIONS:
        lib._text(doc, field, "profile", errors)
    if doc.get("extra") is not None and not lib._is_text(doc.get("extra")):
        errors.append("profile.extra: must be text, null or left out")
    return errors


def stage_ids(product):
    """The stage ids of a product part, in order. Tolerates a malformed file."""
    if not isinstance(product, dict) or not isinstance(product.get("stages"), list):
        return []
    return [s["id"] for s in product["stages"] if isinstance(s, dict) and lib._is_text(s.get("id"))]


def validate_product(doc, idea_id):
    errors = []
    if not _common(doc, idea_id, errors):
        return errors
    lib._text(doc, "positioning", "file", errors)
    market = lib._dict(doc, "first_market", "file", errors)
    for key in ("where", "who", "why"):
        lib._text(market, key, "first_market", errors)

    stages = _objects(doc, "stages", "file", errors, ("id", "name", "goal", "done_when"))
    raw = doc.get("stages") if isinstance(doc.get("stages"), list) else None
    if raw is not None and not 3 <= len(raw) <= 5:
        errors.append(f"file.stages: needs 3 to 5 stages, has {len(raw)}")
    seen = set()
    for path, stage in stages:
        stage_id = stage.get("id")
        if lib._is_text(stage_id):
            if not lib.SLUG.match(stage_id):
                errors.append(f"{path}.id: must be a lowercase slug like 'prove-demand', got {stage_id!r}")
            if stage_id in seen:
                errors.append(f"{path}.id: duplicate stage id {stage_id!r}")
            seen.add(stage_id)
        if not isinstance(stage.get("needs_software"), bool):
            errors.append(f"{path}.needs_software: must be true or false")
        lib._text_list(stage, "what_users_get", path, errors, min_len=1)
        lib._text_list(stage, "left_out", path, errors)
    if raw and isinstance(raw[0], dict) and raw[0].get("needs_software") is True:
        errors.append("stages[0].needs_software: the first stage must prove demand before any software "
                      "is built, so it must be false")
    lib._text_list(doc, "questions_for_users", "file", errors, min_len=3)
    return errors


def validate_design(doc, idea_id, stages):
    errors = []
    if not _common(doc, idea_id, errors):
        return errors
    lib._text_list(doc, "principles", "file", errors, min_len=2)
    _objects(doc, "names", "file", errors, ("name", "why"), min_len=3)
    look = lib._dict(doc, "look", "file", errors)
    lib._text(look, "tone", "look", errors)
    lib._text(look, "font", "look", errors)
    for path, color in _objects(look, "colors", "look", errors, ("name", "use"), min_len=2, max_len=6):
        if not (isinstance(color.get("hex"), str) and HEX_COLOR.match(color["hex"])):
            errors.append(f"{path}.hex: must look like #1A2B3C, got {color.get('hex')!r}")
    for path, screen in _objects(doc, "screens", "file", errors, ("name", "purpose", "main_action"), min_len=4):
        kind = screen.get("kind")
        if not (isinstance(kind, str) and kind in SCREEN_KINDS):
            errors.append(f"{path}.kind: must be one of {', '.join(sorted(SCREEN_KINDS))}, got {kind!r}")
        _stage_ref(screen, "stage", path, stages, errors)
        lib._text_list(screen, "elements", path, errors, min_len=2)
    lib._text_list(doc, "first_two_minutes", "file", errors, min_len=2)
    lib._text_list(doc, "language_notes", "file", errors, min_len=1)
    return errors


def validate_build(doc, idea_id, stages):
    errors = []
    if not _common(doc, idea_id, errors):
        return errors
    lib._text(doc, "approach", "file", errors)
    lib._text(doc, "why_this_way", "file", errors)
    for path, tool in _objects(doc, "tools", "file", errors, ("name", "used_for", "cost"), min_len=1):
        _optional_url(tool, path, errors)
    for path, row in _per_stage(doc, stages, errors, ("who", "duration", "one_time_cost")):
        lib._text_list(row, "work", path, errors, min_len=1)
    for path, cost in _objects(doc, "running_costs", "file", errors, ("item", "monthly_cost"), min_len=1):
        if cost.get("note") is not None and not lib._is_text(cost.get("note")):
            errors.append(f"{path}.note: must be text or omitted")
    lib._text(doc, "running_cost_total", "file", errors)
    lib._text_list(doc, "developer_brief", "file", errors, min_len=3)
    lib._text_list(doc, "risks", "file", errors, min_len=1)
    return errors


def validate_sales(doc, idea_id, stages):
    errors = []
    if not _common(doc, idea_id, errors):
        return errors
    lib._text(doc, "pitch", "file", errors)
    local = lib._dict(doc, "pitch_local", "file", errors)
    lib._text(local, "language", "pitch_local", errors)
    lib._text(local, "text", "pitch_local", errors)
    for path, step in _objects(doc, "price_steps", "file", errors, ("price", "why"), min_len=1):
        _stage_ref(step, "stage", path, stages, errors)
    _objects(doc, "channels", "file", errors, ("name", "how", "cost", "expected"), min_len=3)
    for path, row in _per_stage(doc, stages, errors, ("target",)):
        lib._text_list(row, "actions", path, errors, min_len=1)
    _objects(doc, "first_30_days", "file", errors, ("when", "action"), min_len=4)
    _objects(doc, "scripts", "file", errors, ("use", "text_local", "text_english"), min_len=2)
    for path, partner in _objects(doc, "partners", "file", errors, ("name", "why"), min_len=3):
        _optional_url(partner, path, errors)
    lib._text(doc, "support", "file", errors)
    _objects(doc, "keeping_customers", "file", errors, ("reason_to_leave", "what_we_do"), min_len=2)
    return errors


def validate_money(doc, idea_id, stages):
    errors = []
    if not _common(doc, idea_id, errors):
        return errors
    lib._text(doc, "currency", "file", errors)
    lib._text_list(doc, "assumptions", "file", errors, min_len=2)
    for path, cost in _objects(doc, "start_costs", "file", errors, ("item", "amount"), min_len=1):
        _stage_ref(cost, "stage", path, stages, errors)
    _per_stage(doc, stages, errors, ("paying_customers", "income", "costs", "result"))
    lib._text(doc, "break_even", "file", errors)
    check = lib._dict(doc, "budget_check", "file", errors)
    if not isinstance(check.get("fits"), bool):
        errors.append("budget_check.fits: must be true or false")
    lib._text(check, "why", "budget_check", errors)
    for path, item in _objects(doc, "legal", "file", errors, ("topic", "what_to_do", "who_to_ask"), min_len=3):
        _stage_ref(item, "when", path, stages, errors)
    return errors


PART_VALIDATORS = {"design": validate_design, "build": validate_build,
                   "sales": validate_sales, "money": validate_money}
