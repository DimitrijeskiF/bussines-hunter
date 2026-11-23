"""Renders a Launch Plan as HTML, ready to print to PDF.

Every value written by an agent is escaped, and every field is read defensively, so a
part that is missing or lean never breaks the page. Standard library only.
"""

from pathlib import Path

import hunt_lib as lib
from plan_lib import HEX_COLOR, PARTS

_e, _link, _bullets = lib._e, lib._link, lib._bullets

VERDICT_LABELS = {"start": "Start", "caution": "Start, with caution", "stop": "Do not start"}
CRITIC_LABELS = {"holds": "the plan holds", "needs_fixes": "the plan needs fixes", "broken": "the plan does not hold"}
SECTION_NAMES = {"product": "Product", "design": "Design", "build": "Build", "sales": "Sales",
                 "money": "Money and legal", "critic": "Critic", "roadmap": "Roadmap"}
PROFILE_LABELS = [("builder", "Who builds it"), ("hours_per_week", "Hours a week"),
                  ("budget_six_months", "Money for six months"), ("country", "Country"),
                  ("languages", "Languages"), ("goal", "Goal"), ("extra", "Also")]
CLOSING_NOTE = ("This is desk research by AI agents. Confirm legal and tax points with a local professional, "
                "and talk to real customers before you spend money.")


# ---------------------------------------------------------------- small helpers

def _items(doc, key):
    value = doc.get(key) if isinstance(doc, dict) else None
    return value if isinstance(value, list) else []


def _rows(doc, key):
    return [item for item in _items(doc, key) if isinstance(item, dict)]


def _obj(doc, key):
    value = doc.get(key) if isinstance(doc, dict) else None
    return value if isinstance(value, dict) else {}


