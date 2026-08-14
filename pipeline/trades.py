"""Trade inference and counterfactual analysis.

ESPN's transactions API redacts trade detail for completed seasons (only the
authed user's trades keep their player lists), so trades are inferred from the
weekly roster snapshots we archive: players crossing between the same two
teams in the same week transition, in both directions, constitute a trade.

The counterfactual for a deal compares each involved team's best-possible
lineup WITH its actual rosters against a world where the deal is reversed
(received players swapped back for sent players, at the sent players' real
weekly points wherever they ended up). Wins impact replays regular-season
matchups with that swing applied to the actual score — both sides adjusted
when the trade partners play each other.
"""

from collections import defaultdict

from pipeline.stats import optimal_points, regular_weeks, _sides


def rosters_by_week(season):
    """{week: {team_id: {player_id: player_entry}}} from box-score lineups."""
    out = {}
    for week_data in season["weeks"]:
        rosters = {}
        for tid, _, _, _, m in _sides(week_data):
            side = m["home"] if m["home"]["team_id"] == tid else m["away"]
            rosters[tid] = {
                p["id"]: p for p in side["lineup"] if p.get("id") is not None
            }
        out[week_data["week"]] = rosters
    return out


def _player_timeline(rosters):
    """{player_id: [(week, team_id, entry), ...]} in week order."""
    timeline = defaultdict(list)
    for week in sorted(rosters):
        for tid, players in rosters[week].items():
            for pid, entry in players.items():
                timeline[pid].append((week, tid, entry))
    return timeline


def _adds_and_drops(transactions):
    """Executed acquisition/relinquish paper: {player_id: [(sp, team)]}.

    Draft picks count as acquisitions, so draft-week churn never looks like a
    trade. Trade items are NOT included — ESPN redacts them for completed
    seasons, which is the entire reason inference exists.
    """
    adds, drops = defaultdict(list), defaultdict(list)
    for t in transactions or []:
        if t.get("status") != "EXECUTED":
            continue
        if t.get("type") not in ("FREEAGENT", "WAIVER", "ROSTER", "DRAFT"):
            continue
        sp = t.get("scoringPeriodId")
        for it in t.get("items", []):
            if it.get("type") in ("ADD", "DRAFT"):
                adds[it["playerId"]].append((sp, it.get("toTeamId")))
            elif it.get("type") == "DROP":
                drops[it["playerId"]].append((sp, it.get("fromTeamId")))
    return adds, drops


