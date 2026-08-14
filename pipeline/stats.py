"""Pure stat computations over a season of raw data.

A `season` is {"meta": <meta.json>, "weeks": [<week_NN.json>, ...]} with weeks
sorted ascending. All record/standings math uses regular-season weeks only;
playoff weeks feed the champion and matchup detail views.
"""

import math
from collections import defaultdict

from pipeline.config import BENCH_SLOTS, FLEX_ELIGIBLE


def regular_weeks(season):
    limit = season["meta"]["regular_season_weeks"]
    return [w for w in season["weeks"] if w["week"] <= limit and not w["is_playoff"]]


def playoff_weeks(season):
    return [w for w in season["weeks"] if w["is_playoff"]]


def team_ids(season):
    return [t["id"] for t in season["meta"]["teams"]]


def _sides(week_data):
    """Yield (team_id, score, opponent_id, opponent_score, matchup) per team-week."""
    for m in week_data["matchups"]:
        home, away = m["home"], m["away"]
        yield home["team_id"], home["score"], away["team_id"], away["score"], m
        yield away["team_id"], away["score"], home["team_id"], home["score"], m


# --- lineups ---

def optimal_points(lineup, slots):
    """Best possible score from a roster given the league's starting slots.

    Dedicated slots take the top scorers at their position; FLEX then takes the
    best remaining RB/WR/TE. IR players are not eligible.
    """
    available = [p for p in lineup if p["slot"] != "IR"]
    by_pos = defaultdict(list)
    for p in available:
        by_pos[p["position"]].append(p["points"])
    for pos in by_pos:
        by_pos[pos].sort(reverse=True)

    dedicated = defaultdict(int)
    flex_count = 0
    for slot in slots:
        if slot == "FLEX":
            flex_count += 1
        else:
            dedicated[slot] += 1

    total = 0.0
    for pos, count in dedicated.items():
        total += sum(by_pos[pos][:count])
        by_pos[pos] = by_pos[pos][count:]

    leftovers = sorted(
        (pts for pos in FLEX_ELIGIBLE for pts in by_pos[pos]), reverse=True
    )
    total += sum(leftovers[:flex_count])
    return round(total, 2)


def lineup_efficiency(season):
    """Per team over the regular season: actual vs optimal points and waste."""
    slots = season["meta"]["starting_slots"]
    out = {
        tid: {"actual": 0.0, "optimal": 0.0, "wasted": 0.0, "efficiency": None}
        for tid in team_ids(season)
    }
    for week_data in regular_weeks(season):
        for tid, score, _, _, m in _sides(week_data):
            side = m["home"] if m["home"]["team_id"] == tid else m["away"]
            if not side["lineup"]:
                continue
            optimal = optimal_points(side["lineup"], slots)
            out[tid]["actual"] += score
            out[tid]["optimal"] += optimal
            out[tid]["wasted"] += max(0.0, optimal - score)
    for row in out.values():
        row["actual"] = round(row["actual"], 2)
        row["optimal"] = round(row["optimal"], 2)
        row["wasted"] = round(row["wasted"], 2)
        if row["optimal"]:
            row["efficiency"] = round(row["actual"] / row["optimal"], 4)
    return out


# --- standings and results ---

def standings(season):
    rows = {
        tid: {
            "team_id": tid, "wins": 0, "losses": 0, "ties": 0,
            "points_for": 0.0, "points_against": 0.0,
        }
        for tid in team_ids(season)
    }
    for week_data in regular_weeks(season):
        for tid, score, _, opp_score, _ in _sides(week_data):
            row = rows[tid]
            row["points_for"] += score
            row["points_against"] += opp_score
            if score > opp_score:
                row["wins"] += 1
            elif score < opp_score:
                row["losses"] += 1
            else:
                row["ties"] += 1
    table = sorted(
        rows.values(), key=lambda r: (-r["wins"], -r["points_for"])
    )
    for i, row in enumerate(table, start=1):
        row["place"] = i
        row["points_for"] = round(row["points_for"], 2)
        row["points_against"] = round(row["points_against"], 2)
    return table


def place_by_week(season):
    """Standings place after each regular-season week, for rank-over-time charts."""
    weeks = regular_weeks(season)
    history = {tid: [] for tid in team_ids(season)}
    for i in range(1, len(weeks) + 1):
        partial = {
            "meta": season["meta"],
            "weeks": weeks[:i],
        }
        for row in standings(partial):
            history[row["team_id"]].append(row["place"])
    return history


def team_week_scores(season):
    """Chronological per-team results across all weeks (playoffs flagged)."""
    out = {tid: [] for tid in team_ids(season)}
    for week_data in season["weeks"]:
        for tid, score, opp, opp_score, m in _sides(week_data):
            result = "W" if score > opp_score else ("L" if score < opp_score else "T")
            out[tid].append({
                "week": week_data["week"],
                "points": score,
                "opponent_id": opp,
                "opponent_points": opp_score,
                "result": result,
                "margin": round(score - opp_score, 2),
                "is_playoff": week_data["is_playoff"],
            })
    return out


def allplay(season):
    """All-play record and luck. Luck = actual wins minus the wins you 'deserved'
    (each week's all-play wins divided by the field size)."""
    n = len(team_ids(season))
    out = {
        tid: {"allplay_wins": 0, "allplay_losses": 0, "luck": 0.0}
        for tid in team_ids(season)
    }
    expected = defaultdict(float)
    actual = defaultdict(int)
    for week_data in regular_weeks(season):
        scores = {tid: s for tid, s, _, _, _ in _sides(week_data)}
        for tid, score in scores.items():
            wins = sum(1 for other, s in scores.items() if other != tid and score > s)
            losses = sum(1 for other, s in scores.items() if other != tid and score < s)
            ties = len(scores) - 1 - wins - losses
            out[tid]["allplay_wins"] += wins
            out[tid]["allplay_losses"] += losses
            expected[tid] += (wins + 0.5 * ties) / (n - 1)
        for tid, score, _, opp_score, _ in _sides(week_data):
            if score > opp_score:
                actual[tid] += 1
    for tid in out:
        out[tid]["luck"] = actual[tid] - expected[tid]
    return out


