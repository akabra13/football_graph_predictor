"""Render an opposition report to one self-contained HTML page.

Visual language: a tactics board. Blue magnets are the scouted team with the
ball; red magnets are threat against them. The page is written without
<html>/<body> wrappers so it can be published as-is or opened from Drive.
"""

from __future__ import annotations

from html import escape

from pitchgraph.report.pitch import network_svg, routes_svg

SECTIONS = [
    ("buildup", "How they build up", "own"),
    ("pressing", "How they press", "own"),
    ("vulnerability", "Where they are vulnerable", "opp"),
]
TAGS = {"buildup": "attack", "pressing": "press", "vulnerability": "defence"}

CSS = """
:root{
  --paper:#F3F5F2; --surface:#FFFFFF; --ink:#16201B; --muted:#5B6A62; --hair:#D5DDD7;
  --blue:#2F5DA8; --blue-soft:#DCE5F4; --red:#C2412D; --red-soft:#F5DFDA;
  --turf:#E6ECE7; --turf-line:#AFBDB4;
  --display:"Barlow Condensed","Arial Narrow",Arial,sans-serif;
  --body:"Source Sans 3","Segoe UI",system-ui,sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  --paper:#0F1512; --surface:#161E1A; --ink:#E4EBE6; --muted:#9AA8A0; --hair:#2A3530;
  --blue:#86A8E8; --blue-soft:#1D2A40; --red:#EE8069; --red-soft:#3A221D;
  --turf:#18221D; --turf-line:#3C4B43; color-scheme:dark; } }
:root[data-theme="dark"]{
  --paper:#0F1512; --surface:#161E1A; --ink:#E4EBE6; --muted:#9AA8A0; --hair:#2A3530;
  --blue:#86A8E8; --blue-soft:#1D2A40; --red:#EE8069; --red-soft:#3A221D;
  --turf:#18221D; --turf-line:#3C4B43; color-scheme:dark; }
body{background:var(--paper);color:var(--ink);font:16px/1.55 var(--body);}
.wrap{max-width:880px;margin:0 auto;padding-inline:20px;padding-block:32px 56px;display:grid;gap:40px;}
h1,h2,h3{font-family:var(--display);font-weight:600;line-height:1.05;text-wrap:balance;margin:0;}
h1{font-size:clamp(2.6rem,7vw,4.2rem);letter-spacing:.01em;}
h2{font-size:2rem;letter-spacing:.01em;}
h3{font-size:1.25rem;letter-spacing:.02em;}
p{margin:0;max-width:66ch;}
.eyebrow{font:500 .78rem/1.3 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted);}
header{display:grid;gap:14px;border-bottom:2px solid var(--ink);padding-bottom:22px;}
.meta{display:flex;flex-wrap:wrap;gap:8px 22px;font:500 .85rem/1.4 var(--mono);color:var(--muted);}
.meta b{color:var(--ink);font-weight:500;}
.summary{display:grid;gap:12px;}
.summary ol{margin:0;padding-left:1.3em;display:grid;gap:10px;max-width:70ch;}
.summary li::marker{font-family:var(--mono);color:var(--muted);}
.tag{font:500 .7rem/1 var(--mono);letter-spacing:.06em;text-transform:uppercase;padding:3px 6px;border-radius:3px;margin-left:6px;white-space:nowrap;vertical-align:1px;}
.tag.own{background:var(--blue-soft);color:var(--blue);} .tag.opp{background:var(--red-soft);color:var(--red);}
section{display:grid;gap:20px;}
.section-head{display:grid;gap:6px;border-top:1px solid var(--hair);padding-top:20px;}
.claims{display:grid;gap:0;border-top:1px solid var(--hair);}
.claim{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:6px 20px;padding:14px 0;border-bottom:1px solid var(--hair);align-items:center;}
.claim .label{font-weight:600;}
.claim .val{font:500 1.3rem/1 var(--mono);font-variant-numeric:tabular-nums;text-align:right;}
.claim .sub{grid-column:1/-1;display:flex;flex-wrap:wrap;align-items:center;gap:8px 16px;font-size:.88rem;color:var(--muted);}
.ladder{display:flex;gap:2px;align-items:center;}
.ladder span{width:9px;height:14px;border-radius:1px;background:var(--hair);}
.ladder span.mid{box-shadow:inset 0 -3px 0 var(--muted);}
.ladder span.on{background:var(--blue);} .opp .ladder span.on{background:var(--red);}
.ladder small{font:500 .7rem var(--mono);color:var(--muted);padding-inline:4px;}
.conf{font:500 .72rem/1 var(--mono);letter-spacing:.05em;text-transform:uppercase;padding:4px 7px;border-radius:3px;}
.conf.High{background:var(--ink);color:var(--paper);}
.conf.Medium{border:1px solid var(--ink);color:var(--ink);}
.conf.Low{border:1px dashed var(--muted);color:var(--muted);}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums;}
.figs{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:24px;}
figure{margin:0;display:grid;gap:8px;}
figcaption{font-size:.88rem;color:var(--muted);}
.scroll{overflow-x:auto;}
svg.pitch{width:100%;min-width:320px;height:auto;display:block;}
svg .turf{fill:var(--turf);} svg .line{fill:none;stroke:var(--turf-line);stroke-width:.35;}
svg .goal{fill:var(--turf-line);} svg .lane{stroke:var(--turf-line);stroke-width:.25;stroke-dasharray:1 1.4;}
svg .third{stroke:var(--turf-line);stroke-width:.3;stroke-dasharray:2 1.5;}
svg .dir{font:2.6px var(--mono);fill:var(--muted);}
svg .route{fill:none;stroke:var(--blue);stroke-linecap:round;opacity:.85;}
svg .route-head{fill:var(--blue);} svg .route-dot{fill:var(--blue);}
svg .lbl{font:600 3.2px var(--mono);fill:var(--ink);}
svg .edge{stroke-linecap:round;opacity:.55;} svg .edge.own{stroke:var(--blue);} svg .edge.opp{stroke:var(--red);}
svg .node{stroke:var(--surface);stroke-width:.5;} svg .node.own{fill:var(--blue);} svg .node.opp{fill:var(--red);}
svg .name{font:600 2.7px var(--body);fill:var(--ink);}
table{border-collapse:collapse;width:100%;font-size:.95rem;}
th,td{text-align:left;padding:8px 10px 8px 0;border-bottom:1px solid var(--hair);}
th{font:500 .72rem var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);}
td.n,th.n{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums;}
.bars{display:grid;gap:10px;}
.bar{display:grid;grid-template-columns:9.5rem minmax(0,1fr) 3.5rem;gap:12px;align-items:center;font-size:.92rem;}
.track{position:relative;height:12px;background:var(--hair);border-radius:2px;}
.fill{position:absolute;inset:0 auto 0 0;border-radius:2px;background:var(--red);}
.fill.own{background:var(--blue);}
.tick{position:absolute;top:-4px;bottom:-4px;width:2px;background:var(--ink);}
.states{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;background:var(--hair);border:1px solid var(--hair);}
.states div{background:var(--surface);padding:12px 14px;display:grid;gap:4px;}
.states b{font:500 1.35rem var(--mono);font-variant-numeric:tabular-nums;}
.states span{font-size:.85rem;color:var(--muted);}
.note{font-size:.88rem;color:var(--muted);}
footer{border-top:2px solid var(--ink);padding-top:18px;display:grid;gap:10px;font-size:.88rem;color:var(--muted);}
@media (max-width:520px){ .bar{grid-template-columns:7rem minmax(0,1fr) 3rem;} .ladder span{width:6px;} }
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600'
         '&family=IBM+Plex+Mono:wght@400;500&family=Source+Sans+3:wght@400;600&display=swap">')


def _pct(v: float) -> str:
    return f"{v:.0%}"


def _ladder(rank: int, of: int) -> str:
    # Left = lowest value in the league, right = highest.
    pos = of - rank
    cells = "".join(
        f'<span class="{"on" if i == pos else ""}{" mid" if i == of // 2 else ""}"></span>'
        for i in range(of))
    return f'<span class="ladder" aria-label="rank {rank} of {of}"><small>low</small>{cells}<small>high</small></span>'


def _claim(c) -> str:
    e, s = c.est, c.stat
    rng = (f"90% range {s.fmt.format(e.lo)} to {s.fmt.format(e.hi)}"
           if e.lo == e.lo else "range unavailable")
    return (f'<div class="claim"><div class="label">{escape(s.label)}</div>'
            f'<div class="val">{escape(s.fmt.format(e.value))}</div>'
            f'<div class="sub">{_ladder(c.rank, c.of)}'
            f'<span>league median <span class="mono">{escape(s.fmt.format(e.league))}</span></span>'
            f'<span class="mono">{escape(rng)}</span>'
            f'<span class="conf {e.confidence}">{e.confidence}</span></div></div>')


def _bars(rows: list[dict], label_key: str, kind: str) -> str:
    top = max(max(r["share"], r["league"]) for r in rows) or 1
    out = []
    for r in rows:
        out.append(f'<div class="bar"><span>{escape(r[label_key])}</span>'
                   f'<span class="track"><span class="fill {kind}" style="width:{100 * r["share"] / top:.1f}%"></span>'
                   f'<span class="tick" style="left:{100 * r["league"] / top:.1f}%" title="league"></span></span>'
                   f'<span class="mono">{_pct(r["share"])}</span></div>')
    return '<div class="bars">' + "".join(out) + "</div>"


def render(rep: dict) -> str:
    m, d = rep["meta"], rep["details"]
    claims = rep["claims"]
    kind_of = {k: kind for k, _, kind in SECTIONS}

    summary = "".join(
        f'<li>{escape(c.sentence)}<span class="tag {kind_of[c.stat.section]}">'
        f'{TAGS[c.stat.section]}</span></li>'
        for c in rep["headlines"])

    body = []
    for key, title, kind in SECTIONS:
        rows = "".join(_claim(c) for c in claims if c.stat.section == key)
        extra = ""
        if key == "buildup":
            extra = (
                '<div class="figs">'
                f'<figure><div class="scroll">{routes_svg(d["routes"])}</div>'
                '<figcaption>Their five most common routes. Each arrow joins the lane where the ball '
                'crossed into the middle third (x=40) to the lane where it crossed into the final third '
                '(x=80); thickness and label show the share of full progressions.</figcaption></figure>'
                f'<figure><div class="scroll">{network_svg(d["players"], d["links"], "involvement", "Who the threat flows through")}</div>'
                '<figcaption>Who the threat flows through. Circle size is each player\'s share of the value '
                'the team adds; lines are their most valuable passing links. Positions are median on-ball '
                'locations.</figcaption></figure></div>'
                + _players_table(d["players"]))
        elif key == "pressing":
            pressed = [{**r, "label": r["position"]} for r in d["pressed"]]
            extra = (
                '<div class="figs">'
                f'<figure><div class="scroll">{network_svg(d["press_nodes"], d["copress"], "n", "Co-pressing units", link_key="n")}</div>'
                '<figcaption>Who presses together. Circle size is pressures made; a line joins two players '
                'when one pressed within two seconds of the other in the same opponent possession.</figcaption></figure>'
                '<figure><h3>Who they press first</h3>'
                f'{_bars(pressed, "label", "own")}'
                '<figcaption>Position of the opponent on the ball when their press starts: the five '
                'they press most (tick = league share). Press starts that could not be matched to an '
                'opponent on the ball are left out.</figcaption></figure></div>')
        else:
            lanes = [{**r, "label": r["side"]} for r in d["conceded_lanes"]]
            s = d["states"]
            adj = d["opp_adjusted"]
            adj_text = ("Opponents made {:+.2f} threat per match against them compared with their own "
                        "average in other matches ({} matches). Negative means they hold teams below "
                        "their usual level.").format(adj, d["opp_adjusted_n"]) if adj == adj else ""
            extra = (
                '<div class="figs">'
                '<figure><h3>Where opponents get into the final third</h3>'
                f'{_bars(lanes, "label", "opp")}'
                '<figcaption>Share of opponents\' final-third entries by lane, named from this team\'s '
                'side of the pitch (tick = league share).</figcaption></figure>'
                '<figure><h3>Threat conceded per opponent possession</h3><div class="states">'
                + "".join(f'<div><span>when {st}</span><b>{s.get(st, float("nan")):.3f}</b>'
                          f'<span>league {d["league_states"].get(st, float("nan")):.3f}</span></div>'
                          for st in ("leading", "level", "trailing"))
                + f'</div><p class="note">{escape(adj_text)}</p></figure></div>'
                + _moments(d))
        body.append(f'<section class="{kind}"><div class="section-head"><h2>{escape(title)}</h2></div>'
                    f'<div class="claims">{rows}</div>{extra}</section>')

    return (f"<title>{escape(m['team'])} Scouting Report</title>{FONTS}<style>{CSS}</style>"
            '<div class="wrap"><header>'
            f'<div class="eyebrow">Opposition report &middot; {escape(m["competition"])} {escape(m["season"])}</div>'
            f'<h1>{escape(m["team"])}</h1>'
            f'<div class="meta"><span><b>{m["matches"]}</b> matches</span>'
            f'<span>compared with <b>{m["teams"]}</b> league teams</span>'
            f'<span>data: <b>{escape(m["tier"])}</b></span>'
            f'<span>claims stable across halves of the season: <b>{m["agreement"]:.0%}</b></span></div>'
            '</header>'
            '<section class="summary"><h2>In short</h2>'
            '<p class="note">The strongest findings: high confidence, and furthest from the league middle.</p>'
            f'<ol>{summary}</ol></section>'
            + "".join(body) + _footer(m) + "</div>")


def _players_table(players: list[dict]) -> str:
    rows = "".join(
        f'<tr><td>{escape(p["full"])}</td><td class="n">{_pct(p["involvement"])}</td>'
        f'<td class="n">{_pct(p["created"])}</td><td class="n">{_pct(p["dependency"])}</td></tr>'
        for p in players[:8])
    return ('<div class="scroll"><table><thead><tr><th>Player</th><th class="n">Involved in threat</th>'
            '<th class="n">Created</th><th class="n">In final-third entries</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>'
            '<p class="note">Involved counts a pass for both passer and receiver, so shares can add up to '
            'more than 100%. "In final-third entries" is the share of their final-third entries the player '
            'touched on the way: how much the team leans on them, not what would happen without them.</p>')


def _moments(d: dict) -> str:
    if not d["moments"]:
        return ""
    rows = "".join(
        f'<tr><td>{escape(r["match"])}</td><td class="n">{r["minute"]}\'</td>'
        f'<td>{escape(r["by"])}</td><td class="n">{r["xg"]:.2f}</td></tr>'
        for r in d["moments"])
    return (f'<figure><h3>Moments to watch: down their {escape(d["worst_lane"]["side"])}</h3>'
            '<div class="scroll"><table><thead><tr><th>Match</th><th class="n">Minute</th>'
            '<th>Entry by</th><th class="n">xG that followed</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>'
            '<figcaption>The most dangerous opponent attacks through the lane where they are hit more '
            'than the league average. Find these in the match video.</figcaption></figure>')


def _footer(m: dict) -> str:
    return ('<footer>'
            '<p><b>How to read this.</b> Every figure is compared with all teams in the same competition '
            'and season. Ranges come from resampling whole matches; confidence is High when the range '
            'excludes the league median and both halves of the season agree, Medium when one of those '
            'holds, and Low when neither does. Threat is the change in the chance of the possession '
            'producing a goal, from an absorbing Markov model of possession over pitch zones.</p>'
            f'<p>Data: StatsBomb Open Data. Generated by PitchGraph ({escape(m["model"])}).</p>'
            '</footer>')