def detect_trades(season, transactions=None):
    """Find trades by reconciling roster snapshots against transaction paper.

    Every rule requires positive evidence — ESPN's transaction log for past
    seasons is lossy (drops can be missing entirely), so the absence of paper
    is never treated as proof of a trade. A trade leg is:

    - a player moving between snapshots with no covering ADD;
    - a paper acquisition never followed by a snapshot on that team — the
      player was flipped mid-week (added Wednesday, traded Thursday);
    - a DROP by a team that never rostered the player — traded in and cut
      on arrival.

    Legs cluster into deals by team pair within a 1-week window, and a deal
    always needs legs in both directions. Deals known only from outside
    evidence (league-feed screenshots) belong in trades_manual.json, merged
    by the build step — not here.
    """
    rosters = rosters_by_week(season)
    timeline = _player_timeline(rosters)
    adds, drops = _adds_and_drops(transactions)

    legs = []  # (effective_week, from_team, to_team, pid, entry)

    for pid, appearances in timeline.items():
        for (w1, t1, _), (w2, t2, entry) in zip(appearances, appearances[1:]):
            if t1 == t2:
                continue
            explained = any(
                team == t2 and w1 <= sp <= w2 for sp, team in adds.get(pid, [])
            )
            if not explained:
                legs.append((w2, t1, t2, pid, entry))

    if transactions:
        rostered_by = {
            pid: {t for _, t, _ in apps} for pid, apps in timeline.items()
        }

        # Paper acquisition with no snapshot on the acquiring team: the next
        # snapshot names the team the player was flipped to.
        for pid, add_list in adds.items():
            for sp, team in add_list:
                apps = timeline.get(pid, [])
                nxt = next((a for a in apps if a[0] >= sp), None)
                if nxt is None or nxt[1] == team:
                    continue
                week, actual_team, entry = nxt
                if any(t == team and sp <= s <= week for s, t in drops.get(pid, [])):
                    continue  # properly dropped again; the next add explains it
                if any(t == actual_team and sp <= s <= week
                       for s, t in adds.get(pid, [])):
                    continue  # the destination has its own paper
                legs.append((week, team, actual_team, pid, entry))

        # Drop by a team the player never played for: traded in, cut on arrival.
        for pid, drop_list in drops.items():
            for sp, team in drop_list:
                if team in rostered_by.get(pid, set()):
                    continue
                if any(t == team and abs(s - sp) <= 1 for s, t in adds.get(pid, [])):
                    continue  # added and dropped without appearing: churn
                prior = None
                for w, t, entry in timeline.get(pid, []):
                    if w <= sp:
                        prior = (t, entry)
                if prior is None or prior[0] == team:
                    continue
                legs.append((sp, prior[0], team, pid, prior[1]))

    by_pair = defaultdict(list)
    for leg in legs:
        by_pair[frozenset((leg[1], leg[2]))].append(leg)

    found = []
    for pair, moves in by_pair.items():
        moves.sort(key=lambda m: m[0])
        cluster = [moves[0]]
        for move in moves[1:]:
            if move[0] - cluster[-1][0] <= 1:
                cluster.append(move)
            else:
                found.append((pair, cluster))
                cluster = [move]
        found.append((pair, cluster))

    trades = []
    for pair, cluster in found:
        directions = {(src, dst) for _, src, dst, _, _ in cluster}
        if len(directions) < 2:
            continue  # one-way churn is never a trade, however it was papered
        a, b = sorted(pair)
        trades.append({
            "week": min(m[0] for m in cluster),
            "teams": [a, b],
            "moves": [
                {
                    "id": pid,
                    "name": entry["name"],
                    "position": entry["position"],
                    "from": src,
                    "to": dst,
                }
                for _, src, dst, pid, entry in cluster
            ],
        })
    trades.sort(key=lambda t: t["week"])
    return trades


def _entry_for(rosters, week, pid):
    """(team_id, entry) for a player in a given week, or None if unrostered."""
    for tid, players in rosters.get(week, {}).items():
        if pid in players:
            return tid, players[pid]
    return None


def _room_drops(rosters, drops, trade, tid, exclude_ids):
    """Drops attributable to making roster room for an unbalanced trade."""
    received = sum(1 for m in trade["moves"] if m["to"] == tid)
    sent = sum(1 for m in trade["moves"] if m["from"] == tid)
    net_in = received - sent
    if net_in <= 0:
        return []
    candidates = []
    for pid, drop_list in drops.items():
        if pid in exclude_ids:
            continue
        for sp, team in drop_list:
            if team == tid and abs(sp - trade["week"]) <= 1:
                candidates.append((abs(sp - trade["week"]), sp, pid))
    candidates.sort()
    out = []
    for _, sp, pid in candidates[:net_in]:
        entry = None
        for week in sorted(w for w in rosters if w <= sp):
            if pid in rosters[week].get(tid, {}):
                entry = rosters[week][tid][pid]
        if entry is not None:
            out.append({"id": pid, "name": entry["name"],
                        "position": entry["position"]})
    return out


