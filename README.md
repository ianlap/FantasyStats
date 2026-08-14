# FantasyStats

Stat tracking and a shareable website for our ESPN fantasy football league:
standings, matchup and lineup detail, luck and lineup-efficiency stats, season
records, and rank-over-time charts. Data flows one way:

```
ESPN → pipeline/pull.py → data/raw/<season>/ → pipeline/build.py → site/data/league.json → static site
```

The site is plain HTML/CSS/JS (no build step) and deploys to GitHub Pages.
GitHub Actions refreshes data daily and after each NFL game window.

## Local development

```bash
uv sync                                   # install dependencies
uv run pytest                             # run the test suite
uv run python -m pipeline.fixtures        # generate sample data (only if data/raw is empty)
uv run python -m pipeline.pull --season 2025    # pull real data (needs cookies, see below)
uv run python -m pipeline.build --season 2025   # compile site/data/league.json
python3 -m http.server 8000 -d site       # preview at http://localhost:8000
```

## ESPN cookies (private league)

The league is private, so pulls need two cookies from a logged-in espn.com
session: `ESPN_S2` and `SWID`.

1. Log in at espn.com and open your league.
2. DevTools (F12) → Application → Cookies → `https://www.espn.com`.
3. Copy `espn_s2` and `SWID` (keep SWID's curly braces).
4. Locally: `cp .env.example .env` and fill both in. `.env` is gitignored.
5. GitHub: repo Settings → Secrets and variables → Actions → add `ESPN_S2`
   and `SWID` as repository secrets.

Cookies last roughly a year. When they expire, the scheduled workflow fails
with a message saying to refresh them — repeat steps 1–5.

## Deploying

1. Push this repo to GitHub (public repo for free Pages).
2. Repo Settings → Pages → Source: **GitHub Actions**.
3. Add the two secrets above.
4. Run the "Update league data and deploy" workflow manually once (Actions tab),
   or just push — it also runs on every push to main and on the cron schedule.

The workflow pulls fresh ESPN data, runs the tests, rebuilds `league.json`,
commits the refreshed data back (so git history is the season archive), and
publishes `site/` to Pages. If a pull fails, the site keeps serving the last
good build.