def _table(headers, rows):
    """`rows` holds lists of ready HTML cells. Returns "" when there are no rows."""
    if not rows:
        return ""
    head = "".join(f"<th>{_e(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _numbered(items):
    if not items:
        return ""
    return "<ol>" + "".join(f"<li>{_e(i)}</li>" for i in items) + "</ol>"


def _not_checked(doc):
    items = _items(doc, "not_checked")
    if not items:
        return ""
    return f'<div class="notchecked"><h4>Not checked</h4>{_bullets(items)}</div>'


def _names(keys):
    return ", ".join(SECTION_NAMES.get(k, str(k)) for k in keys)


class _Sections:
    """Numbers the section headings in the order they are actually printed."""

    def __init__(self):
        self.count = 0

    def heading(self, title):
        self.count += 1
        return f'<h2 class="section"><span class="num">{self.count}</span>{_e(title)}</h2>'


# ---------------------------------------------------------------- top of the page

def _verdict_box(roadmap, critic):
    if not roadmap:
        extra = ""
        if critic:
            label = CRITIC_LABELS.get(critic.get("verdict"), critic.get("verdict"))
            extra = f"<p>The critic's verdict: {_e(label)}. {_e(critic.get('verdict_why'))}</p>"
        return ('<div class="verdict none"><span class="label">Verdict</span>'
                f"<strong>No verdict: the plan lead did not finish</strong>{extra}</div>")
    verdict = roadmap.get("verdict")
    css = verdict if verdict in VERDICT_LABELS else "none"
    return (f'<div class="verdict {css}"><span class="label">Verdict</span>'
            f"<strong>{_e(VERDICT_LABELS.get(verdict, 'No verdict'))}</strong>"
            f"<p>{_e(roadmap.get('verdict_why'))}</p></div>")


def _warnings(report, docs):
    out = []
    if report.get("left_out"):
        out.append(f'<div class="callout warn">Left out of this plan: {_e(_names(report["left_out"]))}. '
                   "An agent failed twice on each, so the plan was finished without them.</div>")
    if report.get("kept_earlier"):
        out.append('<div class="callout warn">Kept from before the critic\'s fixes: '
                   f'{_e(_names(report["kept_earlier"]))}. The fixed version did not pass the checks, '
                   "so the earlier version is shown.</div>")
    unchecked = [name for name, doc in docs.items() if _items(doc, "not_checked")]
    if unchecked:
        out.append(f'<div class="callout warn">Some points could not be checked in: {_e(_names(unchecked))}. '
                   "See the “Not checked” box in each of those sections.</div>")
    return "".join(out)


# ---------------------------------------------------------------- roadmap sections

def _summary(roadmap, stop):
    out = [f"<p>{_e(roadmap.get('summary'))}</p>"]
    if stop:
        out.append("<h3>What would change this</h3>" + _bullets(_items(roadmap, "what_would_change_this")))
    elif _items(roadmap, "this_week"):
        out.append('<h3>This week</h3><ul class="checklist">'
                   + "".join(f"<li>{_e(i)}</li>" for i in _items(roadmap, "this_week")) + "</ul>")
    out.append(_not_checked(roadmap))
    return "".join(out)


def _roadmap(roadmap, stages):
    out = []
    for n, row in enumerate(_rows(roadmap, "stages"), start=1):
        stage = stages.get(row.get("stage"), {})
        out.append(
            f'<div class="stage"><div class="stage-head"><span class="rank">{n}</span>'
            f'<h3>{_e(stage.get("name") or row.get("stage"))}</h3>'
            f'<span class="note">{_e(row.get("duration"))} · {_e(row.get("cost"))}</span></div>'
            f'<p><strong>Goal:</strong> {_e(stage.get("goal"))}</p>{_numbered(_items(row, "steps"))}'
            '<div class="grid2">'
            f'<div class="box"><h4>Continue when</h4><p>{_e(row.get("success_signal"))}</p></div>'
            f'<div class="box"><h4>Stop if</h4><p>{_e(row.get("stop_if"))}</p></div></div></div>')
    return "".join(out)


def _decisions(roadmap):
    rows = [[_e(d.get("question")), _bullets(_items(d, "options")), _e(d.get("suggestion"))]
            for d in _rows(roadmap, "decisions_for_you")]
    return _table(["Question", "Options", "Suggestion"], rows) or "<p>None before the first stage.</p>"


# ---------------------------------------------------------------- the five parts

def _product(doc, stages):
    market = _obj(doc, "first_market")
    rows = [[_e(s.get("name")), _e(s.get("goal")), _bullets(_items(s, "what_users_get")),
             _bullets(_items(s, "left_out")), _e(s.get("done_when")),
             "Yes" if s.get("needs_software") else "No"] for s in stages.values()]
    return (f'<p class="lead">{_e(doc.get("positioning"))}</p>'
            f'<div class="box"><h4>First market</h4><p><strong>{_e(market.get("where"))}</strong>: '
            f'{_e(market.get("who"))}</p><p>{_e(market.get("why"))}</p></div>'
            "<h3>The stages</h3>"
            + _table(["Stage", "Goal", "What users get", "Left out on purpose", "Done when", "Software"], rows)
            + "<h3>Questions only real users can answer</h3>" + _bullets(_items(doc, "questions_for_users"))
            + _not_checked(doc))


def _design(doc, stages):
    look = _obj(doc, "look")
    colors = []
    for color in _rows(look, "colors"):
        value = color.get("hex")
        swatch = (f'<span class="swatch" style="background:{value}"></span>'
                  if isinstance(value, str) and HEX_COLOR.match(value) else "")
        colors.append(f'<li>{swatch}<strong>{_e(color.get("name"))}</strong> ({_e(value)}): {_e(color.get("use"))}</li>')
    screens = []
    for screen in _rows(doc, "screens"):
        shape = "phone" if screen.get("kind") == "phone" else "wide"
        stage = stages.get(screen.get("stage"), {})
        screens.append(
            f'<div class="screen {shape}"><h4>{_e(screen.get("name"))}</h4>'
            f'<p class="note">{_e(screen.get("kind"))} · {_e(stage.get("name") or screen.get("stage"))}</p>'
            f'<p class="note">{_e(screen.get("purpose"))}</p>'
            '<ul class="elements">' + "".join(f"<li>{_e(el)}</li>" for el in _items(screen, "elements")) + "</ul>"
            f'<p class="action">{_e(screen.get("main_action"))}</p></div>')
    names = [[_e(n.get("name")), _e(n.get("why"))] for n in _rows(doc, "names")]
    return ("<h3>Principles</h3>" + _bullets(_items(doc, "principles"))
            + "<h3>Name ideas</h3>" + _table(["Name", "Why"], names)
            + f'<h3>Look</h3><p>{_e(look.get("tone"))}</p><p class="note">Font: {_e(look.get("font"))}</p>'
            + ('<ul class="swatches">' + "".join(colors) + "</ul>" if colors else "")
            + '<h3>Screens</h3><div class="screens">' + "".join(screens) + "</div>"
            + "<h3>A new user's first two minutes</h3>" + _numbered(_items(doc, "first_two_minutes"))
            + "<h3>Language notes</h3>" + _bullets(_items(doc, "language_notes"))
            + _not_checked(doc))


def _stage_name(stages, stage_id):
    return _e(stages.get(stage_id, {}).get("name") or stage_id)


def _build(doc, stages):
    tools = [[_link(t.get("name"), t.get("url")), _e(t.get("used_for")), _e(t.get("cost"))]
             for t in _rows(doc, "tools")]
    work = [[_stage_name(stages, r.get("stage")), _bullets(_items(r, "work")), _e(r.get("who")),
             _e(r.get("duration")), _e(r.get("one_time_cost"))] for r in _rows(doc, "per_stage")]
    costs = [[_e(c.get("item")), _e(c.get("monthly_cost")), _e(c.get("note"))] for c in _rows(doc, "running_costs")]
    return (f'<p class="lead">{_e(doc.get("approach"))}</p><p>{_e(doc.get("why_this_way"))}</p>'
            "<h3>Tools</h3>" + _table(["Tool", "Used for", "Cost"], tools)
            + "<h3>Work per stage</h3>" + _table(["Stage", "Work", "Who", "Duration", "One-time cost"], work)
            + "<h3>Running costs</h3>" + _table(["Item", "A month", "Note"], costs)
            + f'<p><strong>Total:</strong> {_e(doc.get("running_cost_total"))}</p>'
            + '<div class="box"><h4>Brief for the developer</h4>' + _bullets(_items(doc, "developer_brief")) + "</div>"
            + "<h3>Build risks</h3>" + _bullets(_items(doc, "risks"))
            + _not_checked(doc))


def _sales(doc, stages):
    local = _obj(doc, "pitch_local")
    prices = [[_stage_name(stages, p.get("stage")), _e(p.get("price")), _e(p.get("why"))]
              for p in _rows(doc, "price_steps")]
    channels = [[_e(c.get("name")), _e(c.get("how")), _e(c.get("cost")), _e(c.get("expected"))]
                for c in _rows(doc, "channels")]
    targets = [[_stage_name(stages, r.get("stage")), _e(r.get("target")), _bullets(_items(r, "actions"))]
               for r in _rows(doc, "per_stage")]
    days = [[_e(d.get("when")), _e(d.get("action"))] for d in _rows(doc, "first_30_days")]
    scripts = "".join(
        f'<div class="box"><h4>{_e(s.get("use"))}</h4><p class="quote">{_e(s.get("text_local"))}</p>'
        f'<p class="note">{_e(s.get("text_english"))}</p></div>' for s in _rows(doc, "scripts"))
    partners = [[_link(p.get("name"), p.get("url")), _e(p.get("why"))] for p in _rows(doc, "partners")]
    keeping = [[_e(k.get("reason_to_leave")), _e(k.get("what_we_do"))] for k in _rows(doc, "keeping_customers")]
    return (f'<p class="lead">{_e(doc.get("pitch"))}</p>'
            f'<p class="quote">{_e(local.get("text"))} <span class="note">({_e(local.get("language"))})</span></p>'
            "<h3>Price steps</h3>" + _table(["Stage", "Price", "Why"], prices)
            + "<h3>Where customers come from</h3>" + _table(["Channel", "How", "Cost", "Expected"], channels)
            + "<h3>Targets per stage</h3>" + _table(["Stage", "Target", "Actions"], targets)
            + "<h3>The first 30 days</h3>" + _table(["When", "Action"], days)
            + "<h3>Sample messages</h3>" + scripts
            + "<h3>Partners</h3>" + _table(["Organisation or group", "Why"], partners)
            + f'<h3>Customer support</h3><p>{_e(doc.get("support"))}</p>'
            + "<h3>Keeping customers</h3>" + _table(["Why they would leave", "What we do about it"], keeping)
            + _not_checked(doc))


def _money(doc, stages):
    check = _obj(doc, "budget_check")
    start = [[_e(c.get("item")), _e(c.get("amount")), _stage_name(stages, c.get("stage"))]
             for c in _rows(doc, "start_costs")]
    per_stage = [[_stage_name(stages, r.get("stage")), _e(r.get("paying_customers")), _e(r.get("income")),
                  _e(r.get("costs")), _e(r.get("result"))] for r in _rows(doc, "per_stage")]
    legal = [[_e(item.get("topic")), _e(item.get("what_to_do")), _stage_name(stages, item.get("when")),
              _e(item.get("who_to_ask"))] for item in _rows(doc, "legal")]
    fits = check.get("fits")
    budget = ("Fits your budget and hours" if fits is True
              else "Does not fit your budget and hours" if fits is False else "Budget check")
    return (f'<p class="note">Amounts in {_e(doc.get("currency"))}.</p>'
            "<h3>Assumptions</h3>" + _bullets(_items(doc, "assumptions"))
            + "<h3>Costs to start</h3>" + _table(["Item", "Amount", "Stage"], start)
            + "<h3>Money per stage, a month</h3>"
            + _table(["Stage", "Paying customers", "Income", "Costs", "Result"], per_stage)
            + f'<p><strong>Break-even:</strong> {_e(doc.get("break_even"))}</p>'
            + f'<div class="callout{"" if fits is not False else " warn"}"><strong>{budget}.</strong> '
              f'{_e(check.get("why"))}</div>'
            + "<h3>Legal checklist</h3>" + _table(["Topic", "What to do", "When", "Who to ask"], legal)
            + _not_checked(doc))


def _critic(critic, roadmap):
    resolved = {r.get("problem_id"): r.get("resolution") for r in _rows(roadmap, "resolved")}
    problems = [[_e(p.get("id")), _e(_names(_items(p, "parts"))), _e(p.get("problem")), _e(p.get("fix")),
                 _e(resolved.get(p.get("id")) or "Not settled")] for p in _rows(critic, "problems")]
    weak = [[_e(w.get("assumption")), _e(w.get("why_weak")), _e(w.get("how_to_test"))]
            for w in _rows(critic, "weak_assumptions")]
    label = CRITIC_LABELS.get(critic.get("verdict"), critic.get("verdict"))
    return (f'<p><strong>The critic says {_e(label)}.</strong> {_e(critic.get("verdict_why"))}</p>'
            "<h3>Problems and how they were settled</h3>"
            + (_table(["#", "Where", "Problem", "Suggested fix", "How it was settled"], problems)
               or "<p>The critic found no contradictions.</p>")
            + "<h3>Weak assumptions</h3>" + _table(["Assumption", "Why it is weak", "How to test it"], weak)
            + ("<h3>Missing from the plan</h3>" + _bullets(_items(critic, "missing"))
               if _items(critic, "missing") else "")
            + f'<p><strong>Biggest risk:</strong> {_e(critic.get("biggest_risk"))}</p>'
            + ("<h3>Open risks</h3>" + _bullets(_items(roadmap, "open_risks"))
               if _items(roadmap, "open_risks") else "")
            + _not_checked(critic))


def _profile_and_sources(report, docs):
    founder = report.get("founder") if isinstance(report.get("founder"), dict) else {}
    rows = [[_e(label), _e(founder.get(field))] for field, label in PROFILE_LABELS if founder.get(field)]
    out = ['<p class="note">The plan was built for this profile. If it has changed, tell Claude and plan again.</p>',
           _table(["About you", "Your answer"], rows)]
    if report.get("notes"):
        out.append(f'<p><strong>Your notes for this plan:</strong> {_e(report["notes"])}</p>')
    for name in PARTS:
        links = [s for s in _rows(docs.get(name), "sources")]
        if links:
            out.append(f"<h3>Sources: {_e(SECTION_NAMES[name])}</h3><ul class=\"sources\">" + "".join(
                f"<li>{_link(s.get('title'), s.get('url'))}</li>" for s in links) + "</ul>")
    out.append(f'<p class="note">{_e(CLOSING_NOTE)}</p>')
    return "".join(out)


# ---------------------------------------------------------------- the page

def render_plan_html(report):
    css = Path(__file__).with_name("report.css").read_text(encoding="utf-8")
    docs = {name: report.get(name) for name in PARTS + ["critic", "roadmap"]}
    product = docs["product"] if isinstance(docs["product"], dict) else {}
    roadmap, critic = docs["roadmap"], docs["critic"]
    stages = {s.get("id"): s for s in _rows(product, "stages")}
    stop = bool(roadmap) and roadmap.get("verdict") == "stop"
    sections = _Sections()

    subtitle = [report.get("date_label"), f"From the hunt of {report.get('source_run')}"]
    previous = report.get("previous")
    if previous:
        subtitle.append(f"Builds on the plan of {previous.get('date_label')}")
    parts = ["<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
             f"<title>Launch Plan {_e(report.get('plan_id'))}</title><style>{css}</style></head><body>",
             f"<header><h1>Launch Plan</h1><p class=\"sub\">{_e(report.get('title'))}</p>"
             f"<p class=\"note\">{_e(' · '.join(str(s) for s in subtitle if s))}</p></header>",
             f'<p class="lead">{_e(report.get("one_liner"))}</p>',
             _verdict_box(roadmap, critic),
             _warnings(report, docs)]

    if roadmap:
        parts.append(sections.heading("Summary") + _summary(roadmap, stop))
        if not stop:
            parts.append('<div class="pagebreak"></div>' + sections.heading("Roadmap") + _roadmap(roadmap, stages))
        parts.append(sections.heading("Decisions for you") + _decisions(roadmap))
    if stop:
        parts.append('<p class="lead reference">What the planners worked out, for reference</p>')

    parts.append('<div class="pagebreak"></div>' + sections.heading("Product") + _product(product, stages))
    for name, render in (("design", _design), ("build", _build), ("sales", _sales), ("money", _money)):
        if docs[name]:
            parts.append('<div class="pagebreak"></div>' + sections.heading(SECTION_NAMES[name])
                         + render(docs[name], stages))
    if critic:
        parts.append('<div class="pagebreak"></div>' + sections.heading("What the critic found")
                     + _critic(critic, roadmap))
    parts.append(sections.heading("Your profile and sources") + _profile_and_sources(report, docs))
    parts.append("</body></html>")
    return "".join(parts)
