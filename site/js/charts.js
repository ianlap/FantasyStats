/* Hand-rolled SVG charts. Colors are validated for the dark surface:
   gold #C98500, blue #3987E5, red #E66767 (see style.css header note). */

const NS = "http://www.w3.org/2000/svg";

const C = {
  gold: "#C98500",
  goldBright: "#F0B428",
  blue: "#3987E5",
  red: "#E66767",
  dim: "#3A4553",
  grid: "#222A35",
  axis: "#667080",
  ink: "#EEF1F6",
  ink2: "#9AA5B4",
};

function el(tag, attrs = {}, text = null) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text != null) node.textContent = text;
  return node;
}

/* ---------- shared tooltip ---------- */

let tooltip;
function tip() {
  if (!tooltip) {
    tooltip = document.createElement("div");
    tooltip.className = "viz-tooltip";
    document.body.appendChild(tooltip);
  }
  return tooltip;
}

export function showTip(html, x, y) {
  const t = tip();
  t.innerHTML = html;
  t.style.display = "block";
  const r = t.getBoundingClientRect();
  const px = Math.min(x + 14, window.innerWidth - r.width - 8);
  const py = Math.min(y + 14, window.innerHeight - r.height - 8);
  t.style.left = `${Math.max(4, px)}px`;
  t.style.top = `${Math.max(4, py)}px`;
}

export function hideTip() {
  if (tooltip) tooltip.style.display = "none";
}

function fmt1(n) {
  return Number(n).toFixed(1);
}

/* ---------- the race: rank bump chart ---------- */

export function bumpChart(host, teams, { onSelect } = {}) {
  host.innerHTML = "";
  const W = Math.max(560, host.clientWidth || 640);
  const nWeeks = teams[0].places.length;
  const n = teams.length;
  const pad = { l: 26, r: 64, t: 14, b: 26 };
  const H = 300;
  const x = (w) => pad.l + ((w - 1) / (nWeeks - 1)) * (W - pad.l - pad.r);
  const y = (p) => pad.t + ((p - 1) / (n - 1)) * (H - pad.t - pad.b);

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" });
  svg.appendChild(el("title", {}, "League place by week"));

  for (let wk = 1; wk <= nWeeks; wk++) {
    svg.appendChild(el("line", {
      x1: x(wk), x2: x(wk), y1: pad.t, y2: H - pad.b,
      stroke: C.grid, "stroke-width": 1,
    }));
    if (wk === 1 || wk % 2 === 0) {
      svg.appendChild(el("text", {
        x: x(wk), y: H - 8, fill: C.axis, "font-size": 11,
        "text-anchor": "middle",
      }, String(wk)));
    }
  }
  svg.appendChild(el("text", {
    x: pad.l - 12, y: y(1) + 4, fill: C.axis, "font-size": 11, "text-anchor": "middle",
  }, "1st"));
  svg.appendChild(el("text", {
    x: pad.l - 12, y: y(n) + 4, fill: C.axis, "font-size": 11, "text-anchor": "middle",
  }, `${n}th`));

  const lines = new Map();
  const labels = new Map();

  const paint = (selId) => {
    for (const [id, path] of lines) {
      const sel = id === selId;
      path.setAttribute("stroke", sel ? C.gold : C.dim);
      path.setAttribute("stroke-width", sel ? 3 : 2);
      path.setAttribute("opacity", selId == null || sel ? 1 : 0.55);
      if (sel) path.parentNode.appendChild(path);
    }
    for (const [id, label] of labels) {
      const sel = id === selId;
      label.setAttribute("fill", sel ? C.goldBright : C.ink2);
      label.setAttribute("font-weight", sel ? 700 : 400);
    }
  };

  for (const team of teams) {
    const d = team.places
      .map((p, i) => `${i ? "L" : "M"}${x(i + 1)},${y(p)}`)
      .join(" ");
    const path = el("path", {
      d, fill: "none", stroke: C.dim, "stroke-width": 2,
      "stroke-linejoin": "round", "stroke-linecap": "round",
    });
    svg.appendChild(path);
    lines.set(team.id, path);

    const hit = el("path", {
      d, fill: "none", stroke: "transparent", "stroke-width": 14, cursor: "pointer",
    });
    hit.addEventListener("pointermove", (e) => {
      paint(team.id);
      const wk = Math.max(1, Math.min(nWeeks,
        Math.round(1 + ((e.offsetX ?? 0) - pad.l) / ((W - pad.l - pad.r) / (nWeeks - 1)))));
      showTip(
        `<div class="tt-title">${team.name}</div>` +
        `<div class="tt-row"><span>Week ${wk}</span><b>${ordinal(team.places[wk - 1])}</b></div>`,
        e.clientX, e.clientY,
      );
    });
    hit.addEventListener("pointerleave", () => { paint(null); hideTip(); });
    if (onSelect) hit.addEventListener("click", () => onSelect(team.id));
    svg.appendChild(hit);

    const label = el("text", {
      x: x(nWeeks) + 8, y: y(team.places[nWeeks - 1]) + 4,
      fill: C.ink2, "font-size": 12,
    }, team.abbrev);
    label.style.cursor = "pointer";
    if (onSelect) label.addEventListener("click", () => onSelect(team.id));
    svg.appendChild(label);
    labels.set(team.id, label);
  }

  host.appendChild(svg);
}

