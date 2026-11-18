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
