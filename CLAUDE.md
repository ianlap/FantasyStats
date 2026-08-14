# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Goal

Stat-tracking and display (likely a webpage) for Ian's ESPN fantasy football league: pull league data, show standings, matchups, lineups, scores, and fun historical stats.

## Current State

Empty project — nothing scaffolded yet. No build/test/lint commands exist. When the stack is chosen and scaffolded, document the commands here.

## Data Strategy (decided)

ESPN exposes an unofficial-but-stable v3 fantasy API. **Do not build a screenshot/manual-upload pipeline** — direct API access works.

- **Primary tool**: the [`espn-api` Python package](https://github.com/cwendt94/espn-api) (`pip install espn_api`). Actively maintained, wraps league, teams, rosters, box scores, matchups, free agents, and historical seasons.
  ```python
  from espn_api.football import League
  league = League(league_id=..., year=2026, espn_s2="...", swid="...")
  ```
- **Auth**: public leagues need only `league_id` + `year`. Private leagues need two browser cookies from a logged-in espn.com session: `espn_s2` and `SWID` (Chrome DevTools → Application → Cookies → espn.com). These are user credentials — keep them in `.env` / untracked config, never committed.
- **Raw endpoint** (if going without the package): `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{league_id}` (2018+); `.../leagueHistory/{league_id}?seasonId={year}` for 2017 and earlier. Player queries use the `X-Fantasy-Filter` header. Useful views: `mTeam`, `mRoster`, `mMatchup`, `mBoxscore`, `mSettings`.
- Because the API is unofficial, ESPN can change it without notice. Cache/snapshot pulled data locally (JSON files or SQLite) so the site never depends on a live ESPN call, and so history survives API changes.

## Open Decisions

- Web stack for the display layer (not chosen; data layer is Python).
- Hosting (a static site regenerated from cached data would be the simplest fit).

## User Notes

- Ian works with large datasets; long-running commands may time out in Claude Code — if a command times out, tell him to run it himself rather than retrying.