export function ordinal(n) {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

/* ---------- team weekly points vs league median ---------- */

export function pointsChart(host, weekly, medians, regWeeks) {
  host.innerHTML = "";
  const W = Math.max(520, host.clientWidth || 640);
  const H = 260;
  const pad = { l: 40, r: 16, t: 14, b: 26 };
  const weeks = weekly.map((d) => d.week);
  const nWeeks = Math.max(...weeks);
  const all = weekly.map((d) => d.points).concat(medians.filter(Boolean));
  const lo = Math.floor(Math.min(...all) / 20) * 20;
  const hi = Math.ceil(Math.max(...all) / 20) * 20;
  const x = (w) => pad.l + ((w - 1) / (nWeeks - 1)) * (W - pad.l - pad.r);
  const y = (v) => pad.t + (1 - (v - lo) / (hi - lo)) * (H - pad.t - pad.b);

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" });
  svg.appendChild(el("title", {}, "Weekly points vs league median"));

  if (nWeeks > regWeeks) {
    svg.appendChild(el("rect", {
      x: x(regWeeks + 0.5), y: pad.t,
      width: x(nWeeks) - x(regWeeks + 0.5) + 8, height: H - pad.t - pad.b,
      fill: "rgba(240,180,40,0.05)",
    }));
    svg.appendChild(el("text", {
      x: x(nWeeks), y: pad.t + 12, fill: C.axis, "font-size": 10, "text-anchor": "end",
    }, "PLAYOFFS"));
  }

  for (let v = lo; v <= hi; v += 20) {
    svg.appendChild(el("line", {
      x1: pad.l, x2: W - pad.r, y1: y(v), y2: y(v), stroke: C.grid, "stroke-width": 1,
    }));
    svg.appendChild(el("text", {
      x: pad.l - 6, y: y(v) + 4, fill: C.axis, "font-size": 11, "text-anchor": "end",
    }, String(v)));
  }
  for (let wk = 1; wk <= nWeeks; wk++) {
    if (wk === 1 || wk % 2 === 0) {
      svg.appendChild(el("text", {
        x: x(wk), y: H - 8, fill: C.axis, "font-size": 11, "text-anchor": "middle",
      }, String(wk)));
    }
  }

  const medianPts = medians
    .map((m, i) => (m == null ? null : [x(i + 1), y(m)]))
    .filter(Boolean);
  svg.appendChild(el("path", {
    d: medianPts.map(([px, py], i) => `${i ? "L" : "M"}${px},${py}`).join(" "),
    fill: "none", stroke: C.axis, "stroke-width": 2, "stroke-dasharray": "5 5",
  }));

  svg.appendChild(el("path", {
    d: weekly.map((d, i) => `${i ? "L" : "M"}${x(d.week)},${y(d.points)}`).join(" "),
    fill: "none", stroke: C.gold, "stroke-width": 2.5,
    "stroke-linejoin": "round", "stroke-linecap": "round",
  }));
  for (const d of weekly) {
    svg.appendChild(el("circle", {
      cx: x(d.week), cy: y(d.points), r: 3.5,
      fill: d.result === "W" ? C.gold : "#0C0F14",
      stroke: C.gold, "stroke-width": 2,
    }));
  }

  const crosshair = el("line", {
    y1: pad.t, y2: H - pad.b, stroke: C.axis, "stroke-width": 1, opacity: 0,
  });
  svg.appendChild(crosshair);

  const overlay = el("rect", {
    x: pad.l, y: pad.t, width: W - pad.l - pad.r, height: H - pad.t - pad.b,
    fill: "transparent",
  });
  overlay.addEventListener("pointermove", (e) => {
    const wk = Math.max(1, Math.min(nWeeks,
      Math.round(1 + (e.offsetX - pad.l) / ((W - pad.l - pad.r) / (nWeeks - 1)))));
    const d = weekly.find((w) => w.week === wk);
    if (!d) return;
    crosshair.setAttribute("x1", x(wk));
    crosshair.setAttribute("x2", x(wk));
    crosshair.setAttribute("opacity", 0.5);
    const med = medians[wk - 1];
    showTip(
      `<div class="tt-title">Week ${wk} · ${d.result}</div>` +
      `<div class="tt-row"><span>Scored</span><b>${fmt1(d.points)}</b></div>` +
      `<div class="tt-row"><span>Opponent</span><b>${fmt1(d.opponent_points)}</b></div>` +
      (med != null ? `<div class="tt-row"><span>League median</span><b>${fmt1(med)}</b></div>` : ""),
      e.clientX, e.clientY,
    );
  });
  overlay.addEventListener("pointerleave", () => {
    crosshair.setAttribute("opacity", 0);
    hideTip();
  });
  svg.appendChild(overlay);

  host.appendChild(svg);
}

/* ---------- weekly lineup efficiency (percent line vs median) ---------- */

export function efficiencyChart(host, rows, medians, regWeeks) {
  host.innerHTML = "";
  const W = Math.max(520, host.clientWidth || 640);
  const H = 240;
  const pad = { l: 44, r: 16, t: 14, b: 26 };
  const nWeeks = Math.max(...rows.map((d) => d.week));
  const all = rows.map((d) => d.eff * 100).concat(
    medians.filter((m) => m != null).map((m) => m * 100));
  const lo = Math.max(0, Math.floor(Math.min(...all) / 10) * 10);
  const hi = 100;
  const x = (w) => pad.l + ((w - 1) / (nWeeks - 1)) * (W - pad.l - pad.r);
  const y = (v) => pad.t + (1 - (v - lo) / (hi - lo)) * (H - pad.t - pad.b);

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" });
  svg.appendChild(el("title", {}, "Weekly lineup efficiency vs league median"));

  if (nWeeks > regWeeks) {
    svg.appendChild(el("rect", {
      x: x(regWeeks + 0.5), y: pad.t,
      width: x(nWeeks) - x(regWeeks + 0.5) + 8, height: H - pad.t - pad.b,
      fill: "rgba(240,180,40,0.05)",
    }));
  }
  for (let v = lo; v <= hi; v += 10) {
    svg.appendChild(el("line", {
      x1: pad.l, x2: W - pad.r, y1: y(v), y2: y(v), stroke: C.grid, "stroke-width": 1,
    }));
    svg.appendChild(el("text", {
      x: pad.l - 6, y: y(v) + 4, fill: C.axis, "font-size": 11, "text-anchor": "end",
    }, `${v}%`));
  }
  for (let wk = 1; wk <= nWeeks; wk++) {
    if (wk === 1 || wk % 2 === 0) {
      svg.appendChild(el("text", {
        x: x(wk), y: H - 8, fill: C.axis, "font-size": 11, "text-anchor": "middle",
      }, String(wk)));
    }
  }

  const medPts = medians
    .map((m, i) => (m == null ? null : [x(i + 1), y(m * 100)]))
    .filter(Boolean);
  svg.appendChild(el("path", {
    d: medPts.map(([px, py], i) => `${i ? "L" : "M"}${px},${py}`).join(" "),
    fill: "none", stroke: C.axis, "stroke-width": 2, "stroke-dasharray": "5 5",
  }));

  svg.appendChild(el("path", {
    d: rows.map((d, i) => `${i ? "L" : "M"}${x(d.week)},${y(d.eff * 100)}`).join(" "),
    fill: "none", stroke: C.gold, "stroke-width": 2.5,
    "stroke-linejoin": "round", "stroke-linecap": "round",
  }));
  for (const d of rows) {
    svg.appendChild(el("circle", {
      cx: x(d.week), cy: y(d.eff * 100), r: 3.5, fill: C.gold,
    }));
  }

  const crosshair = el("line", {
    y1: pad.t, y2: H - pad.b, stroke: C.axis, "stroke-width": 1, opacity: 0,
  });
  svg.appendChild(crosshair);
  const overlay = el("rect", {
    x: pad.l, y: pad.t, width: W - pad.l - pad.r, height: H - pad.t - pad.b,
    fill: "transparent",
  });
  overlay.addEventListener("pointermove", (e) => {
    const wk = Math.max(1, Math.min(nWeeks,
      Math.round(1 + (e.offsetX - pad.l) / ((W - pad.l - pad.r) / (nWeeks - 1)))));
    const d = rows.find((r) => r.week === wk);
    if (!d) return;
    crosshair.setAttribute("x1", x(wk));
    crosshair.setAttribute("x2", x(wk));
    crosshair.setAttribute("opacity", 0.5);
    const med = medians[wk - 1];
    showTip(
      `<div class="tt-title">Week ${wk}</div>` +
      `<div class="tt-row"><span>Efficiency</span><b>${Math.round(d.eff * 100)}%</b></div>` +
      `<div class="tt-row"><span>Started</span><b>${fmt1(d.actual)}</b></div>` +
      `<div class="tt-row"><span>Optimal</span><b>${fmt1(d.optimal)}</b></div>` +
      (med != null ? `<div class="tt-row"><span>League median</span><b>${Math.round(med * 100)}%</b></div>` : ""),
      e.clientX, e.clientY,
    );
  });
  overlay.addEventListener("pointerleave", () => {
    crosshair.setAttribute("opacity", 0);
    hideTip();
  });
  svg.appendChild(overlay);

  host.appendChild(svg);
}

/* ---------- weekly bench points (bars vs median line) ---------- */

export function benchBarChart(host, rows, medians, regWeeks) {
  host.innerHTML = "";
  const W = Math.max(520, host.clientWidth || 640);
  const H = 240;
  const pad = { l: 40, r: 16, t: 14, b: 26 };
  const nWeeks = Math.max(...rows.map((d) => d.week));
  const maxV = Math.max(10, ...rows.map((d) => d.wasted),
    ...medians.filter((m) => m != null));
  const hi = Math.ceil(maxV / 10) * 10;
  const band = (W - pad.l - pad.r) / nWeeks;
  const barW = Math.max(6, band * 0.55);
  const xMid = (w) => pad.l + (w - 0.5) * band;
  const y = (v) => pad.t + (1 - v / hi) * (H - pad.t - pad.b);

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" });
  svg.appendChild(el("title", {}, "Weekly points left on the bench vs league median"));

  if (nWeeks > regWeeks) {
    svg.appendChild(el("rect", {
      x: xMid(regWeeks + 1) - band / 2, y: pad.t,
      width: (nWeeks - regWeeks) * band, height: H - pad.t - pad.b,
      fill: "rgba(240,180,40,0.05)",
    }));
  }
  for (let v = 0; v <= hi; v += hi / 4) {
    svg.appendChild(el("line", {
      x1: pad.l, x2: W - pad.r, y1: y(v), y2: y(v), stroke: C.grid, "stroke-width": 1,
    }));
    svg.appendChild(el("text", {
      x: pad.l - 6, y: y(v) + 4, fill: C.axis, "font-size": 11, "text-anchor": "end",
    }, String(Math.round(v))));
  }
  for (let wk = 1; wk <= nWeeks; wk++) {
    if (wk === 1 || wk % 2 === 0) {
      svg.appendChild(el("text", {
        x: xMid(wk), y: H - 8, fill: C.axis, "font-size": 11, "text-anchor": "middle",
      }, String(wk)));
    }
  }

  for (const d of rows) {
    const h = Math.max(1, y(0) - y(d.wasted));
    svg.appendChild(el("rect", {
      x: xMid(d.week) - barW / 2, y: y(d.wasted), width: barW, height: h,
      rx: 3, fill: C.gold,
    }));
  }

  const medPts = medians
    .map((m, i) => (m == null ? null : [xMid(i + 1), y(m)]))
    .filter(Boolean);
  svg.appendChild(el("path", {
    d: medPts.map(([px, py], i) => `${i ? "L" : "M"}${px},${py}`).join(" "),
    fill: "none", stroke: C.axis, "stroke-width": 2, "stroke-dasharray": "5 5",
  }));

  for (const d of rows) {
    const hit = el("rect", {
      x: xMid(d.week) - band / 2, y: pad.t, width: band, height: H - pad.t - pad.b,
      fill: "transparent",
    });
    hit.addEventListener("pointermove", (e) => {
      const med = medians[d.week - 1];
      showTip(
        `<div class="tt-title">Week ${d.week}</div>` +
        `<div class="tt-row"><span>Left on bench</span><b>${fmt1(d.wasted)}</b></div>` +
        `<div class="tt-row"><span>Started</span><b>${fmt1(d.actual)}</b></div>` +
        `<div class="tt-row"><span>Optimal</span><b>${fmt1(d.optimal)}</b></div>` +
        (med != null ? `<div class="tt-row"><span>League median</span><b>${fmt1(med)}</b></div>` : ""),
        e.clientX, e.clientY,
      );
    });
    hit.addEventListener("pointerleave", hideTip);
    svg.appendChild(hit);
  }

  host.appendChild(svg);
}

/* ---------- diverging luck bars ---------- */

export function luckChart(host, teams) {
  host.innerHTML = "";
  const W = Math.max(480, host.clientWidth || 640);
  const rowH = 26;
  const pad = { l: 52, r: 52, t: 8, b: 22 };
  const H = pad.t + teams.length * rowH + pad.b;
  const maxAbs = Math.max(0.5, ...teams.map((t) => Math.abs(t.luck)));
  const mid = pad.l + (W - pad.l - pad.r) / 2;
  const scale = (W - pad.l - pad.r) / 2 / maxAbs;

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" });
  svg.appendChild(el("title", {}, "Luck: wins above or below deserved"));

  svg.appendChild(el("line", {
    x1: mid, x2: mid, y1: pad.t, y2: H - pad.b, stroke: "#383835", "stroke-width": 1.5,
  }));

  teams.forEach((t, i) => {
    const cy = pad.t + i * rowH + rowH / 2;
    const w = Math.abs(t.luck) * scale;
    const barH = 14;
    const positive = t.luck >= 0;
    const bar = el("rect", {
      x: positive ? mid : mid - w,
      y: cy - barH / 2,
      width: Math.max(w, 1),
      height: barH,
      rx: 3,
      fill: positive ? C.blue : C.red,
    });
    svg.appendChild(bar);

    svg.appendChild(el("text", {
      x: positive ? mid - 8 : mid + 8,
      y: cy + 4,
      fill: C.ink2,
      "font-size": 12,
      "text-anchor": positive ? "end" : "start",
    }, t.abbrev));

    svg.appendChild(el("text", {
      x: positive ? mid + w + 6 : mid - w - 6,
      y: cy + 4,
      fill: C.ink,
      "font-size": 12,
      "font-weight": 600,
      "text-anchor": positive ? "start" : "end",
    }, `${positive ? "+" : "−"}${Math.abs(t.luck).toFixed(1)}`));

    const hit = el("rect", {
      x: pad.l - 40, y: cy - rowH / 2, width: W - pad.l - pad.r + 80, height: rowH,
      fill: "transparent",
    });
    hit.addEventListener("pointermove", (e) => {
      const deserved = (t.wins - t.luck).toFixed(1);
      showTip(
        `<div class="tt-title">${t.name}</div>` +
        `<div class="tt-row"><span>Actual wins</span><b>${t.wins}</b></div>` +
        `<div class="tt-row"><span>Deserved wins</span><b>${deserved}</b></div>` +
        `<div class="tt-row"><span>All-play</span><b>${t.allplay_wins}–${t.allplay_losses}</b></div>`,
        e.clientX, e.clientY,
      );
    });
    hit.addEventListener("pointerleave", hideTip);
    svg.appendChild(hit);
  });

  svg.appendChild(el("text", {
    x: mid - 10, y: H - 6, fill: C.axis, "font-size": 10.5, "text-anchor": "end",
  }, "← UNLUCKY"));
  svg.appendChild(el("text", {
    x: mid + 10, y: H - 6, fill: C.axis, "font-size": 10.5,
  }, "LUCKY →"));

  host.appendChild(svg);
}

/* ---------- simple horizontal bars ---------- */

export function hBars(host, items, { color = C.gold, fmt = fmt1, title = "" } = {}) {
  host.innerHTML = "";
  const W = Math.max(440, host.clientWidth || 640);
  const rowH = 26;
  const pad = { l: 56, r: 64, t: 6, b: 6 };
  const H = pad.t + items.length * rowH + pad.b;
  const max = Math.max(...items.map((d) => d.value));
  const scale = (W - pad.l - pad.r) / (max || 1);

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" });
  if (title) svg.appendChild(el("title", {}, title));

  items.forEach((d, i) => {
    const cy = pad.t + i * rowH + rowH / 2;
    svg.appendChild(el("text", {
      x: pad.l - 8, y: cy + 4, fill: C.ink2, "font-size": 12, "text-anchor": "end",
    }, d.label));
    svg.appendChild(el("rect", {
      x: pad.l, y: cy - 7, width: Math.max(d.value * scale, 1), height: 14, rx: 3,
      fill: color,
    }));
    svg.appendChild(el("text", {
      x: pad.l + d.value * scale + 6, y: cy + 4,
      fill: C.ink, "font-size": 12, "font-weight": 600,
    }, fmt(d.value)));
    if (d.tip) {
      const hit = el("rect", {
        x: 0, y: cy - rowH / 2, width: W, height: rowH, fill: "transparent",
      });
      hit.addEventListener("pointermove", (e) => showTip(d.tip, e.clientX, e.clientY));
      hit.addEventListener("pointerleave", hideTip);
      svg.appendChild(hit);
    }
  });

  host.appendChild(svg);
}

/* ---------- champion pennant ---------- */

export function pennant(host, text) {
  const W = 210, H = 92;
  const svg = el("svg", {
    viewBox: `0 0 ${W} ${H}`, width: W, height: H, class: "pennant", role: "img",
  });
  svg.appendChild(el("title", {}, `League champion: ${text}`));
  svg.appendChild(el("rect", { x: 2, y: 4, width: 5, height: 84, rx: 2, fill: "#4A5462" }));
  svg.appendChild(el("polygon", {
    points: `10,8 ${W - 4},${H / 2} 10,${H - 8}`,
    fill: "#C98500",
    stroke: "#F0B428",
    "stroke-width": 1.5,
  }));
  svg.appendChild(el("polygon", {
    points: `10,8 ${W - 4},${H / 2} 10,${H - 8}`,
    fill: "url(#pennantShade)",
  }));
  const defs = el("defs");
  const grad = el("linearGradient", { id: "pennantShade", x1: 0, y1: 0, x2: 1, y2: 0 });
  grad.appendChild(el("stop", { offset: "0%", "stop-color": "rgba(0,0,0,0.25)" }));
  grad.appendChild(el("stop", { offset: "100%", "stop-color": "rgba(0,0,0,0)" }));
  defs.appendChild(grad);
  svg.appendChild(defs);
  const label = el("text", {
    x: 22, y: H / 2 + 6, fill: "#14100A",
    "font-size": 17, "font-weight": 700, "letter-spacing": "0.08em",
  }, text.toUpperCase());
  label.style.fontFamily = '"Barlow Condensed", "Arial Narrow", sans-serif';
  svg.appendChild(label);
  host.appendChild(svg);
}
