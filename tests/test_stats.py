import pytest

from pipeline import stats

SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "D/ST", "K"]


def player(name, pos, slot, pts):
    return {"name": name, "position": pos, "slot": slot, "points": pts, "projected": pts}


def matchup(home_id, home_score, away_id, away_score, bracket=None):
    return {
        "bracket": bracket,
        "home": {"team_id": home_id, "score": home_score, "lineup": []},
        "away": {"team_id": away_id, "score": away_score, "lineup": []},
    }


def week(n, matchups, is_playoff=False):
    return {"season": 2025, "week": n, "is_playoff": is_playoff, "matchups": matchups}


META = {
    "season": 2025,
    "league_id": 1,
    "league_name": "Test League",
    "regular_season_weeks": 3,
    "playoff_teams": 2,
    "starting_slots": SLOTS,
    "teams": [
        {"id": 1, "name": "Alpha", "abbrev": "ALP", "owner": "A"},
        {"id": 2, "name": "Bravo", "abbrev": "BRV", "owner": "B"},
        {"id": 3, "name": "Charlie", "abbrev": "CHA", "owner": "C"},
        {"id": 4, "name": "Delta", "abbrev": "DEL", "owner": "D"},
    ],
}

# 3 regular-season weeks, 4 teams. Scores chosen so results are easy to verify.
WEEKS = [
    week(1, [matchup(1, 100, 2, 90), matchup(3, 80, 4, 70)]),
    week(2, [matchup(1, 110, 3, 95), matchup(2, 60, 4, 85)]),
    week(3, [matchup(1, 50, 4, 120), matchup(2, 105, 3, 100)]),
]


@pytest.fixture
def season():
    return {"meta": META, "weeks": WEEKS}


class TestOptimalLineup:
    def test_flex_takes_best_leftover(self):
        # Started RB2 (5) over WR3 (20 on bench): optimal puts the 20-pt WR in FLEX.
        lineup = [
            player("QB1", "QB", "QB", 20),
            player("RB1", "RB", "RB", 15),
            player("RB2", "RB", "RB", 5),
            player("WR1", "WR", "WR", 12),
            player("WR2", "WR", "WR", 10),
            player("TE1", "TE", "TE", 8),
            player("RB3", "RB", "FLEX", 6),
            player("DST", "D/ST", "D/ST", 7),
            player("K1", "K", "K", 9),
            player("WR3", "WR", "BE", 20),
        ]
        actual = sum(p["points"] for p in lineup if p["slot"] != "BE")
        assert actual == 92
        # Optimal: QB 20, RBs 15+6, WRs 20+12, TE 8, FLEX WR2 10, DST 7, K 9 = 107
        assert stats.optimal_points(lineup, SLOTS) == 107

    def test_ir_players_excluded(self):
        lineup = [
            player("QB1", "QB", "QB", 10),
            player("QB2", "QB", "IR", 99),
        ]
        assert stats.optimal_points(lineup, ["QB"]) == 10

    def test_empty_slot_stays_empty_when_no_eligible_player(self):
        lineup = [player("QB1", "QB", "QB", 10)]
        assert stats.optimal_points(lineup, SLOTS) == 10


class TestStandings:
    def test_records_and_points(self, season):
        table = stats.standings(season)
        by_id = {row["team_id"]: row for row in table}
        assert (by_id[1]["wins"], by_id[1]["losses"]) == (2, 1)
        assert (by_id[4]["wins"], by_id[4]["losses"]) == (2, 1)
        assert (by_id[2]["wins"], by_id[2]["losses"]) == (1, 2)
        assert (by_id[3]["wins"], by_id[3]["losses"]) == (1, 2)
        assert by_id[1]["points_for"] == 260
        assert by_id[1]["points_against"] == 305

    def test_ties_broken_by_points_for(self, season):
        table = stats.standings(season)
        # Teams 1 and 4 are both 2-1; team 4 has 275 PF vs team 1's 260.
        assert [row["team_id"] for row in table[:2]] == [4, 1]
        assert table[0]["place"] == 1


class TestAllPlay:
    def test_allplay_and_luck(self, season):
        ap = stats.allplay(season)
        # Week 1 scores: 1:100, 2:90, 3:80, 4:70 -> team1 beats all 3
        # Week 2 scores: 1:110, 3:95, 2:60, 4:85 -> team1 beats all 3
        # Week 3 scores: 4:120, 2:105, 3:100, 1:50 -> team1 beats none
        assert ap[1]["allplay_wins"] == 6
        assert ap[1]["allplay_losses"] == 3
        # Team 2: wk1 beats 80,70 -> 2; wk2 beats none -> 0; wk3 beats 100,50 -> 2
        assert ap[2]["allplay_wins"] == 4
        # Luck = actual wins - expected wins (allplay_wins / (n-1))
        assert ap[1]["luck"] == pytest.approx(2 - 6 / 3)
        assert ap[2]["luck"] == pytest.approx(1 - 4 / 3)

    def test_luck_sums_to_zero(self, season):
        ap = stats.allplay(season)
        assert sum(t["luck"] for t in ap.values()) == pytest.approx(0)


class TestStreaks:
    def test_longest_and_current(self, season):
        s = stats.streaks(season)
        assert s[1]["longest_win"] == 2
        assert s[1]["current"] == {"kind": "L", "length": 1}
        assert s[4]["longest_win"] == 2
        assert s[4]["current"] == {"kind": "W", "length": 2}


class TestRecords:
    def test_extremes(self, season):
        r = stats.season_records(season)
        assert r["highest_score"]["points"] == 120
        assert r["highest_score"]["team_id"] == 4
        assert r["lowest_score"]["points"] == 50
        assert r["biggest_blowout"]["margin"] == 70
        assert r["closest_game"]["margin"] == 5


class TestWeeklyAwards:
    def test_top_and_bottom(self, season):
        awards = stats.weekly_awards(season, WEEKS[0])
        assert awards["top_score"]["team_id"] == 1
        assert awards["low_score"]["team_id"] == 4


class TestH2H:
    def test_matrix(self, season):
        h2h = stats.h2h_matrix(season)
        assert h2h[1][2] == {"wins": 1, "losses": 0}
        assert h2h[4][1] == {"wins": 1, "losses": 0}
        assert h2h[1][1] is None


class TestChampion:
    def test_champion_from_winners_bracket(self):
        meta = dict(META, regular_season_weeks=1)
        playoff_weeks = [
            week(1, [matchup(1, 100, 2, 90), matchup(3, 80, 4, 70)]),
            week(2, [matchup(1, 100, 3, 90, bracket="winners"),
                     matchup(2, 100, 4, 110, bracket="consolation")], is_playoff=True),
        ]
        season = {"meta": meta, "weeks": playoff_weeks}
        assert stats.champion(season) == {"team_id": 1, "week": 2}

    def test_no_champion_mid_season(self, season):
        assert stats.champion(season) is None
