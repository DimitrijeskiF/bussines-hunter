"""Builders for valid pipeline documents, used by the tests."""

REGIONS = ["europe", "latin_america", "north_america"]

CHECKS = ["pain_frequency", "audience_size", "willingness_to_pay", "competition_gap",
          "buildability", "cheap_to_run", "cheap_reach"]


def make_card(card_id="eu-01", title="Offline bus tickets"):
    return {
        "id": card_id,
        "title": title,
        "problem": "Commuters cannot check routes or buy tickets without mobile data.",
        "who_feels_it": {"group": "Daily commuters", "how_many": "About 10 million"},
        "gap_type": "missing_here",
        "why_now": "Cheap Android phones are now common",
        "lens": ["wishes", "local_gaps"],
        "evidence": [{"claim": "Commuters complain about data costs", "url": "https://example.com/thread"}],
        "existing_tools": [{"name": "AppX", "gap": "Needs a data connection"}],
        "subscription_case": "People commute every day, so they need it every month.",
        "countries": ["DE"],
        "solution_idea": "Offline-first ticket and timetable app.",
    }


def make_cards_doc(region="europe", n=2):
    prefix = region[:2]
    return {
        "region": region,
        "summary": ["Mobile-first habits drive most gaps here."],
        "cards": [make_card(f"{prefix}-{i:02d}", f"Idea {i}") for i in range(1, n + 1)],
    }


def make_cluster(cluster_id="offline-tickets", regions=("europe",), refs=("europe/eu-01",),
                 title="Offline bus tickets", arbitrage=None):
    return {
        "id": cluster_id,
        "title": title,
        "problem": "Commuters without data cannot check routes or buy tickets.",
        "solution_idea": "Offline-first ticket and timetable app.",
        "customer": "Daily commuters",
        "gap_type": "missing_here",
        "regions": list(regions),
        "patterns": {"global_pain": len(regions) >= 3, "arbitrage": arbitrage},
        "why_now": "Cheap Android phones",
        "subscription_case": "Daily need, so people keep paying.",
        "card_refs": list(refs),
        "evidence": [{"claim": "Commuters complain about data costs", "url": "https://example.com/thread"}],
    }


def make_score(cluster_id, value=4, rejected=False, reason=None):
    entry = {"id": cluster_id, "hard_filter": {"rejected": rejected, "reason": reason}}
    if not rejected:
        entry["checks"] = {key: {"score": value, "why": "reason"} for key in CHECKS}
    return entry


def make_verdict(cluster_id, verdict="survives"):
    return {
        "id": cluster_id,
        "verdict": verdict,
        "big_tech_risk": "low",
        "incumbents": [],
        "reasons": ["No free alternative found."],
        "what_would_change_my_mind": "Google Maps adding offline tickets.",
    }


def make_deepdive(cluster_id="offline-tickets", places=10):
    return {
        "id": cluster_id,
        "title": "Offline bus tickets",
        "one_liner": "Bus tickets and timetables that work without mobile data.",
        "competitors": [{"name": "AppX", "url": "https://appx.example", "what_they_do": "Online tickets (free)", "weakness": "Needs data"}],
        "customer": {"who": "Daily commuters", "where": "Nairobi, Lagos", "pain_in_their_words": "No data, no ticket."},
        "mvp": {"scope": ["Offline timetable", "SMS ticket"], "time_to_build": "2-3 months", "team": "1 developer"},
        "pricing": {"model": "Monthly with free tier", "price": "$1.50 a month", "rationale": "Below one bus fare."},
        "unit_economics": {"cost_per_user": "$0.05 a month", "users_needed": "About 9,000 paying users for $10,000 a month"},
        "how_to_get_users": "Posters at stations plus word of mouth.",
        "first_users": [
            {"name": f"Commuter group {i}", "where": "Facebook", "why": "Riders discuss routes"}
            for i in range(1, places + 1)
        ],
        "risks": ["Google Maps could add it."],
        "sources": [{"title": "Commuter survey", "url": "https://example.com/survey"}],
    }


def make_rubric(top_n=2, penalty=0.85, weights=None):
    return {
        "top_n": top_n,
        "weakened_penalty": penalty,
        "weights": weights or {key: 1.0 for key in CHECKS + ["multi_region"]},
    }


