"""Merge per-season site payloads into an all-time (cumulative) payload.

Franchises are keyed by ESPN team id — a team keeps its history across
renames and owner changes, matching how ESPN treats the league. Efficiency
is recomputed from summed points (actual / optimal), never averaged.
"""

from collections import defaultdict

SUMMED = [
    "wins", "losses", "ties", "points_for", "points_against",
    "allplay_wins", "allplay_losses", "luck",
    "optimal_points", "points_benched",
    "playoff_wins", "playoff_losses", "playoff_pf", "playoff_pa",
    "playoff_games",
]

RECORD_KEYS = {
    "highest_score": ("points", max),
    "lowest_score": ("points", min),
    "biggest_blowout": ("margin", max),
    "closest_game": ("margin", min),
}


def aggregate(payloads):
    """payloads: per-season site payloads, ascending by season."""
    payloads = sorted(payloads, key=lambda p: p["season"])
    latest = payloads[-1]

    franchises = {}
    for payload in payloads:
        champ_id = (payload.get("champion") or {}).get("team_id")
        for t in payload["teams"]:
            row = franchises.setdefault(t["id"], {
                "id": t["id"],
                **{k: 0 for k in SUMMED},
                "titles": 0,
                "finishes": [],
            })
            # Latest season wins the display identity.
            row["name"] = t["name"]
            row["abbrev"] = t["abbrev"]
            row["owner"] = t["owner"]
            for k in SUMMED:
                row[k] += t[k] or 0
            is_champ = t["id"] == champ_id
            row["titles"] += 1 if is_champ else 0
            row["finishes"].append({
                "season": payload["season"],
                "place": t["place"],
                "final": t.get("final_standing"),
                "wins": t["wins"], "losses": t["losses"], "ties": t["ties"],
                "champion": is_champ,
            })
            # Game-level results power the all-time head-to-head drill-down.
            row.setdefault("games", []).extend(
                {**g, "season": payload["season"]} for g in t.get("weekly", [])
            )

    teams = list(franchises.values())
    for row in teams:
        for k in ("points_for", "points_against", "luck",
                  "optimal_points", "points_benched",
                  "playoff_pf", "playoff_pa"):
            row[k] = round(row[k], 2)
        row["efficiency"] = (
            round(row["points_for"] / row["optimal_points"], 4)
            if row["optimal_points"] else None
        )
        row["current_streak"] = None
    teams.sort(key=lambda r: (
        -(r["wins"] / max(1, r["wins"] + r["losses"] + r["ties"])),
        -r["points_for"],
    ))
    for i, row in enumerate(teams, start=1):
        row["place"] = i

    records = {}
    for key, (field, best) in RECORD_KEYS.items():
        candidates = [
            {**payload["records"][key], "season": payload["season"]}
            for payload in payloads
            if payload["records"].get(key)
        ]
        if candidates:
            records[key] = best(candidates, key=lambda c: c[field])

    h2h = defaultdict(lambda: defaultdict(lambda: None))
    for payload in payloads:
        for a, opponents in payload["h2h"].items():
            for b, rec in opponents.items():
                if rec is None:
                    continue
                a_id, b_id = int(a), int(b)
                if h2h[a_id][b_id] is None:
                    h2h[a_id][b_id] = {"wins": 0, "losses": 0}
                h2h[a_id][b_id]["wins"] += rec["wins"]
                h2h[a_id][b_id]["losses"] += rec["losses"]

    trades = [
        {**trade, "season": payload["season"]}
        for payload in payloads
        for trade in payload.get("trades", [])
    ]

    return {
        "cumulative": True,
        "seasons": [p["season"] for p in payloads],
        "league_name": latest["league_name"],
        "demo": any(p.get("demo") for p in payloads),
        "generated_at": latest.get("generated_at"),
        "teams": teams,
        "champions": [
            {"season": p["season"], "team_id": p["champion"]["team_id"]}
            for p in payloads if p.get("champion")
        ],
        "records": records,
        "h2h": {a: dict(b) for a, b in h2h.items()},
        "trades": trades,
    }
