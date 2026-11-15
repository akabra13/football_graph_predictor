"""Render a season replay as one self-contained HTML page."""
from __future__ import annotations

from html import escape

from pitchgraph.prematch.replay import CALLS

CSS = """
body{font-family:system-ui,Segoe UI,Arial,sans-serif;background:#F6F3EE;color:#1D1D1F;margin:0;padding:24px 16px}
main{max-width:1000px;margin:0 auto}
h1{font-size:30px;margin:0 0 6px} h2{font-size:20px;margin:28px 0 10px} h3{font-size:15px;margin:16px 0 6px}
p{line-height:1.5;margin:6px 0} .muted{color:#8A8580} .small{font-size:13px}
.card{background:#fff;border:1px solid #E2DDD5;border-radius:10px;padding:16px 18px;margin:14px 0}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:18px} @media(max-width:760px){.cols{grid-template-columns:1fr}}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{text-align:right;padding:5px 8px;border-bottom:1px solid #EEE9E1;white-space:nowrap}
th:first-child,td:first-child{text-align:left;white-space:normal} th{color:#8A8580;font-weight:600}
.tag{display:inline-block;border-radius:999px;padding:2px 10px;font-size:12px;font-weight:600}
.info{background:#E6EEF3;color:#24607D}
.good{color:#1E6B3A;font-weight:700} .bad{color:#A12B3C}
.score{font-size:22px;font-weight:700}
"""


def _pct(v, signed=False):
    if v is None:
        return "n/a"
    return f"{v:+.0%}" if signed else f"{v:.0%}"


def _names(rows):
    return ", ".join(f"{escape(str(r['name']))} ({_pct(r['share'])})" for r in rows) or "no data yet"


def _cell(c, fmt):
    """predicted -> actual, green when the call was closer than the league average."""
    if c is None:
        return "<td>n/a</td>"
    if c["actual"] is None:
        return f"<td>{fmt.format(c['predicted'])}</td>"
    cls = "good" if c["closer_than_league"] else "bad"
    return f'<td>{fmt.format(c["predicted"])} → <span class="{cls}">{fmt.format(c["actual"])}</span></td>'


def _calls_table(calls, team, opp):
    rows = []
    for feature, label, fmt in CALLS:
        we, they = calls["we"].get(feature), calls["they"].get(feature)
        league = (we or they or {}).get("league")
        rows.append(f"<tr><td>{escape(label)}</td>{_cell(we, fmt)}{_cell(they, fmt)}"
                    f"<td>{fmt.format(league) if league is not None else 'n/a'}</td></tr>")
    return ('<div class="scroll"><table><tr><th>Called before the match → what happened</th>'
            f"<th>{escape(team)}</th><th>{escape(opp)}</th><th>League</th></tr>" + "".join(rows) + "</table></div>"
            '<p class="small muted">Green: the call was closer to what happened than the league average was. '
            "Red: it was not.</p>")


def _game(g, team):
    opp = escape(g["opponent"])
    head = (f'<div class="card"><div class="muted small">{g["date"]} · {"home" if g["home"] else "away"}</div>'
            f'<h2 style="margin:2px 0 8px">{escape(team)} v {opp} '
            f'<span class="score">{g["score"][0]}–{g["score"][1]}</span></h2>')
    p = g.get("plan")
    if p is None:
        return head + '<p class="muted">Too few earlier matches for a plan.</p></div>'
    pl_ = p["players"]
    side = p["lever_side"]
    body = _calls_table(g["calls"], team, g["opponent"]) if g.get("calls") else ""
    body += (
        '<div class="cols"><div>'
        "<h3>Their pass to stop</h3>"
        f'<p>Half-space into the centre of the final third, played more on their <b>{side}</b>: '
        f'{_names(pl_["their_passers"])} to {_names(pl_["their_receivers"])}.</p>'
        f'<p>Who has defended that zone for us: <b>{_names(pl_["our_defenders"])}</b>.</p>'
        "</div><div>"
        "<h3>Where to press</h3>"
        f'<p>Their players who give it away most in their own third: {_names(pl_["their_giveaways"])}.</p>'
        f'<p>Our players who press most in the final third: <b>{_names(pl_["our_pressers"])}</b>.</p>'
        "<h3>Our way in</h3>"
        f'<p>Who takes the ball into the final third for us: <b>{_names(pl_["our_carriers"])}</b>.</p>'
        "</div></div>"
        f'<p class="small muted">Built from {p["prior_matches"]["us"]} of our earlier matches and '
        f'{p["prior_matches"]["them"]} of theirs.</p>')
    o = g.get("outcome")
    if o:
        body += (f'<p class="small">In the match they got <b>{_pct(o["lever"]["vs_usual"], True)}</b> of that pass '
                 f'against their usual, and their open-play threat was '
                 f'<b>{_pct(o["their_threat"]["vs_expected"], True)}</b> against what strength alone predicted '
                 f'({o["their_threat"]["xg"]:.2f} xG).</p>')
    return head + body + "</div>"