# ---------------------------------------------------------------- launch plan builders

def make_ranked_item(idea_id="offline-tickets", rank=1, top=True, title="Offline bus tickets", score=81.5):
    """An entry of ranked.json: the cluster plus rank, score, checks and the skeptic's verdict."""
    item = make_cluster(idea_id, title=title)
    item.update({"rank": rank, "top": top, "score": score, "verdict": "survives",
                 "checks": {key: {"score": 4, "why": "reason"} for key in CHECKS + ["multi_region"]},
                 "skeptic": make_verdict(idea_id)})
    return item


def make_run_entry(run_id, finished_at, ranked=(), excluded=()):
    """A run as plan.py loads it: run id, folder, finish time and the content of ranked.json."""
    return {"run_id": run_id, "run_dir": f"/tmp/runs/{run_id}", "finished_at": finished_at,
            "ranked": {"top_n": 5, "weakened_penalty": 0.85, "ranked": list(ranked), "excluded": list(excluded)}}


PLAN_STAGES = ["prove-demand", "pilot", "paid-version"]


def make_profile():
    return {"builder": "Me alone; I cannot code", "hours_per_week": "10", "budget_six_months": "2,000 EUR",
            "country": "Kenya", "languages": "English, Swahili", "goal": "Side income"}


def make_product(idea_id="offline-tickets", stages=PLAN_STAGES):
    return {
        "id": idea_id,
        "positioning": "For daily commuters without data: tickets and timetables that work offline.",
        "first_market": {"where": "Nairobi", "who": "Minibus commuters", "why": "Deep dive found the most demand here."},
        "stages": [{"id": stage, "name": f"Stage {i}: {stage}", "goal": "Learn whether riders pay.",
                    "needs_software": i > 1, "what_users_get": ["A weekly timetable by SMS"],
                    "left_out": ["Ticket sales"], "done_when": "20 riders pay for a second month"}
                   for i, stage in enumerate(stages, start=1)],
        "questions_for_users": ["How do you check routes today?", "What did you pay last month?",
                                "Who decides which app you use?"],
        "not_checked": [],
    }


def make_design(idea_id="offline-tickets", stages=PLAN_STAGES):
    return {
        "id": idea_id,
        "principles": ["Works on a cheap Android phone", "One action per screen"],
        "names": [{"name": f"Name {i}", "why": "Short and easy to say"} for i in range(1, 4)],
        "look": {"tone": "Friendly and plain", "font": "System font",
                 "colors": [{"name": "Blue", "hex": "#2F6FDB", "use": "Buttons"},
                            {"name": "Ink", "hex": "#1d2129", "use": "Text"}]},
        "screens": [{"name": f"Screen {i}", "kind": kind, "stage": stages[0], "purpose": "Show today's routes",
                     "elements": ["Title", "List of routes"], "main_action": "Pick a route"}
                    for i, kind in enumerate(["page", "document", "phone", "phone"], start=1)],
        "first_two_minutes": ["Open the link", "Pick your route"],
        "language_notes": ["English and Swahili, left to right"],
        "not_checked": [],
    }


def make_build(idea_id="offline-tickets", stages=PLAN_STAGES):
    return {
        "id": idea_id,
        "approach": "A hand-run SMS list first, then a small web app.",
        "why_this_way": "The founder cannot code and has 10 hours a week.",
        "tools": [{"name": "Google Sheets", "used_for": "Rider list", "cost": "Free", "url": "https://sheets.google.com"}],
        "per_stage": [{"stage": stage, "work": ["Set up the rider list"], "who": "Founder",
                       "duration": "3 weeks", "one_time_cost": "0"} for stage in stages],
        "running_costs": [{"item": "SMS", "monthly_cost": "15 EUR"}],
        "running_cost_total": "About 15 EUR a month",
        "developer_brief": ["Works offline", "SMS fallback", "No app store in stage 2"],
        "risks": ["SMS prices change"],
        "not_checked": [],
    }


