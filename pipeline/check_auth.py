"""Verify the ESPN cookies in .env can access the league.

Makes one small API call — no data is written. Run:
uv run python -m pipeline.check_auth [--season 2025]
"""

import argparse

from espn_api.football import League

from pipeline.config import LEAGUE_ID, load_cookies


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2025)
    args = parser.parse_args()

    espn_s2, swid = load_cookies()
    try:
        league = League(
            league_id=LEAGUE_ID, year=args.season, espn_s2=espn_s2, swid=swid
        )
    except Exception as e:
        if "401" in str(e) or "Private" in str(e) or "not authorized" in str(e).lower():
            raise SystemExit(
                "ESPN rejected the cookies (401). Re-copy ESPN_S2 and SWID from "
                "a logged-in espn.com session into .env — watch for truncation, "
                "ESPN_S2 is several hundred characters long."
            ) from e
        raise

    print(f"Authenticated: {league.settings.name} ({args.season})")
    print(f"Teams ({len(league.teams)}):")
    for t in league.teams:
        print(f"  {t.team_id:>2}  {t.team_name}")


if __name__ == "__main__":
    main()
