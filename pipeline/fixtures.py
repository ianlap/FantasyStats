"""Generate a deterministic sample 2025 season in the raw-data schema.

Used until real ESPN cookies are configured (the league is private), and as
test data. Run: uv run python -m pipeline.fixtures
"""

import json
import random

from pipeline import stats
from pipeline.config import RAW_DIR

SEASON = 2025
REG_WEEKS = 14
PLAYOFF_TEAMS = 6
STARTING_SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "D/ST", "K"]
ROSTER_COUNTS = {"QB": 2, "RB": 5, "WR": 5, "TE": 2, "D/ST": 1, "K": 1}
# (mean, stddev) of weekly points for an average starter at each position
BASE_SCORING = {
    "QB": (18, 6), "RB": (11, 6), "WR": (11, 7),
    "TE": (8, 5), "D/ST": (7, 5), "K": (8, 3),
}

TEAMS = [
    (1, "Bijan Mustard", "MSTD", "Alex"),
    (2, "Hurts So Good", "HURT", "Sam"),
    (3, "Breece's Pieces", "BRPC", "Jordan"),
    (4, "Kittle Corn", "KORN", "Casey"),
    (5, "Dak to the Future", "DAKF", "Riley"),
    (6, "Chubb Hub", "CHUB", "Morgan"),
    (7, "Lamarvelous", "LMRV", "Taylor"),
    (8, "Waddle Waddle", "WDDL", "Jamie"),
    (9, "The Gridiron Gentlemen", "GENT", "Drew"),
    (10, "Justin Time", "JSTN", "Pat"),
]

# Ordered roughly best -> worst; quality multipliers are assigned by rank.
POOLS = {
    "QB": [
        "Josh Allen", "Lamar Jackson", "Jalen Hurts", "Patrick Mahomes",
        "Joe Burrow", "Jayden Daniels", "C.J. Stroud", "Justin Herbert",
        "Jordan Love", "Baker Mayfield", "Kyler Murray", "Brock Purdy",
        "Dak Prescott", "Tua Tagovailoa", "Jared Goff", "Trevor Lawrence",
        "Caleb Williams", "Bo Nix", "Geno Smith", "Sam Darnold",
    ],
    "RB": [
        "Bijan Robinson", "Saquon Barkley", "Jahmyr Gibbs", "Christian McCaffrey",
        "De'Von Achane", "Derrick Henry", "Breece Hall", "Jonathan Taylor",
        "Josh Jacobs", "Kyren Williams", "Kenneth Walker III", "James Cook",
        "Alvin Kamara", "Joe Mixon", "Aaron Jones", "David Montgomery",
        "Rhamondre Stevenson", "Chuba Hubbard", "Tony Pollard", "Najee Harris",
        "Rachaad White", "Travis Etienne", "Isiah Pacheco", "Brian Robinson",
        "D'Andre Swift", "Javonte Williams", "Austin Ekeler", "Ashton Jeanty",
        "Omarion Hampton", "TreVeyon Henderson", "Quinshon Judkins", "Bucky Irving",
        "Tyrone Tracy", "Jordan Mason", "Rico Dowdle", "Jaylen Warren",
        "Ray Davis", "Braelon Allen", "Tyjae Spears", "Jerome Ford",
        "Alexander Mattison", "Justice Hill", "Roschon Johnson", "Kimani Vidal",
        "Blake Corum", "Devin Singletary", "Jaleel McLaughlin", "Zack Moss",
        "Kareem Hunt", "Samaje Perine",
    ],
    "WR": [
        "Ja'Marr Chase", "Justin Jefferson", "CeeDee Lamb", "Amon-Ra St. Brown",
        "Malik Nabers", "Puka Nacua", "Nico Collins", "Brian Thomas Jr.",
        "A.J. Brown", "Drake London", "Tyreek Hill", "Tee Higgins",
        "Davante Adams", "Jaylen Waddle", "DK Metcalf", "Mike Evans",
        "Marvin Harrison Jr.", "Garrett Wilson", "Chris Olave", "Rashee Rice",
        "DeVonta Smith", "Zay Flowers", "Jordan Addison", "Jameson Williams",
        "Courtland Sutton", "Calvin Ridley", "Tetairoa McMillan", "Travis Hunter",
        "Rome Odunze", "Ladd McConkey", "Jaxon Smith-Njigba", "Terry McLaurin",
        "George Pickens", "Xavier Worthy", "Stefon Diggs", "Cooper Kupp",
        "Chris Godwin", "Keenan Allen", "Amari Cooper", "Deebo Samuel",
        "Jerry Jeudy", "Khalil Shakir", "Jakobi Meyers", "Josh Downs",
        "Rashid Shaheed", "Darnell Mooney", "Jayden Reed", "Dontayvion Wicks",
        "Michael Pittman Jr.", "Brandon Aiyuk",
    ],
    "TE": [
        "Brock Bowers", "Trey McBride", "George Kittle", "Sam LaPorta",
        "T.J. Hockenson", "Mark Andrews", "David Njoku", "Evan Engram",
        "Dallas Goedert", "Jake Ferguson", "Dalton Kincaid", "Tucker Kraft",
        "Colston Loveland", "Tyler Warren", "Kyle Pitts", "Pat Freiermuth",
        "Hunter Henry", "Zach Ertz", "Cade Otton", "Isaiah Likely",
    ],
    "D/ST": [
        "Ravens D/ST", "Steelers D/ST", "49ers D/ST", "Cowboys D/ST",
        "Jets D/ST", "Browns D/ST", "Bills D/ST", "Eagles D/ST",
        "Broncos D/ST", "Texans D/ST",
    ],
    "K": [
        "Brandon Aubrey", "Justin Tucker", "Harrison Butker", "Jake Bates",
        "Cameron Dicker", "Tyler Bass", "Younghoe Koo", "Jason Sanders",
        "Chris Boswell", "Ka'imi Fairbairn",
    ],
}


