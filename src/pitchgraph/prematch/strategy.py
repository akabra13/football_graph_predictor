"""Strategy lines: instructions that each rest on one checkable pre-match call.

See docs/strategy.md for the rules and the test of their premises.
"""
from __future__ import annotations

THRESHOLD = 0.5      # standard deviations from the league mean for a line to fire
MAX_LINES = 4

# id, whose feature ("we"/"they"), feature, direction, instruction template
RULES = [
    ("without_ball", "we", "possession", -1,
     "Expect to be without the ball: {p} of it (league {l}). Stay compact and plan to break; "
     "do not chase possession."),
    ("with_ball", "we", "possession", +1,
     "You will have the ball: {p} of it (league {l}). The job is opening a set defence; keep it moving "
     "and commit numbers forward."),
    ("press_high", "they", "own_third_turnover_share", +1,
     "Press high. {opp} are called to lose {p} of their giveaways in their own third (league {l}). "
     "Targets: {their_giveaways}. Lead the press with {our_pressers}."),
    ("hold_block", "they", "own_third_turnover_share", -1,
     "Do not chase high. {opp} rarely lose it deep ({p} of giveaways, league {l}). Hold a mid block and "
     "wait for the pass into midfield."),
    ("beat_press", "we", "own_third_turnover_share", +1,
     "They will press you: {p} of your giveaways are called in your own third (league {l}). Play out "
     "early or go longer; no risks in the first phase."),
    ("protect_centre", "they", "central_entries_per_possession", +1,
     "Protect the centre. {opp} are called to reach the central final third {p} times per possession "
     "(league {l}). Stop the half-space pass from {their_passers} to {their_receivers}; "
     "{our_defenders} hold that zone."),
    ("long_balls", "they", "long_forward_share", +1,
     "Expect it long and early: {p} of their moves (league {l}). Win the first ball and set for the "
     "second; {our_defenders} are the ones under it."),
    ("centre_open", "we", "central_entries_per_possession", +1,
     "The centre is open for you: {p} entries per possession called (league {l}). Get {our_carriers} "
     "on the ball facing forward."),
    ("centre_shut", "we", "central_entries_per_possession", -1,
     "Central access will be scarce ({p} per possession, league {l}). Do not force it; work the ball "
     "wide and value set pieces."),
    ("high_regain", "they", "start_height", +1,
     "They win the ball high (their possessions start at {p}, league {l}). Your first pass after a "
     "regain must clear their counter-press."),
    ("patterned", "they", "entropy_rate", -1,
     "They are patterned: their next move is easier to read than most ({p} bits, league {l}). Their "
     "routes repeat, so sit on them."),
]


def departure(call: dict, direction: int) -> float | None:
    """How many league standard deviations the call sits from the league mean, in the rule's direction."""
    sd = call.get("league_sd")
    if not sd or sd <= 0:
        return None
    return direction * (call["predicted"] - call["league"]) / sd


def _names(rows: list[dict]) -> str:
    return ", ".join(str(r["name"]) for r in rows) or "no one identified yet"


def lines(calls: dict, players: dict, opponent: str, formats: dict) -> list[dict]:
    """The strategy lines that fire for one game, strongest departure first."""
    out = []
    for rule, who, feature, direction, template in RULES:
        call = calls.get(who, {}).get(feature)
        if call is None:
            continue
        dep = departure(call, direction)
        if dep is None or dep < THRESHOLD:
            continue
        fmt = formats[feature]
        text = template.format(p=fmt.format(call["predicted"]), l=fmt.format(call["league"]), opp=opponent,
                               **{k: _names(v) for k, v in players.items()})
        held = None
        if call.get("actual") is not None:
            held = bool(direction * (call["actual"] - call["league"]) > 0)
        out.append({"rule": rule, "who": who, "feature": feature, "direction": direction,
                    "departure": float(dep), "text": text, "premise_held": held})
    out.sort(key=lambda r: -r["departure"])
    return out[:MAX_LINES]