def make_sales(idea_id="offline-tickets", stages=PLAN_STAGES):
    return {
        "id": idea_id,
        "pitch": "Your bus times, even without data.",
        "pitch_local": {"language": "Swahili", "text": "Ratiba ya basi, hata bila data."},
        "price_steps": [{"stage": stages[0], "price": "Free", "why": "Proves interest first"}],
        "channels": [{"name": f"Channel {i}", "how": "Posters at stops", "cost": "10 EUR", "expected": "20 riders"}
                     for i in range(1, 4)],
        "per_stage": [{"stage": stage, "target": "20 riders", "actions": ["Talk to riders at two stops"]}
                      for stage in stages],
        "first_30_days": [{"when": f"Week {i}", "action": "Visit one stop"} for i in range(1, 5)],
        "scripts": [{"use": "First message", "text_local": "Habari", "text_english": "Hello"},
                    {"use": "Follow-up", "text_local": "Asante", "text_english": "Thank you"}],
        "partners": [{"name": f"Commuter group {i}", "why": "Riders gather here"} for i in range(1, 4)],
        "support": "The founder answers by WhatsApp within a day.",
        "keeping_customers": [{"reason_to_leave": "Timetable is wrong", "what_we_do": "Weekly check with drivers"},
                              {"reason_to_leave": "Forgot to renew", "what_we_do": "Reminder two days before"}],
        "not_checked": [],
    }


def make_money(idea_id="offline-tickets", stages=PLAN_STAGES):
    return {
        "id": idea_id,
        "currency": "EUR",
        "assumptions": ["Price is 1.50 a month", "One in five trial riders pays"],
        "start_costs": [{"item": "Posters", "amount": "30", "stage": stages[0]}],
        "per_stage": [{"stage": stage, "paying_customers": "20", "income": "30", "costs": "15", "result": "+15"}
                      for stage in stages],
        "break_even": "10 paying riders cover the running costs.",
        "budget_check": {"fits": True, "why": "Stage costs stay under 2,000 EUR."},
        "legal": [{"topic": topic, "what_to_do": "Confirm the rule", "when": stages[0], "who_to_ask": "A local accountant"}
                  for topic in ("Company form", "Tax", "Personal data")],
        "not_checked": [],
    }


def make_critic(idea_id="offline-tickets", verdict="needs_fixes", problems=None):
    if problems is None:
        problems = [
            {"id": "c1", "parts": ["build", "sales"], "problem": "Build plans SMS only; sales promises WhatsApp.",
             "fix": "Use SMS in both until stage 3.", "fix_in": ["build"]},
            {"id": "c2", "parts": ["product"], "problem": "Stage 2 has no measurable result.",
             "fix": "Give it a number of paying riders.", "fix_in": []},
        ]
    return {
        "id": idea_id, "verdict": verdict, "verdict_why": "Two points need work.", "problems": problems,
        "weak_assumptions": [{"assumption": "One in five trial riders pays", "why_weak": "No evidence yet",
                              "how_to_test": "Ask for payment in stage 1"}],
        "missing": [], "biggest_risk": "Riders will not pay.", "not_checked": [],
    }


def make_roadmap(idea_id="offline-tickets", stages=PLAN_STAGES, verdict="caution", resolved=("c1", "c2")):
    stop = verdict == "stop"
    return {
        "id": idea_id, "verdict": verdict, "verdict_why": "The first stage is cheap; the rest depends on it.",
        "summary": "Start with a hand-run SMS timetable for 20 riders.",
        "stages": [] if stop else [
            {"stage": stage, "duration": "3 weeks", "cost": "30 EUR",
             "steps": ["Talk to 20 riders", "Ask for payment"],
             "success_signal": "10 riders pay", "stop_if": "Fewer than 3 riders pay"} for stage in stages],
        "this_week": [] if stop else ["Visit two stops", "Print posters", "Draft the first SMS"],
        "what_would_change_this": ["A bus company agrees to share its timetable"] if stop else [],
        "decisions_for_you": [{"question": "Start in one city or two?", "options": ["One", "Two"],
                               "suggestion": "One"}],
        "resolved": [{"problem_id": pid, "resolution": "Settled in the roadmap."} for pid in resolved],
        "open_risks": ["Riders will not pay."], "not_checked": [],
    }
