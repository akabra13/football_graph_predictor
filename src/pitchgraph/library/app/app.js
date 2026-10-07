/* PitchGraph Library: one page over the season JSON files.
   Routes are bare anchors: #find, #map, #method, #team-<season>-<id>,
   #vs-<season>-<teamA>-<teamB>. A standalone report sets window.PG_DATA
   (one season) and window.PG_START (the route to open). */
(function () {
  "use strict";

  const app = document.getElementById("app");
  const seasons = {};
  let index = null;

  // Results of the validation suite, shown on the Method page. Notebook 02
  // writes validation.json from the full lake; until then these are the
  // four-league results measured during development.
  const VALIDATION_FALLBACK = {
    scope: "four leagues streamed during development: Premier League and Serie A 2015/16, WSL 2020/21, Liga F 2023/24",
    reid: [["Premier League 15/16", 0.90, 0.05], ["Serie A 15/16", 0.95, 0.05],
           ["WSL 20/21", 0.50, 0.08], ["Liga F 23/24", 0.75, 0.06]],
    lanes: [["Premier League 15/16", 0.0014, 0.0027], ["Serie A 15/16", 0.0007, 0.0021],
            ["WSL 20/21", 0.0002, 0.0028], ["Liga F 23/24", -0.0004, 0.0013]],
    volume: [["Premier League 15/16", -0.0008, 0.0021], ["Serie A 15/16", -0.0034, -0.0001],
             ["WSL 20/21", -0.0051, 0.0002], ["Liga F 23/24", -0.0023, 0.0050]],
    missed: { n: 781, r: 0.081, p: 0.011 },
  };

  // ---- helpers ----------------------------------------------------------------
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (v, d = 0) => (v == null ? "n/a" : (100 * v).toFixed(d) + "%");
  const signed = (v) => (v == null ? "n/a" : (v >= 0 ? "+" : "") + (100 * v).toFixed(0) + "%");
  const fmt = (f, v) => {
    if (v == null) return "n/a";
    if (f.includes("%")) return (100 * v).toFixed(1) + "%";
    const m = f.match(/\.(\d)f/);
    return v.toFixed(m ? +m[1] : 2);
  };
  const SECTION_TAG = { buildup: ["attack", "own"], pressing: ["press", "own"], vulnerability: ["defence", "opp"] };
  const LANE_Y = [9, 24, 40, 56, 71];
  const REGION_X = [20, 60, 100];
  const regionXY = (r) => [REGION_X[Math.floor(r / 5)], LANE_Y[r % 5]];

  async function getIndex() {
    if (index) return index;
    if (window.PG_DATA) {
      const d = window.PG_DATA;
      index = { seasons: { [d.key]: { key: d.key, competition: d.competition, season: d.season, gender: d.gender,
        teams: Object.values(d.teams).map((t) => ({ id: t.id, name: t.name, matches: t.matches, small_sample: t.small_sample })) } } };
      seasons[d.key] = d;
      return index;
    }
    const r = await fetch("index.json");
    if (!r.ok) throw new Error("The library index could not be loaded.");
    index = await r.json();
    return index;
  }

  async function getSeason(key) {
    if (seasons[key]) return seasons[key];
    const r = await fetch(`seasons/${key}.json`);
    if (!r.ok) throw new Error(`Season ${key} is not in this library.`);
    seasons[key] = await r.json();
    return seasons[key];
  }

  // ---- pitch drawing --------------------------------------------------------------
  function pitch(inner, label, lanes) {
    let m = '<rect x="0" y="0" width="120" height="80" class="turf"/><rect x="0" y="0" width="120" height="80" class="line"/>' +
      '<line x1="60" y1="0" x2="60" y2="80" class="line"/><circle cx="60" cy="40" r="10" class="line"/>' +
      '<rect x="102" y="18" width="18" height="44" class="line"/><rect x="114" y="30" width="6" height="20" class="line"/>' +
      '<rect x="0" y="18" width="18" height="44" class="line"/><rect x="0" y="30" width="6" height="20" class="line"/>' +
      '<rect x="120" y="36" width="1.6" height="8" class="goal"/><rect x="-1.6" y="36" width="1.6" height="8" class="goal"/>';
    if (lanes) {
      for (const y of [18, 30, 50, 62]) m += `<line x1="0" y1="${y}" x2="120" y2="${y}" class="lane"/>`;
      for (const x of [40, 80]) m += `<line x1="${x}" y1="0" x2="${x}" y2="80" class="third"/>`;
    }
    m += '<text x="118" y="-1.8" class="dir" text-anchor="end">attacking &#8594;</text>';
    const defs = '<defs><marker id="ah" viewBox="0 0 6 6" refX="4.5" refY="3" markerWidth="3.2" markerHeight="3.2" orient="auto"><path d="M0,0 L6,3 L0,6 z" class="head"/></marker>' +
      '<marker id="ahm" viewBox="0 0 6 6" refX="4.5" refY="3" markerWidth="3.2" markerHeight="3.2" orient="auto"><path d="M0,0 L6,3 L0,6 z" class="head-muted"/></marker></defs>';
    return `<div class="scroll"><svg viewBox="-3 -5 126 88" class="pitch" role="img" aria-label="${esc(label)}">${defs}${m}${inner}</svg></div>`;
  }

  function flowSvg(flow) {
    if (!flow || !flow.length) return "";
    const top = Math.max(...flow.map((f) => f.flow));
    let s = "";
    for (const f of [...flow].reverse()) {
      const [x0, y0] = regionXY(f.from), [x1, y1] = regionXY(f.to);
      const cls = f.vs_league == null ? "usual" : f.vs_league >= 1.1 ? "more" : f.vs_league <= 0.9 ? "less" : "usual";
      const w = 0.5 + 3.2 * f.flow / top;
      const mx = (x0 + x1) / 2 + (y1 - y0) * 0.12, my = (y0 + y1) / 2 - (x1 - x0) * 0.12;
      s += `<path d="M${x0},${y0} Q${mx},${my} ${x1},${y1}" class="route ${cls}" stroke-width="${w.toFixed(2)}" marker-end="url(#${cls === "more" ? "ah" : "ahm"})"><title>${esc(f.from_label)} to ${esc(f.to_label)}: ${f.vs_league == null ? "" : f.vs_league.toFixed(2) + "x the league"}</title></path>`;
    }
    return pitch(s, "Strongest links in their flow graph", true);
  }

  function routesSvg(routes) {
    if (!routes || !routes.length) return "";
    const top = Math.max(...routes.map((r) => r.share));
    const Y = { wide_left: 9, halfspace_left: 24, centre: 40, halfspace_right: 56, wide_right: 71 };
    let s = "";
    for (const r of [...routes].sort((a, b) => a.share - b.share)) {
      const y0 = Y[r.from], y1 = Y[r.to], w = 0.6 + 3.4 * r.share / top;
      s += `<path d="M40,${y0} Q60,${(y0 + y1) / 2 + (y1 - y0) * 0.15} 80,${y1}" class="route more" stroke-width="${w.toFixed(2)}" marker-end="url(#ah)"/>` +
        `<text x="63" y="${((y0 + y1) / 2 - 1.2).toFixed(1)}" class="lbl">${pct(r.share)}</text>`;
    }
    return pitch(s, "Most common progression routes", true);
  }

  function networkSvg(nodes, links, sizeKey, linkKey, kind, label) {
    if (!nodes || !nodes.length) return "";
    const by = {};
    for (const n of nodes) by[n.id ?? n.name] = n;
    const topL = Math.max(1e-9, ...links.map((l) => l[linkKey]));
    const topN = Math.max(1e-9, ...nodes.map((n) => n[sizeKey]));
    let s = "";
    for (const l of links) {
      const a = by[l.a], b = by[l.b];
      if (!a || !b) continue;
      s += `<line x1="${a.x.toFixed(1)}" y1="${a.y.toFixed(1)}" x2="${b.x.toFixed(1)}" y2="${b.y.toFixed(1)}" class="edge ${kind}" stroke-width="${(0.25 + 2.2 * l[linkKey] / topL).toFixed(2)}"/>`;
    }
    for (const n of nodes) {
      const r = 1.3 + 3.6 * Math.sqrt(Math.max(0, n[sizeKey]) / topN);
      s += `<circle cx="${n.x.toFixed(1)}" cy="${n.y.toFixed(1)}" r="${r.toFixed(2)}" class="node ${kind}"/>` +
        `<text x="${n.x.toFixed(1)}" y="${(n.y + r + 3.2).toFixed(1)}" class="name" text-anchor="middle">${esc(n.name)}</text>`;
    }
    return pitch(s, label, false);
  }

  // ---- building blocks -------------------------------------------------------------
  function ladder(rank, of) {
    const pos = of - rank;
    let cells = "";
    for (let i = 0; i < of; i++) cells += `<span class="${i === pos ? "on" : ""}${i === Math.floor(of / 2) ? " mid" : ""}"></span>`;
    return `<span class="ladder" aria-label="rank ${rank} of ${of}"><small>low</small>${cells}<small>high</small></span>`;
  }

  function claimRow(c) {
    const range = c.lo == null ? "range unavailable" : `90% range ${fmt(c.fmt, c.lo)} to ${fmt(c.fmt, c.hi)}`;
    return `<div class="claim"><div class="label">${esc(c.label)}</div><div class="val">${fmt(c.fmt, c.value)}</div>` +
      `<div class="sub">${ladder(c.rank, c.of)}<span>league median <span class="mono">${fmt(c.fmt, c.league)}</span></span>` +
      `<span class="mono">${range}</span><span class="conf ${c.confidence}">${c.confidence}</span></div></div>`;
  }

  function bars(rows, labelKey, kind, altKey) {
    const top = Math.max(1e-9, ...rows.map((r) => Math.max(r.share, r.league ?? 0, altKey ? r[altKey] : 0)));
    return '<div class="bars">' + rows.map((r) =>
      `<div class="bar"><span>${esc(r[labelKey])}</span><span class="track">` +
      `<span class="fill ${kind}" style="width:${(100 * r.share / top).toFixed(1)}%"></span>` +
      (altKey ? `<span class="fill alt" style="width:${(100 * r[altKey] / top).toFixed(1)}%"></span>` : "") +
      (r.league != null ? `<span class="tick" style="left:${(100 * r.league / top).toFixed(1)}%"></span>` : "") +
      `</span><span class="mono">${pct(r.share)}</span></div>`).join("") + "</div>";
  }

  // A drop range bar: [adapt, no-adapt] for the team, dotted line = league midpoint.
  function lever(what, sub, lo, hi, leagueLo, leagueHi) {
    const scale = 0.6;   // the bar spans 0-60% threat removed
    const L = (v) => Math.max(0, Math.min(1, v / scale)) * 100;
    const lg = leagueLo == null ? "" : `<span class="lg" style="left:${L((leagueLo + leagueHi) / 2).toFixed(1)}%" title="average team"></span>`;
    return `<div class="lever"><div class="what">${what}<small>${sub}</small></div>` +
      `<div class="range"><span class="span" style="left:${L(Math.max(0, lo)).toFixed(1)}%;width:${Math.max(1, L(hi) - L(Math.max(0, lo))).toFixed(1)}%"></span>${lg}</div>` +
      `<div class="range-lbl"><span>${lo < 0 ? "no clear cost" : pct(lo)} to ${pct(hi)}</span>${leagueLo == null ? "" : `<span>average team ${pct((leagueLo + leagueHi) / 2)}</span>`}</div></div>`;
  }

  const linkName = (l) => `${esc(l.from || l.from_label)} &#8594; ${esc(l.to || l.to_label)}`;

  // ---- views ---------------------------------------------------------------------------
  function nav(active) {
    const tab = (id, label) => `<a class="tab" href="#${id}"${active === id ? ' aria-current="page"' : ""}>${label}</a>`;
    return `<nav class="nav"><div class="nav-in"><a class="brand" href="#find">PitchGraph Library</a>${tab("find", "Find")}${tab("map", "Style map")}${tab("method", "Method")}</div></nav>`;
  }

  function footer() {
    return '<footer><p><b>Data: StatsBomb Open Data.</b> Every figure is compared with the other teams in the same competition and season. ' +
      'Ranges come from resampling whole matches. See Method for what has and has not been validated.</p></footer>';
  }

  async function viewFind() {
    const idx = await getIndex();
    const list = Object.values(idx.seasons).sort((a, b) => (a.competition + a.season).localeCompare(b.competition + b.season));
    app.innerHTML = nav("find") + `<div class="wrap"><header class="page"><div class="eyebrow">Scouting library</div>` +
      `<h1>Find a team</h1><p>Every team with enough matches to compare against its league: how they play, how to stop them, and what to expect in a matchup.</p></header>` +
      `<section><div class="search"><label class="eyebrow" for="q">Team</label><input id="q" type="search" placeholder="e.g. Leicester, Arsenal WFC, Barcelona" autocomplete="off">` +
      `<label class="eyebrow" for="g">Game</label><select id="g"><option value="">All</option><option value="male">Men's</option><option value="female">Women's</option></select></div>` +
      `<div class="seasons" id="list"></div></section>${footer()}</div>`;
    const q = document.getElementById("q"), g = document.getElementById("g"), out = document.getElementById("list");
    try { const saved = localStorage.getItem("pg-gender"); if (saved) g.value = saved; } catch (e) { /* storage unavailable */ }
    function draw() {
      const term = q.value.trim().toLowerCase();
      let html = "";
      for (const s of list) {
        if (g.value && s.gender !== g.value) continue;
        const teams = s.teams.filter((t) => !term || t.name.toLowerCase().includes(term));
        if (!teams.length) continue;
        html += `<div class="season"><h3>${esc(s.competition)} ${esc(s.season)} <small>${s.teams.length} teams</small></h3><div class="chips">` +
          teams.sort((a, b) => a.name.localeCompare(b.name)).map((t) =>
            `<a class="chip${t.small_sample ? " small" : ""}" href="#team-${s.key}-${t.id}" title="${t.matches} matches">${esc(t.name)}</a>`).join("") + "</div></div>";
      }
      out.innerHTML = html || '<p class="empty">No team matches that search.</p>';
    }
    q.addEventListener("input", draw);
    g.addEventListener("change", () => { try { localStorage.setItem("pg-gender", g.value); } catch (e) { /* ignore */ } draw(); });
    draw();
  }

  async function viewMap() {
    const idx = await getIndex();
    let points = idx.style_map ? idx.style_map.points : null;
    const genders = {};
    for (const s of Object.values(idx.seasons)) genders[s.key] = s.gender;
    if (!points) {   // standalone report: one season's map
      const d = Object.values(seasons)[0];
      points = Object.values(d.teams).filter((t) => t.style_xy).map((t) => ({ season: d.key, team_id: t.id, name: t.name, x: t.style_xy[0], y: t.style_xy[1] }));
    }
    const xs = points.map((p) => p.x), ys = points.map((p) => p.y);
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const W = 600, H = 420, pad = 24;
    const X = (v) => pad + (W - 2 * pad) * (v - x0) / ((x1 - x0) || 1), Y = (v) => pad + (H - 2 * pad) * (v - y0) / ((y1 - y0) || 1);
    const label = (p) => `${p.name}, ${idx.seasons[p.season] ? idx.seasons[p.season].competition + " " + idx.seasons[p.season].season : p.season}`;
    const dots = points.map((p, i) => `<a href="#team-${p.season}-${p.team_id}"><circle data-i="${i}" cx="${X(p.x).toFixed(1)}" cy="${Y(p.y).toFixed(1)}" r="4.5" class="${genders[p.season] === "female" ? "f" : "m"}"><title>${esc(label(p))}</title></circle></a>`).join("");
    app.innerHTML = nav("map") + `<div class="wrap"><header class="page"><div class="eyebrow">Style map</div><h1>Who plays like whom</h1>` +
      `<p>Each dot is a team-season, placed so that teams with similar flow graphs sit close together. Hover to name a team, click to open it.</p></header>` +
      `<section><div class="legend"><span><span class="dot" style="background:var(--blue)"></span>Men's</span><span><span class="dot" style="background:var(--red)"></span>Women's</span></div>` +
      `<div class="scroll"><svg class="map" viewBox="0 0 ${W} ${H}" role="img" aria-label="Style map of all teams">${dots}<text id="hover" x="12" y="${H - 10}"></text></svg></div>` +
      `<p class="note">Style is validated within a season: a team's flow graph from half its matches picks out its own other half (see Method). Distances across leagues and eras also carry league-wide differences, so treat cross-league neighbours as exploratory.</p></section>${footer()}</div>`;
    const hover = document.getElementById("hover");
    app.querySelectorAll("svg.map circle").forEach((c) => {
      c.addEventListener("mouseenter", () => { hover.textContent = label(points[+c.dataset.i]); c.classList.add("hi"); });
      c.addEventListener("mouseleave", () => { hover.textContent = ""; c.classList.remove("hi"); });
    });
  }

  async function viewTeam(key, id) {
    const s = await getSeason(key);
    const t = s.teams[id];
    if (!t) throw new Error("That team is not in this season of the library.");
    const claims = t.claims, byKey = Object.fromEntries(claims.map((c) => [c.key, c]));
    const others = Object.values(s.teams).filter((o) => o.id !== t.id).sort((a, b) => a.name.localeCompare(b.name));
    const sect = (name) => claims.filter((c) => c.section === name).map(claimRow).join("");
    const d = t.denial, df = t.defence, ex = t.exposure, pr = t.pressing;
    const removal = t.players.nodes.filter((n) => n.removal).sort((a, b) => (b.removal[0] + b.removal[1]) - (a.removal[0] + a.removal[1])).slice(0, 4);

    app.innerHTML = nav("") + `<div class="wrap">` +
      `<header class="page"><div class="eyebrow">Opposition report &middot; ${esc(s.competition)} ${esc(s.season)}</div><h1>${esc(t.name)}</h1>` +
      `<div class="meta"><span><b>${t.matches}</b> matches</span><span>compared with <b>${claims[0].of}</b> teams</span>` +
      `<span>data: <b>${t.has_360 ? "events + 360" : "events"}</b></span><span>claims stable across halves of the season: <b>${pct(t.agreement)}</b></span></div>` +
      (t.small_sample ? `<p class="warning">Only ${t.matches} matches. Ranges are wide and most claims cannot be established; read this as a sketch, not a scouting conclusion.</p>` : "") +
      `<div class="vs"><label class="eyebrow" for="opp">Plan against</label><select id="opp"><option value="">choose an opponent</option>` +
      others.map((o) => `<option value="${o.id}">${esc(o.name)}</option>`).join("") + `</select></div></header>` +

      `<section class="summary"><h2>In short</h2><p class="note">The strongest findings: high confidence, furthest from the league middle.</p><ol>` +
      (t.headlines.length ? t.headlines.map((k) => { const c = byKey[k]; const [tag, cls] = SECTION_TAG[c.section]; return `<li>${esc(c.sentence)}<span class="tag ${cls}">${tag}</span></li>`; }).join("")
        : "<li>No claim is established with high confidence yet.</li>") + `</ol></section>` +

      `<section class="own"><div class="section-head"><h2>How to stop them</h2><p class="note">What taking away each connection would cost them, as a range: the ball is lost every time (top of the bar) to they simply play their next-best option (bottom). The dotted line is what the same denial costs an average team in this league.</p></div>` +
      `<div class="figs"><div class="levers"><h3>Biggest levers</h3>${d.links.map((l) => lever(linkName(l), `${pct(l.usage, 1)} of their moves`, l.drop_adapt, l.drop_no_adapt, l.league_drop_adapt, l.league_drop_no_adapt)).join("")}</div>` +
      `<div class="levers"><h3>Their players</h3>${removal.map((n) => lever(esc(n.full), `${pct(n.involvement)} of their threat involves them`, n.removal[0], n.removal[1], null, null)).join("")}` +
      `<p class="note">Player effects come from a player-level flow graph. Checked against 781 real absences, predicted and actual drops agree only weakly (r = 0.08): use this to see who the threat runs through, not to forecast results without a player.</p></div></div>` +
      ((d.unusual_links || []).length ? `<div class="callout"><b>Specific to ${esc(t.name)}</b><ul>${d.unusual_links.map((l) => `<li>${linkName(l)}: costs them ${pct((l.drop_adapt + l.drop_no_adapt) / 2)}, an average team ${pct((l.league_drop_adapt + l.league_drop_no_adapt) / 2)}</li>`).join("")}</ul></div>` : "") +
      `</section>` +

      `<section class="own"><div class="section-head"><h2>How they play</h2></div>` +
      `<div class="figs"><figure>${flowSvg(t.flow)}<figcaption>Their strongest links between regions (thirds &times; lanes) in their flow graph. Blue arrows are links they use at least 10% more than the league; grey ones are around or below league level.</figcaption></figure>` +
      `<figure><h3>Plays most like</h3><ul>${(t.similar || []).map((o) => `<li><a href="#team-${key}-${o.team_id}">${esc(o.name)}</a></li>`).join("") || "<li>Not enough teams to compare.</li>"}</ul>` +
      `<p class="note">By flow-graph distance within this season. Expected threat per possession: <b class="mono">${t.threat_per_possession == null ? "n/a" : t.threat_per_possession.toFixed(4)}</b>.</p></figure></div>` +
      `<div class="claims">${sect("buildup")}</div>` +
      `<div class="figs"><figure>${routesSvg(t.routes)}<figcaption>Their five most common routes: the lane where the ball crossed into the middle third (x=40), joined to the lane where it crossed into the final third (x=80).</figcaption></figure>` +
      `<figure>${networkSvg(t.players.nodes, t.players.links, "involvement", "v", "own", "Who the threat flows through")}<figcaption>Circle size is each player's share of the value the team adds; lines are their most valuable passing links, at median on-ball positions.</figcaption></figure></div>` +
      `<div class="scroll"><table><thead><tr><th>Player</th><th class="n">Involved in threat</th><th class="n">Created</th><th class="n">In final-third entries</th></tr></thead><tbody>` +
      t.players.nodes.slice(0, 8).map((p) => `<tr><td>${esc(p.full)}</td><td class="n">${pct(p.involvement)}</td><td class="n">${pct(p.created)}</td><td class="n">${pct(p.dependency)}</td></tr>`).join("") +
      `</tbody></table></div></section>` +

      `<section class="own"><div class="section-head"><h2>How they press</h2></div><div class="claims">${sect("pressing")}</div>` +
      `<div class="figs"><figure>${networkSvg(pr.nodes, pr.pairs, "n", "n", "own", "Co-pressing units")}<figcaption>Who presses together: circle size is pressures made; a line joins two players when one pressed within two seconds of the other.</figcaption></figure>` +
      `<figure><h3>Who they press first</h3>${bars(pr.pressed.map((r) => ({ ...r, label: r.position })), "label", "own")}<figcaption>Position of the opponent on the ball when their press starts (tick = league share).</figcaption></figure></div></section>` +

      `<section class="opp"><div class="section-head"><h2>Where they are vulnerable</h2></div><div class="claims">${sect("vulnerability")}</div>` +
      `<div class="figs"><figure><h3>Where opponents get into the final third</h3>${bars(ex.lanes.map((r) => ({ ...r, label: r.side })), "label", "opp")}<figcaption>By lane, named from ${esc(t.name)}'s side of the pitch (tick = league share).</figcaption></figure>` +
      `<figure><h3>Threat conceded per opponent possession</h3><div class="states">${["leading", "level", "trailing"].map((st) => `<div><span>when ${st}</span><b>${ex.states[st] == null ? "n/a" : ex.states[st].toFixed(3)}</b><span>league ${ex.league_states[st] == null ? "n/a" : ex.league_states[st].toFixed(3)}</span></div>`).join("")}</div>` +
      (t.opp_adjusted.value == null ? "" : `<p class="note">Opponents made ${t.opp_adjusted.value >= 0 ? "+" : ""}${t.opp_adjusted.value.toFixed(2)} threat per match against them compared with their own average elsewhere (${t.opp_adjusted.matches} matches). Negative means they hold teams below their usual level.</p>`) + `</figure></div>` +
      `<div class="figs"><div class="levers"><h3>Protect these</h3><p class="note">Opponents' routes that the threat against ${esc(t.name)} depends on most.</p>${df.protect.map((l) => lever(linkName(l), `${pct(l.usage, 1)} of opponents' moves`, l.drop_adapt, l.drop_no_adapt, l.league_drop_adapt, l.league_drop_no_adapt)).join("")}</div>` +
      `<figure><h3>Moments to watch: down their ${esc(ex.worst.side)}</h3><div class="scroll"><table><thead><tr><th>Match</th><th class="n">Minute</th><th>Entry by</th><th class="n">xG after</th></tr></thead><tbody>` +
      ex.moments.map((m) => `<tr><td>${esc(m.match)}</td><td class="n">${m.minute}'</td><td>${esc(m.by)}</td><td class="n">${m.xg.toFixed(2)}</td></tr>`).join("") +
      `</tbody></table></div><figcaption>Their most dangerous concessions through the lane where they are hit more than the league average. Find these in the match video.</figcaption></figure></div></section>` +
      footer() + `</div>`;

    document.getElementById("opp").addEventListener("change", (e) => { if (e.target.value) location.hash = `#vs-${key}-${id}-${e.target.value}`; });
  }

  async function viewMatchup(key, a, b) {
    const s = await getSeason(key);
    const A = s.teams[a], B = s.teams[b], m = s.matchups && s.matchups[`${a}-${b}`], back = s.matchups && s.matchups[`${b}-${a}`];
    if (!A || !B || !m) throw new Error("That matchup is not in this library.");
    const lanes = s.lane_names.map((name, k) => ({ label: name, share: m.lanes_matchup[k], league: null, alt: m.lanes_own[k] }));
    const options = (sel, other) => Object.values(s.teams).filter((o) => o.id !== other).sort((x, y) => x.name.localeCompare(y.name))
      .map((o) => `<option value="${o.id}"${o.id === sel ? " selected" : ""}>${esc(o.name)}</option>`).join("");
    const change = (l) => `<li>${esc(l.from_label)} &#8594; ${esc(l.to_label)} <span class="mono">${signed(l.change)}</span></li>`;
    app.innerHTML = nav("") + `<div class="wrap"><header class="page"><div class="eyebrow">Matchup &middot; ${esc(s.competition)} ${esc(s.season)}</div>` +
      `<h1>${esc(A.name)} attacking ${esc(B.name)}</h1>` +
      `<div class="vs"><label class="eyebrow" for="ta">Attack</label><select id="ta">${options(+a, +b)}</select><label class="eyebrow" for="tb">Defence</label><select id="tb">${options(+b, +a)}</select>` +
      `<a href="#vs-${key}-${b}-${a}">Swap sides</a></div></header>` +
      `<section class="own"><div class="two"><div><div class="eyebrow">Expected threat vs their usual</div><div class="big">${signed(m.threat_vs_usual)}</div>` +
      `<p class="note">${esc(B.name)} concede ${m.threat_vs_usual >= 0 ? "more" : "less"} than the average side. Threat volume follows strength (attack level &times; how much the defence concedes); the detailed matchup adds nothing to volume in validation, so this is the number to trust.</p></div>` +
      `<div><div class="eyebrow">Their expected final-third entries by lane</div>${bars(lanes, "label", "own", "alt")}<p class="note">Blue: expected against ${esc(B.name)}. Grey: ${esc(A.name)}'s usual. Validated: matchups shift <i>where</i> a team attacks, modestly but reliably in 3 of 4 test leagues.</p></div></div></section>` +
      `<section class="own"><div class="two"><div class="callout"><b>${esc(B.name)} give them more of</b><ul>${m.more_of.map(change).join("")}</ul></div>` +
      `<div class="callout"><b>${esc(B.name)} take away</b><ul>${m.less_of.map(change).join("")}</ul></div></div>` +
      `<p class="note">Change in how often ${esc(A.name)} use each link when ${esc(B.name)}'s leakiness is applied to their habits.</p></section>` +
      `<section class="opp"><div class="section-head"><h2>Head to head</h2></div>` +
      (m.head_to_head.length ? `<div class="scroll"><table><thead><tr><th>Date</th><th class="n">Score</th><th class="n">xG</th></tr></thead><tbody>` +
        m.head_to_head.map((h) => `<tr><td>${esc(h.date)}</td><td class="n">${h.score[0]}&ndash;${h.score[1]}</td><td class="n">${h.xg[0].toFixed(2)}&ndash;${h.xg[1].toFixed(2)}</td></tr>`).join("") +
        `</tbody></table></div><p class="note">From ${esc(A.name)}'s side.</p>` : `<p class="empty">They did not meet in this season's data.</p>`) +
      `<p><a href="#team-${key}-${a}">${esc(A.name)} report</a> &middot; <a href="#team-${key}-${b}">${esc(B.name)} report</a>${back ? ` &middot; <a href="#vs-${key}-${b}-${a}">${esc(B.name)} attacking ${esc(A.name)}</a>` : ""}</p></section>` +
      footer() + `</div>`;
    const go = () => { const x = document.getElementById("ta").value, y = document.getElementById("tb").value; if (x !== y) location.hash = `#vs-${key}-${x}-${y}`; };
    document.getElementById("ta").addEventListener("change", go);
    document.getElementById("tb").addEventListener("change", go);
  }

  async function viewMethod() {
    let v = VALIDATION_FALLBACK;
    if (!window.PG_DATA) { try { const r = await fetch("validation.json"); if (r.ok) v = await r.json(); } catch (e) { /* use fallback */ } }
    const row = (cells) => `<tr>${cells.map((c, i) => `<td${i ? ' class="n"' : ""}>${c}</td>`).join("")}</tr>`;
    const ci = (lo, hi) => `${lo >= 0 ? "+" : ""}${lo.toFixed(4)} to ${hi >= 0 ? "+" : ""}${hi.toFixed(4)}`;
    app.innerHTML = nav("method") + `<div class="wrap"><header class="page"><div class="eyebrow">Method</div><h1>What this is, and how far to trust it</h1>` +
      `<p>Every team is a <b>flow graph</b>: pitch regions are nodes, and from each one a team moves the ball along an edge, shoots, or loses it. Solving that absorbing Markov chain gives the chance a possession ends in a goal. Each team's graph is pulled toward its league's in proportion to how little data supports it.</p></header>` +
      `<section><h2>Style is real</h2><p>A team's flow graph from half its matches should pick out its own other half among every team in the league.</p>` +
      `<div class="scroll"><table><thead><tr><th>League</th><th class="n">Identified</th><th class="n">Chance</th></tr></thead><tbody>${v.reid.map((r) => row([esc(r[0]), pct(r[1]), pct(r[2])])).join("")}</tbody></table></div></section>` +
      `<section><h2>Matchups change where, not how much</h2><p>Predicting each real match from the other matches only. Positive means the matchup model beat the comparison (90% intervals over matches).</p>` +
      `<div class="two"><div><h3>Where they attack (lanes) vs own habits</h3><div class="scroll"><table><tbody>${v.lanes.map((r) => row([esc(r[0]), ci(r[1], r[2])])).join("")}</tbody></table></div></div>` +
      `<div><h3>How much threat vs strength alone</h3><div class="scroll"><table><tbody>${v.volume.map((r) => row([esc(r[0]), ci(r[1], r[2])])).join("")}</tbody></table></div></div></div>` +
      `<p class="note">So the matchup view shows expected lanes from the matchup model and expected volume from strength alone.</p></section>` +
      `<section><h2>Player effects are weak</h2><p>Across ${v.missed.n} real absences, the predicted drop from removing a player agrees with what happened only weakly (r = ${v.missed.r.toFixed(2)}, p = ${v.missed.p.toFixed(3)}). Player levers show who the threat runs through; they are not forecasts.</p></section>` +
      `<section><p class="note">Results: ${esc(v.scope)}.</p></section>${footer()}</div>`;
  }

  async function route() {
    const h = location.hash.replace(/^#/, "") || (window.PG_START || "").replace(/^#/, "") || "find";
    const p = h.split("-");
    window.scrollTo(0, 0);
    try {
      if (p[0] === "team" && p.length === 3) return await viewTeam(p[1], p[2]);
      if (p[0] === "vs" && p.length === 4) return await viewMatchup(p[1], p[2], p[3]);
      if (h === "map") return await viewMap();
      if (h === "method") return await viewMethod();
      return await viewFind();
    } catch (err) {
      app.innerHTML = nav("") + `<div class="wrap"><header class="page"><h1>Not found</h1><p>${esc(err.message)}</p><p><a href="#find">Back to the library</a></p></header></div>`;
    }
  }

  window.addEventListener("hashchange", route);
  route();
})();
