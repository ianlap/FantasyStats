import pytest

from pipeline import trades

SLOTS = ["QB", "RB"]


def player(pid, name, pos, slot, pts):
    return {"id": pid, "name": name, "position": pos, "slot": slot,
            "points": pts, "projected": pts}


def side(team_id, lineup):
    return {
        "team_id": team_id,
        "score": round(sum(p["points"] for p in lineup if p["slot"] not in ("BE", "IR")), 2),
        "lineup": lineup,
    }


def week(n, sides, is_playoff=False):
    matchups = [
        {"bracket": None, "home": sides[i], "away": sides[i + 1]}
        for i in range(0, len(sides), 2)
    ]
    return {"season": 2025, "week": n, "is_playoff": is_playoff, "matchups": matchups}


META = {
    "season": 2025, "league_id": 1, "league_name": "T", "demo": False,
    "regular_season_weeks": 3, "playoff_teams": 2, "starting_slots": SLOTS,
    "teams": [
        {"id": 1, "name": "One", "abbrev": "ONE", "owner": "a"},
        {"id": 2, "name": "Two", "abbrev": "TWO", "owner": "b"},
        {"id": 3, "name": "Three", "abbrev": "THR", "owner": "c"},
        {"id": 4, "name": "Four", "abbrev": "FOU", "owner": "d"},
    ],
}


def build_season():
    """Week 1->2: p11 (team1 QB) and p21 (team2 QB) swap = a trade.
    Also churn noise: team3 drops p32 for waiver pickup p33 (one-directional).
    """
    w1 = week(1, [
        side(1, [player(11, "Alpha QB", "QB", "QB", 20), player(12, "A RB", "RB", "RB", 10)]),
        side(2, [player(21, "Beta QB", "QB", "QB", 15), player(22, "B RB", "RB", "RB", 8)]),
        side(3, [player(31, "C QB", "QB", "QB", 12), player(32, "C RB", "RB", "RB", 6)]),
        side(4, [player(41, "D QB", "QB", "QB", 11), player(42, "D RB", "RB", "RB", 7)]),
    ])
    # After the trade: p21 on team1, p11 on team2. p32 gone, p33 arrives on team3.
    w2 = week(2, [
        side(1, [player(21, "Beta QB", "QB", "QB", 30), player(12, "A RB", "RB", "RB", 10)]),
        side(2, [player(11, "Alpha QB", "QB", "QB", 5), player(22, "B RB", "RB", "RB", 12)]),
        side(3, [player(31, "C QB", "QB", "QB", 9), player(33, "C RB2", "RB", "RB", 4)]),
        side(4, [player(41, "D QB", "QB", "QB", 14), player(42, "D RB", "RB", "RB", 3)]),
    ])
    w3 = week(3, [
        side(1, [player(21, "Beta QB", "QB", "QB", 25), player(12, "A RB", "RB", "RB", 9)]),
        side(2, [player(11, "Alpha QB", "QB", "QB", 22), player(22, "B RB", "RB", "RB", 2)]),
        side(3, [player(31, "C QB", "QB", "QB", 13), player(33, "C RB2", "RB", "RB", 8)]),
        side(4, [player(41, "D QB", "QB", "QB", 10), player(42, "D RB", "RB", "RB", 12)]),
    ])
    return {"meta": META, "weeks": [w1, w2, w3]}


@pytest.fixture
def season():
    return build_season()


class TestDetectTrades:
    def test_finds_the_swap_and_ignores_churn(self, season):
        found = trades.detect_trades(season)
        assert len(found) == 1
        t = found[0]
        assert t["week"] == 2
        assert sorted(t["teams"]) == [1, 2]
        moves = {(m["id"], m["from"], m["to"]) for m in t["moves"]}
        assert moves == {(11, 1, 2), (21, 2, 1)}

    def test_no_trades_in_quiet_season(self, season):
        # Remove the swap by keeping original rosters in weeks 2-3.
        for w in season["weeks"][1:]:
            w["matchups"][0]["home"]["lineup"][0] = player(11, "Alpha QB", "QB", "QB", 30)
            w["matchups"][0]["away"]["lineup"][0] = player(21, "Beta QB", "QB", "QB", 5)
        assert trades.detect_trades(season) == []

    def test_multi_player_same_pair_is_one_trade(self, season):
        # Also swap the RBs between teams 1 and 2 in the same window.
        w2, w3 = season["weeks"][1], season["weeks"][2]
        for w in (w2, w3):
            w["matchups"][0]["home"]["lineup"][1] = player(22, "B RB", "RB", "RB", 6)
            w["matchups"][0]["away"]["lineup"][1] = player(12, "A RB", "RB", "RB", 11)
        found = trades.detect_trades(season)
        assert len(found) == 1
        assert len(found[0]["moves"]) == 4


