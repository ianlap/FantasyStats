"""End-to-end: fixture season -> assemble -> the schema the frontend relies on."""

import pytest

from pipeline import fixtures
from pipeline.build import assemble

TEAM_KEYS = {
    "id", "name", "abbrev", "owner", "wins", "losses", "ties", "place",
    "points_for", "points_against", "allplay_wins", "allplay_losses", "luck",
    "longest_win", "longest_loss", "current_streak", "optimal_points",
    "points_benched", "efficiency", "weekly", "places",
}


@pytest.fixture(scope="module")
def payload():
    meta, weeks = fixtures.generate()
    return assemble({"meta": meta, "weeks": weeks})


def test_team_schema_and_ordering(payload):
    assert len(payload["teams"]) == 10
    for team in payload["teams"]:
        assert TEAM_KEYS <= set(team)
    assert [t["place"] for t in payload["teams"]] == list(range(1, 11))


def test_records_totals(payload):
    teams = payload["teams"]
    total_wins = sum(t["wins"] for t in teams)
    total_losses = sum(t["losses"] for t in teams)
    assert total_wins == total_losses == 5 * 14  # 5 games x 14 reg weeks


def test_full_season_shape(payload):
    assert len(payload["weeks"]) == 17
    assert [w["week"] for w in payload["weeks"]] == list(range(1, 18))
    assert all(w["is_playoff"] == (w["week"] > 14) for w in payload["weeks"])
    assert payload["demo"] is True


def test_champion_exists_and_played_the_final(payload):
    champ = payload["champion"]
    assert champ is not None and champ["week"] == 17
    final = [
        m for m in payload["weeks"][-1]["matchups"] if m["bracket"] == "winners"
    ]
    assert len(final) == 1
    assert champ["team_id"] in (
        final[0]["home"]["team_id"], final[0]["away"]["team_id"]
    )


def test_lineups_and_efficiency_populated(payload):
    for team in payload["teams"]:
        assert team["efficiency"] is not None
        assert 0.5 < team["efficiency"] <= 1.0
        assert team["points_benched"] >= 0
        # 14 regular season entries at minimum; playoff entries allowed on top.
        assert len([w for w in team["weekly"] if not w["is_playoff"]]) == 14
        assert len(team["places"]) == 14


def test_weekly_awards_present(payload):
    for week in payload["weeks"]:
        assert "top_score" in week["awards"]
        assert "most_points_benched" in week["awards"]


def test_luck_zero_sum(payload):
    assert sum(t["luck"] for t in payload["teams"]) == pytest.approx(0, abs=0.05)


def test_trades_key_present(payload):
    # The fixture season has no trades; the key must still exist for the site.
    assert payload["trades"] == []
