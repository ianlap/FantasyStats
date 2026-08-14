# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Goal

Stat-tracking site for Ian's ESPN fantasy football league ("Generic ass name", 12 teams): standings, matchups, lineups, luck/efficiency stats, records.

**Deployed**: https://ianlap.github.io/FantasyStats/ from the public repo `ianlap/FantasyStats` (GitHub Pages, source: Actions). Cookie secrets `ESPN_S2`/`SWID` are set on the repo; the schedule keeps data fresh.

## Commands

```bash
uv sync                                        # install deps (Python 3.11+, uv-managed)
uv run pytest                                  # run tests (tests/ over pipeline/)
uv run pytest tests/test_stats.py -k luck      # run a single test
uv run python -m pipeline.fixtures             # regenerate deterministic sample season
uv run python -m pipeline.pull --season 2025   # pull real ESPN data (needs .env cookies)
uv run python -m pipeline.build --season 2025  # compile site/data/league.json
python3 -m http.server 8000 -d site            # preview site locally
```

## Architecture

One-way data flow, three layers:

1. **`pipeline/pull.py`** — ESPN via `espn-api` → normalized raw JSON in `data/raw/<season>/` (`meta.json` + `week_NN.json`). The schema is documented in `pipeline/config.py`. `pipeline/fixtures.py` generates a deterministic sample season in the same schema.
2. **`pipeline/stats.py`** — pure functions over `{"meta", "weeks"}`: standings, all-play/luck, optimal lineups, streaks, records, awards, champion. All record math uses regular-season weeks only. Keep functions pure; display rounding happens in `build.py`, not here (the zero-sum luck test depends on it). **`pipeline/trades.py`** infers trades by reconciling weekly roster snapshots against the transaction log (`data/raw/<season>/transactions.json`, swept per scoring period by `pull.py`) and computes with/without-the-deal counterfactuals. ESPN redacts trade contents and sometimes loses drops for completed seasons, so every detection rule requires positive evidence and deals need legs both ways; verified 12/12 against the league's ESPN Transaction Counter for 2025. Deals only provable from the league feed go in `data/raw/<season>/trades_manual.json`.
3. **`pipeline/build.py`** → `site/data/league.json`, the single payload the static site (`site/`, vanilla JS SPA with hash routing + hand-rolled SVG charts in `site/js/charts.js`) renders. `tests/test_build.py` pins this schema — update it when changing the payload.

`.github/workflows/update.yml` runs pull → test → build → commit data → deploy Pages on a cron schedule (daily + after each NFL game window, DST-safe UTC times). Raw snapshots are committed so git history is the season archive; the season is auto-computed (year, or year−1 before September).

## ESPN Data

The league (id 451795550) is **private**: pulls need `ESPN_S2` and `SWID` cookies from a logged-in espn.com browser session, stored in `.env` locally (gitignored) and as GitHub Actions repo secrets. The API is ESPN's unofficial v3 (`lm-api-reads.fantasy.espn.com`), accessed through the [`espn-api` package](https://github.com/cwendt94/espn-api) — it can change without notice, which is why raw snapshots are committed and the site never depends on a live ESPN call. `pull.py` refuses to overwrite an existing week file with a smaller response, and surfaces expired cookies (401) with re-auth instructions.

## User Notes

- Ian works with large datasets; long-running commands may time out in Claude Code — if a command times out, tell him to run it himself rather than retrying.
