"""Render a season replay as one self-contained HTML page."""
from __future__ import annotations

from html import escape

from pitchgraph.prematch.replay import LANE_LABELS, mirror_lane

CSS = """
body{font-family:system-ui,Segoe UI,Arial,sans-serif;background:#F6F3EE;color:#1D1D1F;margin:0;padding:24px 16px}
main{max-width:980px;margin:0 auto}
h1{font-size:30px;margin:0 0 6px} h2{font-size:20px;margin:28px 0 10px} h3{font-size:15px;margin:14px 0 6px}
p{line-height:1.5;margin:6px 0} .muted{color:#8A8580} .small{font-size:13px}
.card{background:#fff;border:1px solid #E2DDD5;border-radius:10px;padding:16px 18px;margin:14px 0}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:18px} @media(max-width:760px){.cols{grid-template-columns:1fr}}
table{border-collapse:collapse;width:100%;font-size:13.5px} th,td{text-align:right;padding:5px 8px;border-bottom:1px solid #EEE9E1}
th:first-child,td:first-child{text-align:left} th{color:#8A8580;font-weight:600}
.tag{display:inline-block;border-radius:999px;padding:2px 10px;font-size:12px;font-weight:600}
.hit{background:#E3F1E7;color:#1E6B3A} .miss{background:#F7E3E6;color:#A12B3C} .info{background:#E6EEF3;color:#24607D}
.lanes{display:grid;grid-template-columns:repeat(5,1fr);gap:4px;margin:4px 0 2px}
.lane{border-radius:4px;padding:6px 2px;text-align:center;font-size:12px}
.score{font-size:22px;font-weight:700} .top{font-weight:700}
"""


def _pct(v, signed=False):
    if v is None:
        return "n/a"
    return f"{v:+.0%}" if signed else f"{v:.0%}"


def _lanes(shares, mirror=False):
    order = [mirror_lane(i) for i in range(5)] if mirror else list(range(5))
    top = max(range(5), key=lambda i: shares[i])
    cells = []
    for i in order:
        a = min(0.85, shares[i] * 2.2)
        cells.append(f'<div class="lane{" top" if i == top else ""}" style="background:rgba(46,134,171,{a:.2f})">'
                     f'{_pct(shares[i])}</div>')
    return '<div class="lanes">' + "".join(cells) + "</div>"


def _names(rows):
    return ", ".join(f"{escape(str(r['name']))} ({_pct(r['share'])})" for r in rows) or "no data yet"


def _tag(ok, yes="called it", no="missed"):
    return f'<span class="tag {"hit" if ok else "miss"}">{yes if ok else no}</span>'


def _game(g, team):
    opp = escape(g["opponent"])
    head = (f'<div class="card"><div class="muted small">{g["date"]} · {"home" if g["home"] else "away"}</div>'
            f'<h2 style="margin:2px 0 8px">{escape(team)} v {opp} '
            f'<span class="score">{g["score"][0]}–{g["score"][1]}</span></h2>')
    p = g.get("plan")
    if p is None:
        return head + '<p class="muted">Too few earlier matches for a plan.</p></div>'
    side = p["lever_side"]
    lv = p["lever"][side]
    they, we = p["they_attack"], p["we_attack"]
    their_top = max(range(5), key=lambda i: they["matchup"][i])
    our_side = LANE_LABELS[mirror_lane(their_top)]
    pre = (
        '<div class="cols"><div>'
        f'<h3>Before the match: where {opp} will come from</h3>'
        f'<p class="small muted">Share of their entries into the final third, shown from our side '
        f'(our left flank on the left).</p>{_lanes(they["matchup"], mirror=True)}'
        f'<p>Expect most through <b>our {our_side}</b> ({_pct(they["matchup"][their_top])}; '
        f'the league sends {_pct(they["league"][their_top])} there).</p>'
        f'<h3>The pass to stop</h3>'
        f'<p>Half-space into the centre of the final third. {opp} play it more on their <b>{side}</b> '
        f'({lv["share"]:.1%} of their moves), mostly from {_names(p["players"]["their_passers"])} '
        f'to {_names(p["players"]["their_receivers"])}.</p>'
        f'<p>Our players who have defended that zone: <b>{_names(p["players"]["our_defenders"])}</b>.</p>'
        '</div><div>'
        f'<h3>Before the match: where we should go</h3>'
        f'<p class="small muted">Share of our entries expected against {opp}.</p>{_lanes(we["matchup"])}'
        f'<p>This opponent pulls our attack toward the <b>{LANE_LABELS[p["lane_we"]]}</b> '
        f'({_pct(we["matchup"][p["lane_we"]])} against our usual {_pct(we["own"][p["lane_we"]])}).</p>'
        f'<p>Our players who take the ball in there: <b>{_names(p["players"]["our_carriers"])}</b>.</p>'
        f'<p class="small muted">Plan built from {p["prior_matches"]["us"]} of our earlier matches and '
        f'{p["prior_matches"]["them"]} of theirs.</p></div></div>')
    o = g.get("outcome")
    if not o:
        return head + pre + "</div>"
    post = (
        '<h3 style="margin-top:16px">What happened</h3><div class="cols"><div>'
        f'<p class="small muted">Their real entries (from our side).</p>{_lanes(o["they"]["actual"], mirror=True)}'
        f'<p>{_tag(o["they"]["top_hit"]["matchup"])} busiest lane. Distance from the real shares: plan '
        f'{o["they"]["tv"]["matchup"]:.2f}, their own habits {o["they"]["tv"]["own"]:.2f}, '
        f'league {o["they"]["tv"]["league"]:.2f} (lower is better).</p>'
        f'<p>They got <b>{_pct(o["lever"]["vs_usual"], True)}</b> of that pass against their usual, and their '
        f'threat was <b>{_pct(o["their_threat"]["vs_expected"], True)}</b> against what strength alone '
        f'predicted ({o["their_threat"]["xg"]:.2f} xG from open play).</p>'
        '</div><div>'
        f'<p class="small muted">Our real entries.</p>{_lanes(o["we"]["actual"])}'
        f'<p>{_tag(o["we"]["top_hit"]["matchup"])} busiest lane. Distance: plan {o["we"]["tv"]["matchup"]:.2f}, '
        f'our own habits {o["we"]["tv"]["own"]:.2f}, league {o["we"]["tv"]["league"]:.2f}.</p></div></div>')
    return head + pre + post + "</div>"