def txn(txn_type, sp, items):
    return {
        "type": txn_type, "status": "EXECUTED", "scoringPeriodId": sp,
        "items": [
            {"type": t, "playerId": pid, "fromTeamId": src, "toTeamId": dst}
            for t, pid, src, dst in items
        ],
    }


class TestTransactionFiltering:
    def test_waiver_explained_crossing_is_not_a_trade(self, season):
        # The 11/21 "swap" was really: both dropped, each claimed the other's
        # castoff on waivers. ADD transactions explain both movements.
        transactions = [
            txn("WAIVER", 2, [("ADD", 21, 0, 1), ("DROP", 11, 1, 0)]),
            txn("WAIVER", 2, [("ADD", 11, 0, 2), ("DROP", 21, 2, 0)]),
        ]
        assert trades.detect_trades(season, transactions) == []

    def test_real_trade_survives_unrelated_waivers(self, season):
        transactions = [
            txn("WAIVER", 2, [("ADD", 33, 0, 3), ("DROP", 32, 3, 0)]),
        ]
        found = trades.detect_trades(season, transactions)
        assert len(found) == 1
        assert sorted(found[0]["teams"]) == [1, 2]

    def test_added_wednesday_traded_thursday(self, season):
        # Team 3 claims p34 midweek and flips him to team 4 before he ever
        # appears in a team-3 snapshot. His week-2 arrival at team 4 has no
        # team-4 paper, so the leg is 3 -> 4; team 4's p42 goes back visibly.
        w2, w3 = season["weeks"][1], season["weeks"][2]
        for w in (w2, w3):
            w["matchups"][1]["away"]["lineup"][1] = player(34, "Flipped RB", "RB", "RB", 9)
            w["matchups"][1]["home"]["lineup"][1] = player(42, "D RB", "RB", "RB", 5)
        # (test season: matchups[1] pairs team 3 (home) and team 4 (away))
        transactions = [
            txn("WAIVER", 2, [("ADD", 34, 0, 3)]),
        ]
        found = trades.detect_trades(season, transactions)
        pairs = {tuple(t["teams"]) for t in found}
        assert (3, 4) in pairs
        deal = next(t for t in found if tuple(t["teams"]) == (3, 4))
        moves = {(m["id"], m["from"], m["to"]) for m in deal["moves"]}
        assert (34, 3, 4) in moves and (42, 4, 3) in moves

    def test_paperless_disappearance_is_not_evidence(self, season):
        # p12 vanishes from team 1 after week 1 with no drop transaction.
        # ESPN's log is lossy, so a missing drop must read as churn, not trade.
        for w in season["weeks"][1:]:
            w["matchups"][0]["home"]["lineup"][1] = player(14, "Pickup RB", "RB", "RB", 3)
        transactions = [
            txn("WAIVER", 2, [("ADD", 14, 0, 1)]),
        ]
        found = trades.detect_trades(season, transactions)
        assert {tuple(t["teams"]) for t in found} == {(1, 2)}  # only the real swap

    def test_invisible_leg_synthesized_from_unexplained_drop(self, season):
        # Team 2 receives p11 but drops him before he ever appears in a
        # box score for team 2: weeks 2-3 show p11 nowhere. The only trace is
        # team 2's DROP transaction with no matching ADD.
        for w in season["weeks"][1:]:
            w["matchups"][0]["away"]["lineup"][0] = player(23, "Waiver QB", "QB", "QB", 7)
        transactions = [
            txn("ROSTER", 2, [("DROP", 11, 2, 0)]),
            txn("WAIVER", 2, [("ADD", 23, 0, 2)]),
        ]
        found = trades.detect_trades(season, transactions)
        assert len(found) == 1
        t = found[0]
        assert sorted(t["teams"]) == [1, 2]
        moves = {(m["id"], m["from"], m["to"]) for m in t["moves"]}
        assert (11, 1, 2) in moves and (21, 2, 1) in moves