def _summary(s, team):
    rows = []
    for feature, label, _ in CALLS:
        cells = ""
        for who in ("we", "they"):
            c = s["calls"][who].get(feature)
            if c is None or c["skill"] is None:
                cells += "<td>n/a</td><td>n/a</td>"
            else:
                cls = "good" if c["skill"] > 0 else "bad"
                cells += (f'<td>{c["closer_than_league"]}/{c["n"]}</td>'
                          f'<td class="{cls}">{c["skill"]:+.0%}</td>')
        rows.append(f"<tr><td>{escape(label)}</td>{cells}</tr>")
    extra = ""
    if "lever_vs_threat_r" in s:
        extra = (f'<p class="small">When opponents got less of their half-space-to-centre pass than usual, their '
                 f'threat averaged {_pct(s["threat_when_lever_low"], True)} against expectation; when they got more, '
                 f'{_pct(s["threat_when_lever_high"], True)} (correlation {s["lever_vs_threat_r"]:+.2f}; one link in '
                 f'one match is a handful of passes, so this is descriptive only).</p>')
    return (
        '<div class="card"><h2 style="margin-top:0">Scorecard</h2>'
        f'<p><b>{s["calls_closer"]} of {s["calls_total"]}</b> calls were closer to what happened than the league '
        f'average was, over {s["games"]} games.</p>'
        '<div class="scroll"><table><tr><th>Call</th>'
        f'<th>{escape(team)}: closer</th><th>skill</th><th>Opponents: closer</th><th>skill</th></tr>'
        + "".join(rows) + "</table></div>"
        '<p class="small muted">Skill = how much of the league average\'s squared error the call removed over these '
        "games (0% = no better than the league, 100% = perfect, negative = worse).</p>" + extra + "</div>")


def render_html(rep: dict, team: str, competition: str, season: str) -> str:
    games = "".join(_game(g, team) for g in rep["games"])
    return (
        f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,'
        f'initial-scale=1"><title>{escape(team)} season replay</title><style>{CSS}</style></head><body><main>'
        f'<h1>{escape(team)}: the pre-match plan, game by game</h1>'
        f'<p class="muted">{escape(competition)} {escape(season)}, second half of the season. Every plan uses only '
        f'matches played before that game\'s date, then is scored against what happened.</p>'
        '<div class="card"><p><span class="tag info">What is called</span> Nine things that an audit of 5,456 '
        'team-matches found knowable before kick-off, each predicted from the team\'s earlier matches and from what '
        'earlier opponents did against this opponent. Lane-by-lane entry calls were dropped: the audit found them '
        'the least knowable item tested.</p><p><span class="tag info">What is not claimed</span> A replay shows '
        'what the tool would have said. It cannot show what would have happened had the team acted on it. Player '
        'lists describe who has done the job so far, not who should.</p></div>'
        + _summary(rep["summary"], team) + games +
        '<p class="small muted">Data: StatsBomb Open Data. '
        '<img alt="StatsBomb" height="22" style="vertical-align:middle" src="https://raw.githubusercontent.com/'
        'statsbomb/open-data/master/img/SB%20-%20Icon%20Lockup%20-%20Colour%20positive.png"></p>'
        '</main></body></html>')