def build_rosters(rng):
    """Snake-deal each position pool (best first) so talent spreads evenly."""
    rosters = {tid: [] for tid, *_ in TEAMS}
    order = [tid for tid, *_ in TEAMS]
    rng.shuffle(order)
    for pos, count in ROSTER_COUNTS.items():
        pool = POOLS[pos][: count * len(TEAMS)]
        for rnd in range(count):
            picks = order if rnd % 2 == 0 else list(reversed(order))
            for i, tid in enumerate(picks):
                idx = rnd * len(TEAMS) + i
                quality = 1.30 - 0.55 * (idx / max(1, len(pool) - 1))
                quality *= 1 + rng.gauss(0, 0.06)
                rosters[tid].append({
                    "name": pool[idx], "position": pos, "quality": quality,
                })
    return rosters


def score_week(rng, roster):
    """Simulate one week: produce a full lineup with slots assigned."""
    scored = []
    for p in roster:
        mean, std = BASE_SCORING[p["position"]]
        projected = round(max(1.0, mean * p["quality"]), 1)
        if rng.random() < 0.05:  # injury / dud / didn't play
            points = 0.0
        else:
            points = round(max(0.0, rng.gauss(projected, std)), 1)
        # Managers start players on perceived value, not hindsight.
        perceived = projected + rng.gauss(0, 3.5)
        scored.append({
            "name": p["name"], "position": p["position"],
            "points": points, "projected": projected, "_perceived": perceived,
        })

    starters = []
    remaining = sorted(scored, key=lambda p: -p["_perceived"])

    def take(pos_set, slot):
        for p in remaining:
            if p["position"] in pos_set:
                remaining.remove(p)
                p2 = dict(p, slot=slot)
                starters.append(p2)
                return

    for slot in ["QB", "RB", "RB", "WR", "WR", "TE"]:
        take({slot}, slot)
    take({"RB", "WR", "TE"}, "FLEX")
    take({"D/ST"}, "D/ST")
    take({"K"}, "K")
    bench = [dict(p, slot="BE") for p in remaining]

    lineup = starters + bench
    for p in lineup:
        p.pop("_perceived", None)
    score = round(sum(p["points"] for p in starters), 1)
    return score, lineup


