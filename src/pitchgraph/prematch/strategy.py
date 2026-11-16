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

# Set-piece rules: same form, tested separately (docs/set_pieces.md).
SP_RULES = [
    ("defend_corners", "they", "corners", +1,
     "Expect a lot of corners to defend: {p} called for {opp} (league {l}). Deliveries come from "
     "{their_takers}; their set-piece shots come from {their_shooters}."),
    ("win_corners", "we", "corners", +1,
     "You should win corners today: {p} called (league {l}). Have the routines ready: {our_takers} "
     "deliver, {our_shooters} attack them."),
    ("defend_set_pieces", "they", "sp_shots", +1,
     "{opp} are called to get {p} shots from set pieces (league {l}). No cheap fouls or corners in your "
     "own half; pick up {their_shooters}."),
    ("attack_set_pieces", "we", "sp_shots", +1,
     "Set pieces are a route to goal today: {p} shots from them called (league {l}). Get {our_takers} "
     "on the dead balls and {our_shooters} into the box."),
]


# Rules about THIS game: the call against a normal week for the team (docs/strategy.md,
# "instructions about this game"). {p} = the call, {u} = the reference.
GAME_THRESHOLD = 0.4
GAME_RULES = [
    ("less_ball", "we", "possession", -1,
     "Less of the ball than you are used to: {p} against your usual {u}. {opp} take it off teams; "
     "be ready to defend longer spells and to break when you win it."),
    ("more_ball", "we", "possession", +1,
     "More of the ball than you are used to: {p} against your usual {u}. {opp} give it up; you will "
     "have to break down a set defence."),
    ("pressed_deep", "we", "own_third_turnover_share", +1,
     "{opp} force mistakes deep: {p} of your giveaways are called in your own third (your usual {u}). "
     "Keep the first phase simple or go over them."),
    ("sloppier", "we", "turnover_rate", +1,
     "Expect to give the ball away more than usual ({p} of actions, your usual {u}). {opp} disrupt; "
     "protect against the turnover before you play the risky pass."),
    ("centre_tighter", "we", "central_entries_per_possession", -1,
     "The centre will be tighter than you are used to ({p} entries per possession, your usual {u}). "
     "Do not force it; go round."),
    ("centre_looser", "we", "central_entries_per_possession", +1,
     "{opp} leave the centre more open than most ({p} entries per possession, your usual {u}). "
     "Get {our_carriers} on the ball facing forward."),
    ("fewer_shots", "we", "shots_per_possession", -1,
     "Chances will be scarcer than usual ({p} shots per possession, your usual {u}). Value each one "
     "and your set pieces."),
    ("more_shots", "we", "shots_per_possession", +1,
     "{opp} give up shots: {p} per possession called, against your usual {u}. Shoot when it is on."),
    ("forced_long", "we", "long_forward_share", +1,
     "You will be pushed longer than usual ({p} of moves, your usual {u}). Decide who contests the "
     "first ball and who collects the second."),
    ("pinned_back", "we", "start_height", -1,
     "Your possessions will start deeper than usual ({p}, your usual {u}). Plan the way out before "
     "you win it."),
    ("win_more_corners", "we", "corners", +1,
     "More corners than usual: {p} called against your usual {u}. {our_takers} deliver, "
     "{our_shooters} attack them."),
    ("press_them", "they", "own_third_turnover_share", +1,
     "Press high. {opp} lose it deep more than the sides you usually face ({p} of their giveaways in "
     "their own third, your opponents' usual {u}). Targets: {their_giveaways}. Lead with {our_pressers}."),
    ("leave_them", "they", "own_third_turnover_share", -1,
     "Do not chase high. {opp} are safer at the back than the sides you usually face ({p} of giveaways "
     "in their own third, usual {u}). Hold your shape and wait."),
    ("they_go_long", "they", "long_forward_share", +1,
     "{opp} go long more than the sides you usually face ({p} of moves, usual {u}). Win the first "
     "ball and set for the second; {our_defenders} are the ones under it."),
    ("they_come_central", "they", "central_entries_per_possession", +1,
     "{opp} get into the central final third more than the sides you usually face ({p} per "
     "possession, usual {u}). Stop the half-space pass from {their_passers} to {their_receivers}; "
     "{our_defenders} hold that zone."),
    ("they_regain_high", "they", "start_height", +1,
     "{opp} win the ball higher than the sides you usually face (their possessions start at {p}, "
     "usual {u}). Your first pass after a regain must clear their counter-press."),
    ("they_are_readable", "they", "entropy_rate", -1,
     "{opp} are easier to read than the sides you usually face ({p} bits a move, usual {u}). Their "
     "routes repeat; sit on them."),
    ("more_corners_against", "they", "corners", +1,
     "More corners to defend than usual: {p} called for {opp}, against {u} for your usual opponent. "
     "Deliveries from {their_takers}; their set-piece shots come from {their_shooters}."),
]


def reference_value(call: dict, who: str, reference: str) -> float:
    """What the call is compared with: the league mean, or a normal week for the team
    (its own usual for its own numbers; what opponents usually do against it for theirs)."""
    if reference == "usual":
        return call["own"] if who == "we" else call["predicted"] - call["own"] + call["league"]
    return call["league"]


def departure(call: dict, direction: int, who: str = "we", reference: str = "league") -> float | None:
    """How many league standard deviations the call sits from its reference, in the rule's direction."""
    sd = call.get("league_sd")
    if not sd or sd <= 0:
        return None
    return direction * (call["predicted"] - reference_value(call, who, reference)) / sd


def _names(rows: list[dict]) -> str:
    return ", ".join(str(r["name"]) for r in rows) or "no one identified yet"


def lines(calls: dict, players: dict, opponent: str, formats: dict, rules=None, reference: str = "league",
          threshold: float | None = None) -> list[dict]:
    """The strategy lines that fire for one game, strongest departure first."""
    out = []
    for rule, who, feature, direction, template in (RULES if rules is None else rules):
        call = calls.get(who, {}).get(feature)
        if call is None:
            continue
        dep = departure(call, direction, who, reference)
        if dep is None or dep < (THRESHOLD if threshold is None else threshold):
            continue
        ref = reference_value(call, who, reference)
        fmt = formats[feature]
        text = template.format(p=fmt.format(call["predicted"]), l=fmt.format(call["league"]), u=fmt.format(ref), opp=opponent,
                               **{k: _names(v) for k, v in players.items()})
        held = None
        if call.get("actual") is not None:
            held = bool(direction * (call["actual"] - ref) > 0)
        out.append({"rule": rule, "who": who, "feature": feature, "direction": direction,
                    "departure": float(dep), "text": text, "premise_held": held})
    out.sort(key=lambda r: -r["departure"])
    return out[:MAX_LINES]