def streaks(season):
    results = {tid: [] for tid in team_ids(season)}
    for week_data in regular_weeks(season):
        for tid, score, _, opp_score, _ in _sides(week_data):
            if score != opp_score:
                results[tid].append("W" if score > opp_score else "L")
    out = {}
    for tid, seq in results.items():
        longest = {"W": 0, "L": 0}
        run_kind, run_len = None, 0
        for r in seq:
            if r == run_kind:
                run_len += 1
            else:
                run_kind, run_len = r, 1
            longest[r] = max(longest[r], run_len)
        out[tid] = {
            "longest_win": longest["W"],
            "longest_loss": longest["L"],
            "current": {"kind": run_kind, "length": run_len} if run_kind else None,
        }
    return out


def h2h_matrix(season):
    ids = team_ids(season)
    matrix = {a: {b: (None if a == b else {"wins": 0, "losses": 0}) for b in ids} for a in ids}
    for week_data in regular_weeks(season):
        for tid, score, opp, opp_score, _ in _sides(week_data):
            if score > opp_score:
                matrix[tid][opp]["wins"] += 1
            elif score < opp_score:
                matrix[tid][opp]["losses"] += 1
    return matrix


# --- records and awards ---

def season_records(season):
    high, low, blowout, closest = None, None, None, None
    for week_data in regular_weeks(season):
        for tid, score, opp, opp_score, _ in _sides(week_data):
            entry = {"team_id": tid, "week": week_data["week"], "points": score}
            if high is None or score > high["points"]:
                high = entry
            if low is None or score < low["points"]:
                low = entry
            if score > opp_score:
                game = {
                    "week": week_data["week"],
                    "winner_id": tid,
                    "loser_id": opp,
                    "winner_points": score,
                    "loser_points": opp_score,
                    "margin": round(score - opp_score, 2),
                }
                if blowout is None or game["margin"] > blowout["margin"]:
                    blowout = game
                if closest is None or game["margin"] < closest["margin"]:
                    closest = game
    return {
        "highest_score": high,
        "lowest_score": low,
        "biggest_blowout": blowout,
        "closest_game": closest,
    }


def weekly_awards(season, week_data):
    """Awards for one week: extremes always; lineup-based awards when data allows."""
    slots = season["meta"]["starting_slots"]
    sides = list(_sides(week_data))
    if not sides:
        return {}
    top = max(sides, key=lambda s: s[1])
    bottom = min(sides, key=lambda s: s[1])
    awards = {
        "top_score": {"team_id": top[0], "points": top[1]},
        "low_score": {"team_id": bottom[0], "points": bottom[1]},
    }
    decided = [s for s in sides if s[1] > s[3]]
    if decided:
        blowout = max(decided, key=lambda s: s[1] - s[3])
        nailbiter = min(decided, key=lambda s: s[1] - s[3])
        awards["biggest_blowout"] = {
            "winner_id": blowout[0], "loser_id": blowout[2],
            "margin": round(blowout[1] - blowout[3], 2),
        }
        awards["nailbiter"] = {
            "winner_id": nailbiter[0], "loser_id": nailbiter[2],
            "margin": round(nailbiter[1] - nailbiter[3], 2),
        }
    wasted = []
    for tid, score, _, _, m in sides:
        side = m["home"] if m["home"]["team_id"] == tid else m["away"]
        if side["lineup"]:
            wasted.append((tid, optimal_points(side["lineup"], slots) - score))
    if wasted:
        worst = max(wasted, key=lambda w: w[1])
        awards["most_points_benched"] = {"team_id": worst[0], "points": round(worst[1], 2)}
    return awards


# --- playoffs ---

def final_week_number(season):
    meta = season["meta"]
    rounds = max(1, math.ceil(math.log2(meta["playoff_teams"]))) if meta["playoff_teams"] else 0
    return meta["regular_season_weeks"] + rounds


def champion(season):
    """Winner of the winners-bracket game in the season's final week.

    When the final week has several winners-bracket games (e.g. a third-place
    game tagged the same way), prefer the one whose participants both won
    winners-bracket games the week before.
    """
    final_week = final_week_number(season)
    week_data = next((w for w in playoff_weeks(season) if w["week"] == final_week), None)
    if week_data is None:
        return None
    finals = [m for m in week_data["matchups"] if m["bracket"] == "winners"]
    if not finals:
        return None
    if len(finals) > 1:
        prior = next(
            (w for w in playoff_weeks(season) if w["week"] == final_week - 1), None
        )
        if prior:
            prior_winners = set()
            for m in prior["matchups"]:
                if m["bracket"] == "winners":
                    h, a = m["home"], m["away"]
                    prior_winners.add(
                        h["team_id"] if h["score"] > a["score"] else a["team_id"]
                    )
            qualified = [
                m for m in finals
                if {m["home"]["team_id"], m["away"]["team_id"]} <= prior_winners
            ]
            if qualified:
                finals = qualified
    game = finals[0]
    h, a = game["home"], game["away"]
    winner = h if h["score"] > a["score"] else a
    return {"team_id": winner["team_id"], "week": final_week}