def round_robin(team_order):
    """Circle-method schedule: 9 unique rounds for 10 teams."""
    ids = list(team_order)
    fixed, rest = ids[0], ids[1:]
    rounds = []
    for _ in range(len(ids) - 1):
        current = [fixed] + rest
        pairs = [
            (current[i], current[len(ids) - 1 - i]) for i in range(len(ids) // 2)
        ]
        rounds.append(pairs)
        rest = rest[-1:] + rest[:-1]
    return rounds


def matchup(rng, rosters, home_id, away_id, bracket=None):
    home_score, home_lineup = score_week(rng, rosters[home_id])
    away_score, away_lineup = score_week(rng, rosters[away_id])
    if home_score == away_score:  # avoid ties; nudge the home team
        home_score = round(home_score + 0.1, 1)
    return {
        "bracket": bracket,
        "home": {"team_id": home_id, "score": home_score, "lineup": home_lineup},
        "away": {"team_id": away_id, "score": away_score, "lineup": away_lineup},
    }


def winner(m):
    return (m["home"] if m["home"]["score"] > m["away"]["score"] else m["away"])["team_id"]


def generate(seed=20250901):
    rng = random.Random(seed)
    rosters = build_rosters(rng)

    meta = {
        "season": SEASON,
        "league_id": 0,
        "league_name": "Demo League",
        "demo": True,
        "regular_season_weeks": REG_WEEKS,
        "playoff_teams": PLAYOFF_TEAMS,
        "starting_slots": STARTING_SLOTS,
        "teams": [
            {"id": tid, "name": name, "abbrev": ab, "owner": owner}
            for tid, name, ab, owner in TEAMS
        ],
    }

    rounds = round_robin([tid for tid, *_ in TEAMS])
    weeks = []
    for wk in range(1, REG_WEEKS + 1):
        pairs = rounds[(wk - 1) % len(rounds)]
        matchups = [
            matchup(rng, rosters, h, a) if wk % 2 else matchup(rng, rosters, a, h)
            for h, a in pairs
        ]
        weeks.append({
            "season": SEASON, "week": wk, "is_playoff": False, "matchups": matchups,
        })

    season = {"meta": meta, "weeks": weeks}
    seeds = [row["team_id"] for row in stats.standings(season)]

    def playoff_week(wk, winners_pairs, everyone_else):
        ms = [matchup(rng, rosters, h, a, bracket="winners") for h, a in winners_pairs]
        others = [t for t in seeds if t in everyone_else]
        for i in range(0, len(others) - 1, 2):
            ms.append(matchup(rng, rosters, others[i], others[i + 1], bracket="consolation"))
        return {"season": SEASON, "week": wk, "is_playoff": True, "matchups": ms}

    # Week 15 quarterfinals: seeds 1-2 bye; 3v6, 4v5; the rest play consolation.
    wk15 = playoff_week(
        15,
        [(seeds[2], seeds[5]), (seeds[3], seeds[4])],
        set(seeds[6:]),
    )
    weeks.append(wk15)
    qf = [m for m in wk15["matchups"] if m["bracket"] == "winners"]
    qf_winners = sorted((winner(m) for m in qf), key=seeds.index)

    # Week 16 semifinals: 1 seed plays the worst surviving seed.
    sf_pairs = [(seeds[0], qf_winners[-1]), (seeds[1], qf_winners[0])]
    wk16 = playoff_week(
        16, sf_pairs, set(seeds) - {seeds[0], seeds[1], *qf_winners}
    )
    weeks.append(wk16)
    sf = [m for m in wk16["matchups"] if m["bracket"] == "winners"]
    sf_winners = sorted((winner(m) for m in sf), key=seeds.index)

    # Week 17 championship; everyone else pairs off by seed.
    wk17 = playoff_week(
        17, [(sf_winners[0], sf_winners[1])], set(seeds) - set(sf_winners)
    )
    weeks.append(wk17)
    return meta, weeks


def write(meta, weeks):
    out_dir = RAW_DIR / str(SEASON)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=1))
    for week_data in weeks:
        path = out_dir / f"week_{week_data['week']:02d}.json"
        path.write_text(json.dumps(week_data, indent=1))
    return out_dir


if __name__ == "__main__":
    meta, weeks = generate()
    out = write(meta, weeks)
    print(f"Wrote {len(weeks)} weeks of sample data to {out}")
