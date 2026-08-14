"""Compile raw season data into site/data/league.json for the frontend.

Run: uv run python -m pipeline.build [--season 2025]
"""

import argparse
import json
from datetime import datetime, timezone

from pipeline import stats
from pipeline.config import RAW_DIR, SITE_DATA


def load_season(season):
    season_dir = RAW_DIR / str(season)
    meta = json.loads((season_dir / "meta.json").read_text())
    weeks = [
        json.loads(p.read_text())
        for p in sorted(season_dir.glob("week_*.json"))
    ]
    if not weeks:
        raise SystemExit(f"No week data in {season_dir}; run a pull first.")
    return {"meta": meta, "weeks": weeks}


def assemble(season):
    meta = season["meta"]
    table = stats.standings(season)
    ap = stats.allplay(season)
    st = stats.streaks(season)
    eff = stats.lineup_efficiency(season)
    weekly_scores = stats.team_week_scores(season)
    places = stats.place_by_week(season)

    teams = []
    for row in table:
        tid = row["team_id"]
        info = next(t for t in meta["teams"] if t["id"] == tid)
        teams.append({
            **info,
            "wins": row["wins"], "losses": row["losses"], "ties": row["ties"],
            "place": row["place"],
            "points_for": row["points_for"],
            "points_against": row["points_against"],
            "allplay_wins": ap[tid]["allplay_wins"],
            "allplay_losses": ap[tid]["allplay_losses"],
            "luck": round(ap[tid]["luck"], 2),
            "longest_win": st[tid]["longest_win"],
            "longest_loss": st[tid]["longest_loss"],
            "current_streak": st[tid]["current"],
            "optimal_points": eff[tid]["optimal"],
            "points_benched": eff[tid]["wasted"],
            "efficiency": eff[tid]["efficiency"],
            "weekly": weekly_scores[tid],
            "places": places[tid],
        })

    slots = meta["starting_slots"]
    weeks = []
    for week_data in season["weeks"]:
        matchups = []
        for m in week_data["matchups"]:
            enriched = dict(m)
            for side_key in ("home", "away"):
                side = dict(m[side_key])
                if side["lineup"]:
                    side["optimal"] = stats.optimal_points(side["lineup"], slots)
                enriched[side_key] = side
            matchups.append(enriched)
        weeks.append({
            "week": week_data["week"],
            "is_playoff": week_data["is_playoff"],
            "matchups": matchups,
            "awards": stats.weekly_awards(season, week_data),
        })

    return {
        "season": meta["season"],
        "league_id": meta["league_id"],
        "league_name": meta["league_name"],
        "demo": meta.get("demo", False),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "regular_season_weeks": meta["regular_season_weeks"],
        "playoff_teams": meta["playoff_teams"],
        "starting_slots": meta["starting_slots"],
        "teams": teams,
        "weeks": weeks,
        "records": stats.season_records(season),
        "champion": stats.champion(season),
        "h2h": stats.h2h_matrix(season),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2025)
    args = parser.parse_args()

    payload = assemble(load_season(args.season))
    SITE_DATA.parent.mkdir(parents=True, exist_ok=True)
    SITE_DATA.write_text(json.dumps(payload, separators=(",", ":")))
    size_kb = SITE_DATA.stat().st_size // 1024
    print(f"Wrote {SITE_DATA} ({size_kb} KB, season {payload['season']}, "
          f"{len(payload['weeks'])} weeks)")


if __name__ == "__main__":
    main()
