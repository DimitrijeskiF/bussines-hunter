"""Deterministic parts of the Launch Plan command.

Planning agents write JSON files. This module reads the owner's arguments, finds the
idea in past hunts and checks the agents' files. `plan_report.py` renders the PDF and
`plan.py` is the command line. Standard library only.
"""

import re

import hunt_lib as lib


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
