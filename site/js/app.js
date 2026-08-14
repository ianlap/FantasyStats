import {
  bumpChart, pointsChart, luckChart, hBars, pennant, ordinal,
} from "./charts.js";

let D = null;            // league payload
let teamById = new Map();
let medians = [];        // league median score per week (index week-1)

const view = () => document.getElementById("view");

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

const f1 = (n) => Number(n).toFixed(1);
const team = (id) => teamById.get(id);
const tname = (id) => esc(team(id)?.name ?? `Team ${id}`);
const tabbr = (id) => esc(team(id)?.abbrev ?? `T${id}`);

function median(nums) {
  if (!nums.length) return null;
  const s = [...nums].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function streakText(st) {
  if (!st) return "–";
  return `${st.kind}${st.length}`;
}

function luckText(luck) {
  const sign = luck >= 0 ? "+" : "−";
  return `${sign}${Math.abs(luck).toFixed(1)}`;
}

function kicker(chipText, title, note = "") {
  return `<div class="kicker"><span class="chip">${chipText}</span><h2>${title}</h2>` +
    (note ? `<span class="note">${note}</span>` : "") + `</div>`;
}

/* ---------- routing ---------- */

const routes = {
  standings: renderStandings,
  matchups: renderMatchups,
  teams: renderTeams,
  trades: renderTrades,
  records: renderRecords,
};

function parseHash() {
  const parts = location.hash.replace(/^#\/?/, "").split("/");
  const page = routes[parts[0]] ? parts[0] : "standings";
  return { page, arg: parts[1] ? Number(parts[1]) : null };
}

function navigate() {
  const { page, arg } = parseHash();
  for (const btn of document.querySelectorAll(".tab")) {
    btn.setAttribute("aria-selected", btn.dataset.page === page ? "true" : "false");
  }
  routes[page](arg);
  window.scrollTo(0, 0);
}

/* ---------- standings ---------- */

function renderStandings() {
  if (D.cumulative) {
    renderStandingsCumulative();
    return;
  }
  const champ = D.champion ? team(D.champion.team_id) : null;
  const lastWeek = D.weeks[D.weeks.length - 1];

  let html = "";
  if (champ) {
    html += `<section class="section">
      <div class="pennant-wrap">
        <div id="pennant-host"></div>
        <div class="pennant-caption">
          <div class="label">${D.season} League Champion</div>
          <div class="name">${esc(champ.name)}</div>
          <div class="sub">${esc(champ.owner)} · ${champ.wins}–${champ.losses} regular season · ${f1(champ.points_for)} PF</div>
        </div>
      </div>
    </section>`;
  }

  html += `<section class="section" id="standings-block"></section>`;

  html += `<section class="section">
    ${kicker("The Race", "Place by week", "tap a line for the team page")}
    <div class="card chart-card"><div class="chart-host" id="bump-host"></div></div>
  </section>`;

  if (lastWeek?.awards && Object.keys(lastWeek.awards).length) {
    html += `<section class="section">
      ${kicker("Week " + lastWeek.week, lastWeek.is_playoff ? "Final week awards" : "Latest awards")}
      ${awardsHtml(lastWeek.awards)}
    </section>`;
  }

  view().innerHTML = html;

  if (champ) pennant(document.getElementById("pennant-host"), "CHAMPS");
  renderStandingsBlock();
  bumpChart(document.getElementById("bump-host"), D.teams, {
    onSelect: (id) => { location.hash = `#/teams/${id}`; },
  });
}

/* ---------- sortable standings table (season + all-time) ---------- */

const ST = { view: "regular", mode: "total", sort: null };

function streakValue(t) {
  const s = t.current_streak;
  return s ? (s.kind === "W" ? s.length : -s.length) : 0;
}

function standingsColumns() {
  const perGame = ST.mode === "pergame";
  const games = (t) => ST.view === "playoff"
    ? t.playoff_games
    : t.wins + t.losses + t.ties;
  const pts = (raw, t) => {
    const g = games(t);
    if (!g) return null;
    return perGame ? raw / g : raw;
  };
  const ptsCell = (raw, t) => {
    const v = pts(raw, t);
    return v == null ? "–" : f1(v);
  };
  const diffCol = (getDiff) => ({
    key: "diff", label: "+/−",
    val: (t) => pts(getDiff(t), t) ?? 0,
    td: (t) => {
      const v = pts(getDiff(t), t);
      if (v == null) return "<td>–</td>";
      return `<td class="${v >= 0 ? "pos" : "neg"}">${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(1)}</td>`;
    },
  });

  if (ST.view === "playoff") {
    return [
      { key: "record", label: "W–L", val: (t) => t.playoff_wins,
        td: (t) => `<td>${t.playoff_games ? `${t.playoff_wins}–${t.playoff_losses}` : "–"}</td>` },
      { key: "gp", label: "GP", val: (t) => t.playoff_games,
        td: (t) => `<td>${t.playoff_games}</td>` },
      { key: "pf", label: "PF", val: (t) => pts(t.playoff_pf, t) ?? -1,
        td: (t) => `<td>${ptsCell(t.playoff_pf, t)}</td>` },
      { key: "pa", label: "PA", val: (t) => pts(t.playoff_pa, t) ?? -1,
        td: (t) => `<td>${ptsCell(t.playoff_pa, t)}</td>` },
      diffCol((t) => t.playoff_pf - t.playoff_pa),
    ];
  }

  const cols = [
    { key: "record", label: "W–L", val: (t) => t.wins,
      td: (t) => `<td>${t.wins}–${t.losses}${t.ties ? "–" + t.ties : ""}</td>` },
    { key: "pf", label: "PF", val: (t) => pts(t.points_for, t) ?? -1,
      td: (t) => `<td>${ptsCell(t.points_for, t)}</td>` },
    { key: "pa", label: "PA", val: (t) => pts(t.points_against, t) ?? -1,
      td: (t) => `<td>${ptsCell(t.points_against, t)}</td>` },
    diffCol((t) => t.points_for - t.points_against),
  ];
  if (D.cumulative) {
    cols.push({ key: "titles", label: "Titles", val: (t) => t.titles,
      td: (t) => `<td>${t.titles ? "🏆".repeat(t.titles) : ""}</td>` });
  } else {
    cols.push({ key: "streak", label: "Streak", val: streakValue,
      td: (t) => `<td class="streak-${(t.current_streak?.kind || "").toLowerCase()}">${streakText(t.current_streak)}</td>` });
  }
  cols.push({ key: "allplay", label: "All-play", val: (t) => t.allplay_wins,
    td: (t) => `<td>${t.allplay_wins}–${t.allplay_losses}</td>` });
  cols.push({ key: "luck", label: "Luck", val: (t) => t.luck,
    td: (t) => `<td class="${t.luck >= 0 ? "pos" : "neg"}">${luckText(t.luck)}</td>` });
  return cols;
}

function renderStandingsBlock() {
  const block = document.getElementById("standings-block");
  if (!block) return;
  const cols = standingsColumns();

  const rows = [...D.teams];
  if (ST.sort) {
    const col = cols.find((c) => c.key === ST.sort.key);
    if (col) {
      const dir = ST.sort.dir === "desc" ? 1 : -1;
      rows.sort((a, b) => (col.val(b) - col.val(a)) * dir);
    }
  }

  const chipText = ST.view === "playoff" ? "Playoffs"
    : D.cumulative ? "All-time" : "Final";
  const note = ST.view === "playoff"
    ? "playoff weeks, consolation included"
    : D.cumulative
      ? `${D.seasons.length} season${D.seasons.length === 1 ? "" : "s"} · ranked by win %`
      : `regular season, weeks 1–${D.regular_season_weeks}`;

  const control = (attr, value, label, active) =>
    `<button class="select-chip" ${attr}="${value}" aria-pressed="${active}">${label}</button>`;

  const ths = cols.map((c) => {
    const state = ST.sort?.key === c.key
      ? (ST.sort.dir === "desc" ? "descending" : "ascending") : "none";
    const mark = state === "none" ? "" : (state === "descending" ? "▼" : "▲");
    return `<th data-sort="${c.key}" aria-sort="${state}" tabindex="0"
      title="Sort by ${c.label}">${c.label}<span class="sort-mark">${mark}</span></th>`;
  }).join("");

  const showCut = !D.cumulative && ST.view === "regular" && !ST.sort;
  block.innerHTML = `
    ${kicker(chipText, "Standings", note)}
    <div class="chip-row st-controls">
      ${control("data-stview", "regular", "Regular season", ST.view === "regular")}
      ${control("data-stview", "playoff", "Playoffs", ST.view === "playoff")}
      <span class="spacer"></span>
      ${control("data-stmode", "total", "Totals", ST.mode === "total")}
      ${control("data-stmode", "pergame", "Per game", ST.mode === "pergame")}
    </div>
    <div class="card table-scroll"><table>
      <thead><tr><th></th><th class="l">Team</th>${ths}</tr></thead>
      <tbody>
        ${rows.map((t) => `
          <tr class="rowlink ${showCut && t.place === D.playoff_teams ? "playoff-cut" : ""}" data-team="${t.id}" tabindex="0">
            <td class="place-cell">${t.place}</td>
            <td class="l"><span class="team-cell"><span class="tname">${esc(t.name)}</span><span class="owner">${esc(t.owner)}</span></span></td>
            ${cols.map((c) => c.td(t)).join("")}
          </tr>`).join("")}
      </tbody>
    </table></div>`;

  for (const chip of block.querySelectorAll("[data-stview]")) {
    chip.addEventListener("click", () => {
      if (ST.view !== chip.dataset.stview) {
        ST.view = chip.dataset.stview;
        ST.sort = null;
        renderStandingsBlock();
      }
    });
  }
  for (const chip of block.querySelectorAll("[data-stmode]")) {
    chip.addEventListener("click", () => {
      if (ST.mode !== chip.dataset.stmode) {
        ST.mode = chip.dataset.stmode;
        renderStandingsBlock();
      }
    });
  }
  for (const th of block.querySelectorAll("th[data-sort]")) {
    const cycle = () => {
      const key = th.dataset.sort;
      if (ST.sort?.key !== key) ST.sort = { key, dir: "desc" };
      else if (ST.sort.dir === "desc") ST.sort = { key, dir: "asc" };
      else ST.sort = null;
      renderStandingsBlock();
    };
    th.addEventListener("click", cycle);
    th.addEventListener("keydown", (e) => { if (e.key === "Enter") cycle(); });
  }
  for (const row of block.querySelectorAll("tr.rowlink")) {
    const go = () => { location.hash = `#/teams/${row.dataset.team}`; };
    row.addEventListener("click", go);
    row.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
  }
}

function renderStandingsCumulative() {
  const nSeasons = D.seasons.length;
  let html = `<section class="section">
    ${kicker("Banners", "Champions")}
    <div class="awards">
      ${D.champions.map((c) => `
        <div class="award"><span class="a-label">${c.season}</span>
          <span class="a-value"><b>${tname(c.team_id)}</b></span></div>`).join("")
        || '<div class="award"><span class="a-value">No completed seasons yet.</span></div>'}
    </div>
  </section>`;

  html += `<section class="section" id="standings-block"></section>`;

  view().innerHTML = html;
  renderStandingsBlock();
}

const AWARD_LABELS = {
  top_score: "Top score",
  low_score: "Toilet bowl",
  biggest_blowout: "Beatdown",
  nailbiter: "Nailbiter",
  most_points_benched: "Left on bench",
};

function awardsHtml(awards) {
  const rows = [];
  for (const [key, label] of Object.entries(AWARD_LABELS)) {
    const a = awards[key];
    if (!a) continue;
    let value = "";
    if (key === "biggest_blowout" || key === "nailbiter") {
      value = `<b>${tname(a.winner_id)}</b> over ${tname(a.loser_id)} by ${f1(a.margin)}`;
    } else {
      value = `<b>${tname(a.team_id)}</b> · ${f1(a.points)}`;
    }
    rows.push(`<div class="award"><span class="a-label">${label}</span><span class="a-value">${value}</span></div>`);
  }
  return `<div class="awards">${rows.join("")}</div>`;
}

/* ---------- matchups ---------- */

function renderMatchups(weekNum) {
  if (D.cumulative) {
    renderStandings();
    return;
  }
  const week = D.weeks.find((w) => w.week === weekNum) || D.weeks[D.weeks.length - 1];

  const chips = D.weeks.map((w) => `
    <button class="select-chip" aria-pressed="${w.week === week.week}" data-week="${w.week}">
      ${w.week}${w.is_playoff ? '<span class="p-mark">P</span>' : ""}
    </button>`).join("");

  let html = `<section class="section">
    ${kicker("Schedule", "Matchups", week.is_playoff ? "playoff week" : "")}
    <div class="chip-row" role="group" aria-label="Pick a week">${chips}</div>`;

  if (week.awards && Object.keys(week.awards).length) {
    html += awardsHtml(week.awards) + '<div style="height:14px"></div>';
  }

  html += `<div class="matchups">
    ${week.matchups.map((m, i) => matchupCard(m, i)).join("")}
  </div></section>`;

  view().innerHTML = html;

  for (const chip of view().querySelectorAll(".select-chip")) {
    chip.addEventListener("click", () => {
      location.hash = `#/matchups/${chip.dataset.week}`;
    });
  }
}

function matchupCard(m, idx) {
  const homeWon = m.home.score > m.away.score;
  const bracket = m.bracket === "winners" ? '<span class="gold">Winners bracket</span>'
    : m.bracket === "consolation" ? "Consolation" : "";
  const margin = f1(Math.abs(m.home.score - m.away.score));
  const hasLineups = m.home.lineup?.length && m.away.lineup?.length;

  const row = (side, won) => `
    <div class="m-row ${won ? "winner" : ""}">
      <span class="m-team">${tname(side.team_id)}</span>
      <span class="m-score">${f1(side.score)}</span>
    </div>`;

  return `<details class="card matchup ${m.bracket === "winners" ? "final" : ""}">
    <summary>
      ${row(m.home, homeWon)}
      ${row(m.away, !homeWon)}
      <div class="m-tag">${bracket}${bracket ? " · " : ""}margin ${margin}${hasLineups ? " · tap for lineups" : ""}</div>
    </summary>
    ${hasLineups ? lineupsHtml(m) : ""}
  </details>`;
}

const SLOT_DISPLAY_ORDER = ["QB", "RB", "WR", "TE", "FLEX", "D/ST", "K"];

function lineupsHtml(m) {
  const rank = (slot) => {
    const i = SLOT_DISPLAY_ORDER.indexOf(slot);
    return i === -1 ? SLOT_DISPLAY_ORDER.length : i;
  };
  const side = (s) => {
    const starters = s.lineup.filter((p) => p.slot !== "BE" && p.slot !== "IR");
    starters.sort((a, b) => rank(a.slot) - rank(b.slot));
    const bench = s.lineup.filter((p) => p.slot === "BE" || p.slot === "IR");
    const left = s.optimal != null ? (s.optimal - s.score) : null;
    return `<div>
      <h4>${tname(s.team_id)}</h4>
      <table>
        ${starters.map((p) => `
          <tr>
            <td class="slot l">${esc(p.slot)}</td>
            <td class="l pname">${esc(p.name)}</td>
            <td>${f1(p.points)}</td>
          </tr>`).join("")}
      </table>
      <details class="bench"><summary>Bench (${bench.length})</summary>
        <table>
          ${bench.map((p) => `
            <tr>
              <td class="slot l">${esc(p.position)}</td>
              <td class="l pname">${esc(p.name)}</td>
              <td>${f1(p.points)}</td>
            </tr>`).join("")}
        </table>
      </details>
      ${left != null && left > 0.05
        ? `<div class="benched-note">Left <b>${f1(left)}</b> on the bench — optimal was ${f1(s.optimal)}.</div>`
        : ""}
    </div>`;
  };
  return `<div class="lineups">${side(m.home)}${side(m.away)}</div>`;
}

/* ---------- teams ---------- */

function renderTeams(teamId) {
  const t = team(teamId) || D.teams[0];

  const chips = D.teams.map((x) => `
    <button class="select-chip" aria-pressed="${x.id === t.id}" data-team="${x.id}">${esc(x.abbrev)}</button>
  `).join("");

  const effPct = t.efficiency != null ? Math.round(t.efficiency * 100) + "%" : "–";

  let html = `<section class="section">
    <div class="chip-row" role="group" aria-label="Pick a team">${chips}</div>
    <div class="team-head">
      <h3>${esc(t.name)}</h3>
      <span class="sub">${esc(t.owner)} · ${ordinal(t.place)} ${D.cumulative ? "all-time" : "place"} · ${t.wins}–${t.losses}${D.cumulative && t.titles ? " · " + "🏆".repeat(t.titles) : ""}</span>
    </div>
    <div class="statgrid">
      <div class="stat"><div class="s-label">Points for</div><div class="s-value">${f1(t.points_for)}</div></div>
      <div class="stat"><div class="s-label">Points against</div><div class="s-value">${f1(t.points_against)}</div></div>
      <div class="stat"><div class="s-label">All-play</div><div class="s-value">${t.allplay_wins}–${t.allplay_losses}</div></div>
      <div class="stat"><div class="s-label">Luck</div><div class="s-value ${t.luck >= 0 ? "pos" : "neg"}">${luckText(t.luck)}</div><div class="s-sub">wins vs deserved</div></div>
      <div class="stat"><div class="s-label">Efficiency</div><div class="s-value">${effPct}</div><div class="s-sub">of optimal lineups</div></div>
      <div class="stat"><div class="s-label">Left on bench</div><div class="s-value">${f1(t.points_benched)}</div><div class="s-sub">${D.cumulative ? "career total" : "season total"}</div></div>
    </div>
  </section>`;

  if (!D.cumulative) {
    html += `<section class="section">
      ${kicker("Form", "Weekly points", "vs league median (dashed)")}
      <div class="card chart-card">
        <div class="legend">
          <span><span class="swatch" style="background:#C98500"></span>${esc(t.abbrev)}</span>
          <span><span class="swatch" style="background:#667080"></span>League median</span>
        </div>
        <div class="chart-host" id="points-host"></div>
      </div>
    </section>`;
  }

  html += `<section class="section">
    ${kicker("H2H", "Head to head", "regular season")}
    <div class="awards">
      ${D.teams.filter((x) => x.id !== t.id).map((x) => {
        const rec = D.h2h[t.id]?.[x.id];
        if (!rec) return "";
        const cls = rec.wins > rec.losses ? "pos" : rec.wins < rec.losses ? "neg" : "";
        return `<div class="award"><span class="a-label">${esc(x.abbrev)}</span>
          <span class="a-value ${cls}"><b>${rec.wins}–${rec.losses}</b></span></div>`;
      }).join("")}
    </div>
  </section>`;

  if (D.cumulative) {
    html += `<section class="section">
      ${kicker("History", "Season by season")}
      <div class="card table-scroll"><table>
        <thead><tr><th class="l">Season</th><th>RS finish</th><th>Final</th><th>W–L</th><th></th></tr></thead>
        <tbody>
          ${t.finishes.map((f) => `
            <tr>
              <td class="l">${f.season}</td>
              <td>${ordinal(f.place)}</td>
              <td>${f.final ? ordinal(f.final) : "–"}</td>
              <td>${f.wins}–${f.losses}${f.ties ? "–" + f.ties : ""}</td>
              <td>${f.champion ? "🏆 Champion" : ""}</td>
            </tr>`).join("")}
        </tbody>
      </table></div>
    </section>`;
  } else {
    html += `<section class="section">
      ${kicker("Log", "Season results")}
      <div class="card table-scroll"><table>
        <thead><tr><th>Wk</th><th class="l">Opponent</th><th>Score</th><th>Result</th></tr></thead>
        <tbody>
          ${t.weekly.map((g) => `
            <tr>
              <td>${g.week}${g.is_playoff ? '<span class="p-mark">P</span>' : ""}</td>
              <td class="l">${tname(g.opponent_id)}</td>
              <td>${f1(g.points)}–${f1(g.opponent_points)}</td>
              <td class="streak-${g.result.toLowerCase()}">${g.result}</td>
            </tr>`).join("")}
        </tbody>
      </table></div>
    </section>`;
  }

  view().innerHTML = html;

  if (!D.cumulative) {
    pointsChart(document.getElementById("points-host"), t.weekly, medians.slice(), D.regular_season_weeks);
  }

  for (const chip of view().querySelectorAll(".select-chip")) {
    chip.addEventListener("click", () => {
      location.hash = `#/teams/${chip.dataset.team}`;
    });
  }
}

/* ---------- trades ---------- */

function renderTrades() {
  const deals = D.trades || [];
  if (!deals.length) {
    view().innerHTML = `<section class="section">
      ${kicker("Trades", "The trade ledger")}
      <div class="card" style="padding:20px">No trades detected this season.</div>
    </section>`;
    return;
  }

  const playerList = (items, cls) => items.length
    ? `<ul class="t-players ${cls}">` + items.map((p) =>
        `<li><span>${esc(p.name)}</span><b>${f1(p.points_since)}</b></li>`).join("") + "</ul>"
    : "";

  const sideHtml = (side) => {
    const t = team(side.team_id);
    const wl = side.wins_with !== side.wins_without
      ? `record ${side.wins_with}W with the deal, ${side.wins_without}W without`
      : `no change in wins`;
    return `<div class="trade-side">
      <div class="ts-head">
        <span class="ts-team">${esc(t.name)}</span>
        <span class="ts-delta ${side.delta_fpts >= 0 ? "pos" : "neg"}">
          ${side.delta_fpts >= 0 ? "+" : "−"}${Math.abs(side.delta_fpts).toFixed(1)}
        </span>
      </div>
      <div class="ts-label">Got</div>
      ${playerList(side.received, "got") || '<div class="ts-none">nothing visible</div>'}
      <div class="ts-label">Gave</div>
      ${playerList(side.sent, "gave") || '<div class="ts-none">nothing visible</div>'}
      ${side.dropped?.length ? `<div class="ts-label">Cut for room</div>${playerList(side.dropped, "gave")}` : ""}
      <div class="ts-wl">${wl}</div>
    </div>`;
  };

  let html = `<section class="section">
    ${kicker("Ledger", "Who won every trade", "best-lineup points swing since the deal; ranked by impact")}
    <div class="trade-list">`;

  for (const deal of deals) {
    const winner = team(deal.verdict.winner_id);
    html += `<div class="card trade-card">
      <div class="trade-head">
        <span class="trade-week">${deal.season ? `${deal.season} · ` : ""}Week ${deal.week}</span>
        <span class="trade-verdict">${esc(winner.abbrev)} won this deal
          <b>+${deal.verdict.margin_fpts.toFixed(1)} FPts</b></span>
      </div>
      <div class="trade-sides">${deal.teams.map(sideHtml).join("")}</div>
    </div>`;
  }
  html += `</div>
    <p class="method-note">Player numbers are fantasy points since the trade. A team's +/− is
    its best-possible-lineup points swing versus a season where the deal never happened;
    wins are the same replay applied to actual matchups.</p>
  </section>`;

  view().innerHTML = html;
}

/* ---------- records ---------- */

function renderRecords() {
  const r = D.records;
  const tile = (label, value, context) => `
    <div class="tile">
      <div class="t-label">${label}</div>
      <div class="t-value">${value}</div>
      <div class="t-context">${context}</div>
    </div>`;

  const when = (rec) => `week ${rec.week}${rec.season ? `, ${rec.season}` : ""}`;
  let html = `<section class="section">
    ${kicker(D.cumulative ? "All-time" : "Season", "Records")}
    <div class="tilegrid">
      ${tile("Highest score", f1(r.highest_score.points),
        `${tname(r.highest_score.team_id)}, ${when(r.highest_score)}`)}
      ${tile("Lowest score", f1(r.lowest_score.points),
        `${tname(r.lowest_score.team_id)}, ${when(r.lowest_score)}`)}
      ${tile("Biggest beatdown", f1(r.biggest_blowout.margin),
        `${tname(r.biggest_blowout.winner_id)} ${f1(r.biggest_blowout.winner_points)}–${f1(r.biggest_blowout.loser_points)} ${tname(r.biggest_blowout.loser_id)}, ${when(r.biggest_blowout)}`)}
      ${tile("Closest call", f1(r.closest_game.margin),
        `${tname(r.closest_game.winner_id)} edges ${tname(r.closest_game.loser_id)}, ${when(r.closest_game)}`)}
    </div>
  </section>`;

  html += `<section class="section">
    ${kicker("Luck", "Wins above deserved", "all-play says who earned it")}
    <div class="card chart-card"><div class="chart-host" id="luck-host"></div></div>
  </section>`;

  html += `<section class="section">
    ${kicker("Shame", "Points left on the bench", "season totals — start your studs")}
    <div class="card chart-card"><div class="chart-host" id="bench-host"></div></div>
  </section>`;

  html += `<section class="section">
    ${kicker("Discipline", "Lineup efficiency", "actual points as a share of optimal")}
    <div class="card chart-card"><div class="chart-host" id="eff-host"></div></div>
  </section>`;

  view().innerHTML = html;

  const byLuck = [...D.teams].sort((a, b) => b.luck - a.luck);
  luckChart(document.getElementById("luck-host"), byLuck);

  const byBench = [...D.teams].sort((a, b) => b.points_benched - a.points_benched);
  hBars(document.getElementById("bench-host"),
    byBench.map((t) => ({
      label: t.abbrev,
      value: t.points_benched,
      tip: `<div class="tt-title">${esc(t.name)}</div>` +
        `<div class="tt-row"><span>Left on bench</span><b>${f1(t.points_benched)}</b></div>` +
        `<div class="tt-row"><span>Optimal total</span><b>${f1(t.optimal_points)}</b></div>`,
    })),
    { title: "Points left on the bench" });

  const byEff = [...D.teams].filter((t) => t.efficiency != null)
    .sort((a, b) => b.efficiency - a.efficiency);
  hBars(document.getElementById("eff-host"),
    byEff.map((t) => ({ label: t.abbrev, value: t.efficiency * 100 })),
    { fmt: (v) => Math.round(v) + "%", title: "Lineup efficiency" });
}

/* ---------- boot & season switching ---------- */

let dataVersion = "";

async function fetchJson(path, bustCache = false) {
  const v = bustCache ? Date.now() : dataVersion;
  const res = await fetch(v ? `${path}?v=${encodeURIComponent(v)}` : path);
  return res.ok ? res.json() : null;
}

function computeMedians() {
  medians = [];
  if (!D.weeks) return;
  const nWeeks = Math.max(...D.weeks.map((w) => w.week));
  for (let wk = 1; wk <= nWeeks; wk++) {
    const week = D.weeks.find((w) => w.week === wk);
    const scores = week
      ? week.matchups.flatMap((m) => [m.home.score, m.away.score]) : [];
    medians.push(week && !week.is_playoff ? median(scores) : null);
  }
}

function applyHeader() {
  const nameEl = document.querySelector(".league-name");
  const words = D.league_name.split(" ");
  const last = words.pop();
  nameEl.innerHTML = `${esc(words.join(" "))} <span class="accent">${esc(last)}</span>`;
  const label = D.cumulative ? "All-time" : D.season;
  document.title = `${D.league_name} · ${label}`;

  const old = document.querySelector(".badge.demo");
  if (old) old.remove();
  if (D.demo) {
    const demo = document.createElement("span");
    demo.className = "badge demo";
    demo.textContent = "Sample data";
    demo.title = "Showing generated sample data until ESPN cookies are configured.";
    document.querySelector(".bug-meta").appendChild(demo);
  }
  const updated = D.generated_at ? new Date(D.generated_at) : null;
  document.getElementById("footer-meta").textContent =
    (updated ? `Updated ${updated.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}` : "") +
    (D.demo ? " · sample data — connect ESPN cookies for the real league" : "");
}

function applyTabVisibility() {
  const matchupsTab = document.querySelector('.tab[data-page="matchups"]');
  matchupsTab.hidden = Boolean(D.cumulative);
  if (D.cumulative && parseHash().page === "matchups") {
    location.hash = "#/standings";
  }
}

async function loadSeason(key) {
  const data = await fetchJson(`data/${key}.json`);
  if (!data) return false;
  D = data;
  localStorage.setItem("ffs-season", key);
  teamById = new Map(D.teams.map((t) => [t.id, t]));
  computeMedians();
  applyHeader();
  applyTabVisibility();
  return true;
}

async function boot() {
  const manifest = await fetchJson("data/index.json", true);
  dataVersion = manifest?.generated_at || "";
  if (!manifest || !manifest.seasons?.length) {
    view().innerHTML = `<section class="section"><div class="card" style="padding:20px">
      League data has not been generated yet. Run the pipeline, then reload.
    </div></section>`;
    return;
  }

  const select = document.getElementById("season-select");
  select.innerHTML =
    manifest.seasons.map((s) => `<option value="${s}">${s}</option>`).join("") +
    `<option value="cumulative">All-time</option>`;

  const valid = [...manifest.seasons.map(String), "cumulative"];
  const saved = localStorage.getItem("ffs-season");
  const key = valid.includes(saved) ? saved : String(manifest.seasons[0]);
  select.value = key;

  select.addEventListener("change", async () => {
    if (await loadSeason(select.value)) navigate();
  });

  for (const btn of document.querySelectorAll(".tab")) {
    btn.addEventListener("click", () => { location.hash = `#/${btn.dataset.page}`; });
  }
  window.addEventListener("hashchange", navigate);

  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(navigate, 150);
  });

  if (await loadSeason(key)) navigate();
}

boot();
