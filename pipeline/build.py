"""Compile raw data into per-season payloads plus an all-time aggregate.

Run: uv run python -m pipeline.build            # every season + cumulative
     uv run python -m pipeline.build --season 2025   # one season only

Outputs under site/data/: <season>.json per season, cumulative.json,
and index.json (the manifest the site loads first).
"""

import argparse
import json
from datetime import datetime, timezone

from pipeline import cumulative, stats, trades
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


def load_optional(season, filename):
    path = RAW_DIR / str(season) / filename
    return json.loads(path.read_text()) if path.exists() else None


def assemble(season, transactions=None, manual_trades=None):
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
        playoff_games = [g for g in weekly_scores[tid] if g["is_playoff"]]
        teams.append({
            "final_standing": info.get("final_standing"),
            "playoff_wins": sum(1 for g in playoff_games if g["result"] == "W"),
            "playoff_losses": sum(1 for g in playoff_games if g["result"] == "L"),
            "playoff_pf": round(sum(g["points"] for g in playoff_games), 2),
            "playoff_pa": round(sum(g["opponent_points"] for g in playoff_games), 2),
            "playoff_games": len(playoff_games),
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
        "trades": trades.analyze_all(season, transactions, manual_trades),
    }


def discover_seasons():
    """Season directories under data/raw/ that contain at least one week."""
    seasons = []
    for path in sorted(RAW_DIR.iterdir()) if RAW_DIR.exists() else []:
        if path.is_dir() and path.name.isdigit() and list(path.glob("week_*.json")):
            seasons.append(int(path.name))
    return seasons


def build_season(season):
    return assemble(
        load_season(season),
        transactions=load_optional(season, "transactions.json"),
        manual_trades=load_optional(season, "trades_manual.json"),
    )


def write(path, payload):
    path.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"Wrote {path} ({path.stat().st_size // 1024} KB)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=None,
                        help="build one season only (skips cumulative/manifest)")
    args = parser.parse_args()

    out_dir = SITE_DATA.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.season is not None:
        write(out_dir / f"{args.season}.json", build_season(args.season))
        return

    seasons = discover_seasons()
    if not seasons:
        raise SystemExit(f"No season data under {RAW_DIR}; run a pull first.")
    payloads = [build_season(s) for s in seasons]
    for payload in payloads:
        write(out_dir / f"{payload['season']}.json", payload)
    write(out_dir / "cumulative.json", cumulative.aggregate(payloads))
    write(out_dir / "index.json", {
        "seasons": sorted(seasons, reverse=True),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    legacy = out_dir / "league.json"
    if legacy.exists():
        legacy.unlink()


if __name__ == "__main__":
    main()
