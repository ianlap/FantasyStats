import pytest

from pipeline.cumulative import aggregate


def season_payload(season, teams, champion_id=None, records=None, h2h=None, trades=None):
    return {
        "season": season,
        "league_name": f"League {season}",
        "demo": False,
        "teams": teams,
        "champion": {"team_id": champion_id, "week": 17} if champion_id else None,
        "records": records or {},
        "h2h": h2h or {},
        "trades": trades or [],
    }


def team(tid, name, **kw):
    base = {
        "id": tid, "name": name, "abbrev": name[:3].upper(), "owner": f"o{tid}",
        "place": 1, "wins": 0, "losses": 0, "ties": 0,
        "points_for": 0.0, "points_against": 0.0,
        "allplay_wins": 0, "allplay_losses": 0, "luck": 0.0,
        "optimal_points": 0.0, "points_benched": 0.0, "efficiency": None,
        "playoff_wins": 1, "playoff_losses": 1, "playoff_pf": 100.0,
        "playoff_pa": 100.0, "playoff_games": 2, "final_standing": None,
    }
    base.update(kw)
    return base


@pytest.fixture
def payloads():
    s1 = season_payload(
        2025,
        [
            team(1, "Alpha", place=1, wins=10, losses=4, points_for=1500.0,
                 points_against=1300.0, allplay_wins=100, allplay_losses=54,
                 luck=1.5, optimal_points=1800.0, points_benched=300.0,
                 efficiency=0.8333, final_standing=1),
            team(2, "Bravo", place=2, wins=4, losses=10, points_for=1200.0,
                 points_against=1400.0, allplay_wins=54, allplay_losses=100,
                 luck=-1.5, optimal_points=1500.0, points_benched=300.0,
                 efficiency=0.8),
        ],
        champion_id=1,
        records={"highest_score": {"team_id": 1, "week": 3, "points": 180.0}},
        h2h={1: {2: {"wins": 2, "losses": 0}}, 2: {1: {"wins": 0, "losses": 2}}},
        trades=[{"week": 5, "teams": [], "verdict": {}}],
    )
    s2 = season_payload(
        2026,
        [
            # Same franchise id 1, renamed and under a new owner.
            team(1, "Alpha Reborn", owner="newguy", place=2, wins=6, losses=8,
                 points_for=1400.0, points_against=1450.0, allplay_wins=70,
                 allplay_losses=84, luck=0.5, optimal_points=1600.0,
                 points_benched=200.0, efficiency=0.875),
            team(2, "Bravo", place=1, wins=8, losses=6, points_for=1450.0,
                 points_against=1400.0, allplay_wins=84, allplay_losses=70,
                 luck=-0.5, optimal_points=1500.0, points_benched=50.0,
                 efficiency=0.9667),
        ],
        champion_id=2,
        records={"highest_score": {"team_id": 2, "week": 7, "points": 190.0}},
        h2h={1: {2: {"wins": 1, "losses": 1}}, 2: {1: {"wins": 1, "losses": 1}}},
        trades=[{"week": 2, "teams": [], "verdict": {}}],
    )
    return [s1, s2]


def test_franchise_totals_and_latest_identity(payloads):
    cum = aggregate(payloads)
    one = next(t for t in cum["teams"] if t["id"] == 1)
    assert one["name"] == "Alpha Reborn" and one["owner"] == "newguy"
    assert (one["wins"], one["losses"]) == (16, 12)
    assert one["points_for"] == pytest.approx(2900.0)
    assert one["allplay_wins"] == 170
    assert one["luck"] == pytest.approx(2.0)
    assert one["points_benched"] == pytest.approx(500.0)
    assert one["playoff_games"] == 4
    assert one["playoff_pf"] == pytest.approx(200.0)


def test_efficiency_is_weighted_not_averaged(payloads):
    cum = aggregate(payloads)
    one = next(t for t in cum["teams"] if t["id"] == 1)
    assert one["efficiency"] == pytest.approx(2900.0 / 3400.0, abs=1e-4)


def test_titles_and_finishes(payloads):
    cum = aggregate(payloads)
    one = next(t for t in cum["teams"] if t["id"] == 1)
    two = next(t for t in cum["teams"] if t["id"] == 2)
    assert one["titles"] == 1 and two["titles"] == 1
    assert [f["season"] for f in one["finishes"]] == [2025, 2026]
    assert one["finishes"][0]["champion"] is True
    assert one["finishes"][0]["final"] == 1
    assert cum["champions"] == [
        {"season": 2025, "team_id": 1}, {"season": 2026, "team_id": 2},
    ]


def test_alltime_ranking_by_win_pct(payloads):
    cum = aggregate(payloads)
    # Franchise 1: 16-12 (.571); franchise 2: 12-16 (.429).
    assert [t["id"] for t in cum["teams"]] == [1, 2]
    assert cum["teams"][0]["place"] == 1


def test_records_tagged_with_season(payloads):
    cum = aggregate(payloads)
    rec = cum["records"]["highest_score"]
    assert rec["points"] == 190.0 and rec["season"] == 2026


def test_h2h_summed(payloads):
    cum = aggregate(payloads)
    assert cum["h2h"][1][2] == {"wins": 3, "losses": 1}


def test_trades_tagged_and_flag_set(payloads):
    cum = aggregate(payloads)
    assert cum["cumulative"] is True
    assert cum["seasons"] == [2025, 2026]
    assert {t["season"] for t in cum["trades"]} == {2025, 2026}