def _summary(s):
    def row(label, d, n):
        return (f"<tr><td>{label}</td>" + "".join(
            f'<td>{d[m]["top_lane_hits"]}/{n}</td><td>{d[m]["mean_tv"]:.3f}</td>'
            for m in ("matchup", "own", "league")) + f'<td>{d["matchup_beats_own"]}/{n}</td></tr>')
    n = s["games"]
    extra = ""
    if "lever_vs_threat_r" in s:
        extra = (f'<p>When the opponent got <b>less</b> of the half-space-to-centre pass than usual, their threat '
                 f'averaged <b>{_pct(s["threat_when_lever_low"], True)}</b> against expectation; when they got '
                 f'more, <b>{_pct(s["threat_when_lever_high"], True)}</b> (correlation {s["lever_vs_threat_r"]:+.2f} '
                 f'over {n} games; small sample, descriptive only).</p>')
    return (
        '<div class="card"><h2 style="margin-top:0">Scorecard</h2><table><tr><th>Lane calls</th>'
        '<th>Plan: busiest lane</th><th>distance</th><th>Own habits: busiest</th><th>distance</th>'
        '<th>League: busiest</th><th>distance</th><th>Plan closer than own habits</th></tr>'
        + row("Where they attacked", s["they"], n) + row("Where we attacked", s["we"], n) + "</table>"
        '<p class="small muted">Distance = total variation between predicted and real lane shares, averaged '
        'over games; 0 is perfect.</p>' + extra + "</div>")


def render_html(rep: dict, team: str, competition: str, season: str) -> str:
    games = "".join(_game(g, team) for g in rep["games"])
    return (
        f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,'
        f'initial-scale=1"><title>{escape(team)} season replay</title><style>{CSS}</style></head><body><main>'
        f'<h1>{escape(team)}: the pre-match plan, game by game</h1>'
        f'<p class="muted">{escape(competition)} {escape(season)}, second half of the season. Every plan uses only '
        f'matches played before that game\'s date, then is scored against what happened.</p>'
        '<div class="card"><p><span class="tag info">What is tested</span> Lane predictions from the matchup model '
        'passed their test in four of five leagues. The half-space-to-centre pass is confirmed as the main lever '
        'across 5,456 team-matches (12 to 14% of threat).</p><p><span class="tag info">What is not</span> '
        'Whether one team depends on that pass more than another could not be resolved. A replay shows what the '
        'tool would have said; it cannot show what would have happened had the team acted on it.</p></div>'
        + _summary(rep["summary"]) + games +
        '<p class="small muted">Data: StatsBomb Open Data. '
        '<img alt="StatsBomb" height="22" style="vertical-align:middle" src="https://raw.githubusercontent.com/'
        'statsbomb/open-data/master/img/SB%20-%20Icon%20Lockup%20-%20Colour%20positive.png"></p>'
        '</main></body></html>')