class TestAnalyzeTrade:
    def test_deltas_and_verdict(self, season):
        trade = trades.detect_trades(season)[0]
        result = trades.analyze_trade(season, trade)
        one = next(r for r in result["teams"] if r["team_id"] == 1)
        two = next(r for r in result["teams"] if r["team_id"] == 2)

        # Team 1 optimal WITH (has Beta QB): wk2 30+10=40, wk3 25+9=34.
        # WITHOUT (Alpha QB back): wk2 5+10=15, wk3 22+9=31.
        assert one["delta_fpts"] == pytest.approx((40 - 15) + (34 - 31))  # +28
        # Team 2 mirror: WITH wk2 5+12=17, wk3 22+2=24; WITHOUT wk2 30+12=42, wk3 25+2=27.
        assert two["delta_fpts"] == pytest.approx((17 - 42) + (24 - 27))  # -28
        assert result["verdict"]["winner_id"] == 1

    def test_wl_swing_with_partner_matchup(self, season):
        # Weeks 2 and 3 team1 plays team2 directly, so both sides adjust.
        trade = trades.detect_trades(season)[0]
        result = trades.analyze_trade(season, trade)
        one = next(r for r in result["teams"] if r["team_id"] == 1)
        two = next(r for r in result["teams"] if r["team_id"] == 2)
        # Actual: wk2 team1 40-17 W, wk3 team1 34-24 W -> 2 wins.
        # Counterfactual: wk2 15-42 L, wk3 31-27 W -> 1 win.
        assert one["wins_with"] == 2 and one["wins_without"] == 1
        assert two["wins_with"] == 0 and two["wins_without"] == 1

    def test_room_making_drop_joins_the_counterfactual(self, season):
        # Make it 2-for-1: team 1 also sends its RB (12) to team 2, receiving
        # only Beta QB — so team 2 (net +1) drops its own RB (22) for room.
        w2, w3 = season["weeks"][1], season["weeks"][2]
        for w, rb_pts in ((w2, 11), (w3, 5)):
            w["matchups"][0]["home"]["lineup"][1] = player(13, "Street RB", "RB", "RB", 2)
            w["matchups"][0]["away"]["lineup"][1] = player(12, "A RB", "RB", "RB", rb_pts)
        transactions = [
            txn("ROSTER", 2, [("DROP", 22, 2, 0)]),
        ]
        found = trades.detect_trades(season, transactions)
        assert len(found) == 1
        result = trades.analyze_trade(season, found[0], transactions)
        two = next(r for r in result["teams"] if r["team_id"] == 2)
        assert [d["id"] for d in two["dropped"]] == [22]
        # Team 2 WITH: wk2 5+11=16, wk3 22+5=27. WITHOUT (Beta QB + own RB 22
        # back, but 22 is unrostered after the drop so contributes 0):
        # wk2 30+0=30, wk3 25+0=25.
        assert two["delta_fpts"] == pytest.approx((16 - 30) + (27 - 25))

    def test_sent_player_disappears_counts_zero(self, season):
        # Alpha QB (11) vanishes from all rosters in week 3 (team2 dropped him).
        w3 = season["weeks"][2]
        w3["matchups"][0]["away"]["lineup"][0] = player(23, "Waiver QB", "QB", "QB", 22)
        trade = trades.detect_trades(season)[0]
        result = trades.analyze_trade(season, trade)
        one = next(r for r in result["teams"] if r["team_id"] == 1)
        # Team 1 WITHOUT in wk3 loses Alpha's points entirely: optimal 9 vs with 34.
        assert one["delta_fpts"] == pytest.approx((40 - 15) + (34 - 9))
        assert 3 in one["gap_weeks"]
