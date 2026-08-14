"""League constants and credential loading.

Raw data schema (data/raw/<season>/):

meta.json
    season, league_id, league_name, regular_season_weeks, playoff_teams,
    starting_slots (e.g. ["QB","RB","RB","WR","WR","TE","FLEX","D/ST","K"]),
    teams: [{id, name, abbrev, owner}]

week_NN.json
    season, week, is_playoff,
    matchups: [{
        bracket: null | "winners" | "consolation",
        home: {team_id, score, lineup: [{id, name, position, slot, points, projected}]},
        away: {same}
    }]

    lineup `id` is the ESPN player id (absent in older fixture data); trade
    inference in pipeline/trades.py depends on it.

    slot is the lineup slot the player occupied ("QB", "RB", "FLEX", ...,
    "BE" for bench, "IR" for injured reserve). score is the sum of points of
    non-BE/IR players.
"""

import os
from pathlib import Path

LEAGUE_ID = 451795550
ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
SITE_DATA = ROOT / "site" / "data" / "league.json"

BENCH_SLOTS = {"BE", "IR"}
FLEX_ELIGIBLE = {"RB", "WR", "TE"}


def load_cookies():
    """Read ESPN auth cookies from the environment or a .env file.

    Returns (espn_s2, swid) or raises with instructions if missing.
    """
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())
    espn_s2 = os.environ.get("ESPN_S2")
    swid = os.environ.get("SWID")
    if not espn_s2 or not swid:
        raise SystemExit(
            "Missing ESPN cookies. This league is private, so pulls need the "
            "ESPN_S2 and SWID values from a logged-in espn.com browser session.\n"
            "Locally: copy .env.example to .env and fill both in.\n"
            "GitHub Actions: add them as repository secrets named ESPN_S2 and SWID."
        )
    return espn_s2, swid
