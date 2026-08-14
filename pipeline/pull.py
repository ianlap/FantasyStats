"""Pull real league data from ESPN into the raw-data schema.

Requires ESPN_S2 and SWID cookies (the league is private) — see .env.example.
Run: uv run python -m pipeline.pull [--season 2025]

Never clobbers good data: an existing week file is only overwritten when the
fresh response contains at least as many matchups.
"""

import argparse
import json
import math

import requests
from espn_api.football import League

from pipeline.config import LEAGUE_ID, RAW_DIR, load_cookies

# espn-api slot names we normalize; anything else passes through untouched.
SLOT_ALIASES = {"RB/WR/TE": "FLEX", "OP": "FLEX"}


def norm_slot(slot):
    return SLOT_ALIASES.get(slot, slot)


def bracket_for(box, is_playoff):
    if not is_playoff:
        return None
    kind = getattr(box, "matchup_type", "") or ""
    if "WINNERS" in kind:
        return "winners"
    return "consolation"


def side(team, score, lineup):
    return {
        "team_id": team.team_id,
        "score": round(score, 2),
        "lineup": [
            {
                "id": p.playerId,
                "name": p.name,
                "position": p.position,
                "slot": norm_slot(p.slot_position),
                "points": round(p.points, 2),
                "projected": round(p.projected_points, 2),
            }
            for p in lineup
        ],
    }


def owner_name(team):
    owners = getattr(team, "owners", None) or []
    if owners and isinstance(owners[0], dict):
        first = owners[0].get("firstName", "").strip()
        last = owners[0].get("lastName", "").strip()
        return f"{first} {last}".strip() or team.team_abbrev
    return team.team_abbrev


def is_finalized(season):
    meta_path = RAW_DIR / str(season) / "meta.json"
    if not meta_path.exists():
        return False
    return bool(json.loads(meta_path.read_text()).get("finalized"))


def pull_season(season):
    if is_finalized(season):
        print(f"Season {season} is finalized; skipping pull.")
        return
    espn_s2, swid = load_cookies()
    league = League(
        league_id=LEAGUE_ID, year=season, espn_s2=espn_s2, swid=swid
    )

    reg_weeks = league.settings.reg_season_count
    playoff_teams = league.settings.playoff_team_count
    playoff_rounds = max(1, math.ceil(math.log2(playoff_teams))) if playoff_teams else 0
    total_weeks = reg_weeks + playoff_rounds
    last_completed = min(total_weeks, max(1, league.current_week))

    meta = {
        "season": season,
        "league_id": LEAGUE_ID,
        "league_name": league.settings.name,
        "demo": False,
        "regular_season_weeks": reg_weeks,
        "playoff_teams": playoff_teams,
        "starting_slots": None,  # filled from the first week's lineups below
        "teams": [
            {
                "id": t.team_id,
                "name": t.team_name,
                "abbrev": t.team_abbrev,
                "owner": owner_name(t),
                # ESPN's bracket-inclusive final placement; 0 until season end.
                "final_standing": getattr(t, "final_standing", 0) or None,
            }
            for t in league.teams
        ],
    }

    out_dir = RAW_DIR / str(season)
    out_dir.mkdir(parents=True, exist_ok=True)

    starting_slots = None
    for week in range(1, last_completed + 1):
        boxes = league.box_scores(week)
        is_playoff = week > reg_weeks
        matchups = []
        for box in boxes:
            # Bye entries have a 0/False home or away team.
            if not getattr(box, "home_team", None) or not getattr(box, "away_team", None):
                continue
            if box.home_team == 0 or box.away_team == 0:
                continue
            matchups.append({
                "bracket": bracket_for(box, is_playoff),
                "home": side(box.home_team, box.home_score, box.home_lineup),
                "away": side(box.away_team, box.away_score, box.away_lineup),
            })
        if starting_slots is None and matchups:
            first = matchups[0]["home"]["lineup"]
            starting_slots = [
                p["slot"] for p in first if p["slot"] not in ("BE", "IR")
            ]

        path = out_dir / f"week_{week:02d}.json"
        if path.exists():
            existing = json.loads(path.read_text())
            if len(matchups) < len(existing.get("matchups", [])):
                print(f"week {week}: response smaller than saved data, keeping existing")
                continue
        if not matchups:
            print(f"week {week}: no matchups returned, skipping")
            continue
        path.write_text(json.dumps({
            "season": season, "week": week,
            "is_playoff": is_playoff, "matchups": matchups,
        }, indent=1))
        print(f"week {week}: saved {len(matchups)} matchups")

    meta["starting_slots"] = starting_slots or [
        "QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "D/ST", "K"
    ]
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=1))
    print(f"Saved league meta for {meta['league_name']} ({season})")
    pull_transactions(season)


def pull_transactions(season):
    """Sweep the transaction log (trade inference needs it). ESPN only returns
    transactions per scoring period, so query each week and dedupe by id."""
    espn_s2, swid = load_cookies()
    cookies = {"espn_s2": espn_s2, "SWID": swid}
    base = (
        "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/"
        f"seasons/{season}/segments/0/leagues/{LEAGUE_ID}"
    )
    seen = {}
    for sp in range(1, 19):
        r = requests.get(
            base, params={"view": "mTransactions2", "scoringPeriodId": sp},
            cookies=cookies, timeout=30,
        )
        if r.ok:
            for t in r.json().get("transactions", []):
                seen.setdefault(t.get("id"), t)
    path = RAW_DIR / str(season) / "transactions.json"
    if path.exists():
        existing = json.loads(path.read_text())
        if len(seen) < len(existing):
            print(f"transactions: response smaller than saved data "
                  f"({len(seen)} < {len(existing)}), keeping existing")
            return
    ordered = sorted(seen.values(), key=lambda t: t.get("processDate") or 0)
    path.write_text(json.dumps(ordered, indent=1))
    print(f"Saved {len(ordered)} transactions")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2025)
    args = parser.parse_args()
    try:
        pull_season(args.season)
    except Exception as e:  # surface cookie expiry clearly for CI logs
        if "401" in str(e) or "Private" in str(e) or "not authorized" in str(e).lower():
            raise SystemExit(
                "ESPN rejected the request (401). The ESPN_S2/SWID cookies have "
                "likely expired — re-copy them from a logged-in espn.com session "
                "and update the .env file / GitHub repo secrets."
            ) from e
        raise


if __name__ == "__main__":
    main()