def analyze_trade(season, trade, transactions=None):
    meta = season["meta"]
    slots = meta["starting_slots"]
    rosters = rosters_by_week(season)
    _, drops = _adds_and_drops(transactions)
    reg_week_numbers = {w["week"] for w in regular_weeks(season)}
    weeks_after = [w for w in sorted(rosters) if w >= trade["week"]]
    move_ids = {m["id"] for m in trade["moves"]}

    teams_out = []
    adjustments = {}  # team_id -> {week: without_opt - with_opt}
    for tid in trade["teams"]:
        received = [m for m in trade["moves"] if m["to"] == tid]
        sent = [m for m in trade["moves"] if m["from"] == tid]
        dropped = _room_drops(rosters, drops, trade, tid, move_ids)
        received_ids = {m["id"] for m in received}
        gap_weeks = []
        delta = 0.0
        adj = {}
        received_pts = defaultdict(float)
        returned_pts = defaultdict(float)  # sent + room-dropped players

        for week in weeks_after:
            roster = rosters[week].get(tid)
            if roster is None:
                continue  # no matchup that week (playoff bye)
            actual = list(roster.values())
            without = [p for p in actual if p["id"] not in received_ids]
            for m in sent + dropped:
                located = _entry_for(rosters, week, m["id"])
                if located is None:
                    gap_weeks.append(week)
                else:
                    without.append(located[1])
                    returned_pts[m["id"]] += located[1]["points"]
            for m in received:
                if m["id"] in roster:
                    received_pts[m["id"]] += roster[m["id"]]["points"]
            with_opt = optimal_points(actual, slots)
            without_opt = optimal_points(without, slots)
            delta += with_opt - without_opt
            adj[week] = without_opt - with_opt

        adjustments[tid] = adj

        def outbound(move):
            return {**{k: move[k] for k in ("id", "name", "position")},
                    "points_since": round(returned_pts[move["id"]], 2)}

        teams_out.append({
            "team_id": tid,
            "received": [
                {**{k: m[k] for k in ("id", "name", "position")},
                 "points_since": round(received_pts[m["id"]], 2)}
                for m in received
            ],
            "sent": [outbound(m) for m in sent],
            "dropped": [outbound(m) for m in dropped],
            "delta_fpts": round(delta, 2),
            "gap_weeks": sorted(set(gap_weeks)),
        })

    partner = {trade["teams"][0]: trade["teams"][1],
               trade["teams"][1]: trade["teams"][0]}
    for row in teams_out:
        tid = row["team_id"]
        wins_with = wins_without = 0
        for week_data in season["weeks"]:
            week = week_data["week"]
            if week < trade["week"] or week not in reg_week_numbers:
                continue
            for team, score, opp, opp_score, _ in _sides(week_data):
                if team != tid:
                    continue
                cf_score = score + adjustments[tid].get(week, 0.0)
                cf_opp = opp_score
                if opp == partner[tid]:
                    cf_opp += adjustments[opp].get(week, 0.0)
                if score > opp_score:
                    wins_with += 1
                if cf_score > cf_opp:
                    wins_without += 1
        row["wins_with"] = wins_with
        row["wins_without"] = wins_without

    ranked = sorted(teams_out, key=lambda r: -r["delta_fpts"])
    verdict = {
        "winner_id": ranked[0]["team_id"],
        "margin_fpts": round(ranked[0]["delta_fpts"] - ranked[-1]["delta_fpts"], 2),
    }
    return {"week": trade["week"], "teams": teams_out, "verdict": verdict}


def analyze_all(season, transactions=None, manual_trades=None):
    """Detect and analyze every trade, biggest total impact first.

    `manual_trades` are deals in the same {week, teams, moves} shape,
    established from evidence the API doesn't expose (league feed).
    """
    detected = detect_trades(season, transactions)
    for manual in manual_trades or []:
        if not any(t["teams"] == manual["teams"] and abs(t["week"] - manual["week"]) <= 1
                   for t in detected):
            detected.append(manual)
    detected.sort(key=lambda t: t["week"])
    results = [analyze_trade(season, t, transactions) for t in detected]
    results.sort(key=lambda r: -max(abs(t["delta_fpts"]) for t in r["teams"]))
    return results
