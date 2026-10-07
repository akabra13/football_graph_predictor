"""Player flow graphs: the same absorbing chain, with players as the nodes.

From each player in possession the ball goes to a team-mate (a completed pass),
ends in a shot, or is lost. Carries keep the ball with the same player, so they
are not transitions. Players below a minimum number of actions are pooled into
an "others" node, so every row is estimated from enough data, and each row is
shrunk toward the team's average row.

Taking a player out of the graph answers "what if we stopped this player
getting the ball", with the same two bounds as the zone denial planner:
  no adaptation    passes meant for him are lost, and possessions that would
                   have started with him start with team-mates instead
  full adaptation  passers spread those passes over their other team-mates

The natural experiment `missed_matches` checks the prediction against what
actually happened when a player was absent.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from pitchgraph.value.markov import classify_actions, solve_values

OTHERS = -1
MIN_ACTIONS = 150
KAPPA_ROW = 20.0
KAPPA_XG = 5.0


@dataclass
class PlayerChain:
    players: list            # node order; OTHERS last
    P: np.ndarray            # (k, k + 2): pass to node, shoot, lose
    g: np.ndarray            # (k,) mean xG per shot
    start: np.ndarray        # (k,) who has the ball first

    @property
    def k(self) -> int:
        return len(self.players)

    @property
    def threat(self) -> float:
        v = solve_values(self.P[:, : self.k], self.P[:, self.k], self.g)
        return float(self.start @ v)

    def without(self, player, adapt: bool) -> "PlayerChain":
        i = self.players.index(player)
        k = self.k
        P = self.P.copy()
        to_i = P[:, i].copy()
        P[:, i] = 0.0
        if adapt:
            others = P[:, :k].sum(1)
            scale = np.divide(others + to_i, others, out=np.ones(k), where=others > 0)
            P[:, :k] *= scale[:, None]
            P[:, k + 1] += np.where(others > 0, 0.0, to_i)
        else:
            P[:, k + 1] += to_i
        # The removed player never has the ball: his row is irrelevant, and the
        # possessions he would have started go to team-mates proportionally.
        start = self.start.copy()
        start[i] = 0.0
        if start.sum() <= 0:
            # Nobody else ever started a possession: who would is unknown, so
            # spread them evenly rather than letting possessions vanish.
            start = np.ones(k)
            start[i] = 0.0
        start = start / start.sum()
        return PlayerChain(self.players, P, self.g, start)


def player_actions(events: pl.LazyFrame) -> pl.DataFrame:
    """Open-play passes, shots and losses with the passer and receiver."""
    return (classify_actions(events, open_play_only=True)
            .filter(pl.col("player_id").is_not_null()
                    & ~((pl.col("kind") == "move") & (pl.col("type") == "Carry")))
            .select("match_id", "possession", "idx", "team_id", "player_id",
                    "recipient_id", "kind", "type", "xg")
            .collect())


def build(actions: pl.DataFrame, team_id: int, min_actions: int = MIN_ACTIONS,
          keep_matches=None) -> PlayerChain:
    a = actions.filter(pl.col("team_id") == team_id)
    if keep_matches is not None:
        a = a.filter(pl.col("match_id").is_in(list(keep_matches)))
    counts = a.group_by("player_id").len()
    regulars = (counts.filter(pl.col("len") >= min_actions)
                      .sort(["len", "player_id"], descending=[True, False])["player_id"].to_list())
    nodes = regulars + [OTHERS]
    index = {p: n for n, p in enumerate(regulars)}
    k = len(nodes)

    def node(col):
        return pl.col(col).replace_strict(index, default=k - 1, return_dtype=pl.Int64)

    a = a.with_columns(src=node("player_id"),
                       dst=pl.when(pl.col("recipient_id").is_null()).then(None).otherwise(node("recipient_id")))
    C = np.zeros((k, k + 2))
    passes = a.filter((pl.col("kind") == "move") & pl.col("dst").is_not_null())
    np.add.at(C, (passes["src"].to_numpy(), passes["dst"].to_numpy()), 1.0)
    shots = a.filter(pl.col("kind") == "shot")
    np.add.at(C[:, k], shots["src"].to_numpy(), 1.0)
    lost = a.filter(pl.col("kind") == "turnover")
    np.add.at(C[:, k + 1], lost["src"].to_numpy(), 1.0)
    xg = np.bincount(shots["src"].to_numpy(), weights=shots["xg"].fill_null(0.0).to_numpy(), minlength=k)

    team_row = C.sum(0)
    team_row = team_row / team_row.sum()
    # Shrink each player's row toward the team's average row.
    P = (C + KAPPA_ROW * team_row) / (C.sum(1, keepdims=True) + KAPPA_ROW)
    team_g = xg.sum() / max(C[:, k].sum(), 1.0)
    g = (xg + KAPPA_XG * team_g) / (C[:, k] + KAPPA_XG)

    firsts = a.sort("idx").group_by("match_id", "possession", maintain_order=True).agg(pl.first("src"))
    start = np.bincount(firsts["src"].to_numpy(), minlength=k).astype(float)
    return PlayerChain(nodes, P, g, start / max(start.sum(), 1.0))


def removal_effects(chain: PlayerChain, top: int = 5) -> list[dict]:
    base = chain.threat
    rows = []
    for p in chain.players:
        if p == OTHERS:
            continue
        rows.append({"player_id": p,
                     "drop_adapt": 1 - chain.without(p, adapt=True).threat / base,
                     "drop_no_adapt": 1 - chain.without(p, adapt=False).threat / base})
    return sorted(rows, key=lambda r: (-r["drop_adapt"], -r["drop_no_adapt"]))[:top]


def opponent_adjusted_rates(actions: pl.DataFrame) -> dict:
    """{(match_id, team_id): xG per possession / what that opponent usually concedes}.

    The usual level is the opponent's average conceded rate in its OTHER matches.
    Absences cluster in particular parts of a season, so without this a
    player's "effect" is partly just who the team happened to play.
    """
    pm = (actions.group_by("match_id", "team_id")
                 .agg(xg=pl.col("xg").fill_null(0.0).sum(), n=pl.col("possession").n_unique())
                 .with_columns(rate=pl.col("xg") / pl.col("n")))
    pairs = (pm.join(pm.select("match_id", pl.col("team_id").alias("opp_id")), on="match_id")
               .filter(pl.col("team_id") != pl.col("opp_id")))
    conc = pairs.select("match_id", pl.col("opp_id").alias("defender"), pl.col("rate").alias("conceded"))
    tot = conc.group_by("defender").agg(s=pl.col("conceded").sum(), c=pl.len())
    usual = (conc.join(tot, on="defender")
                 .with_columns(usual=pl.when(pl.col("c") > 1)
                                       .then((pl.col("s") - pl.col("conceded")) / (pl.col("c") - 1)))
                 .select("match_id", pl.col("defender").alias("opp_id"), "usual"))
    adj = pairs.join(usual, on=["match_id", "opp_id"]).with_columns(adj=pl.col("rate") / pl.col("usual"))
    return {(m, t): a for m, t, a in adj.select("match_id", "team_id", "adj").iter_rows()
            if a is not None}


def missed_matches(actions: pl.DataFrame, lineups: pl.DataFrame, team_id: int,
                   min_missed: int = 3, rates: dict | None = None) -> list[dict]:
    """Natural experiment: predicted vs observed change when a regular was absent.

    Predicted: the player-chain removal bounds, fitted on the matches he played.
    Observed: the team's xG per possession in matches he missed vs played. Both
    sides are noisy and confounded (opponents differ), so this is a consistency
    check across many players, not proof for any one.
    """
    a = actions.filter(pl.col("team_id") == team_id)
    # Lineups list the whole matchday squad; an unused substitute has no
    # positions, so "in the lineup" alone does not mean "played".
    played = (lineups.filter((pl.col("team_id") == team_id) & (pl.col("positions") != "[]"))
                     .select("match_id", "player_id").unique())
    team_matches = set(a["match_id"].unique().to_list())
    poss = a.group_by("match_id").agg(xg=pl.col("xg").fill_null(0.0).sum(),
                                      n=pl.struct("possession").n_unique())
    full = build(a, team_id)
    out = []
    for p in full.players:
        if p == OTHERS:
            continue
        with_p = set(played.filter(pl.col("player_id") == p)["match_id"].to_list()) & team_matches
        without = team_matches - with_p
        if len(without) < min_missed or len(with_p) < min_missed:
            continue
        chain = build(a, team_id, keep_matches=with_p)
        if p not in chain.players:
            continue
        if rates is not None:
            # Opponent-adjusted: mean of each match's rate relative to the opponent.
            def rate(ms):
                vals = [rates[(m, team_id)] for m in ms if (m, team_id) in rates]
                return float(np.mean(vals)) if vals else float("nan")
        else:
            def rate(ms):
                f = poss.filter(pl.col("match_id").is_in(list(ms)))
                return f["xg"].sum() / max(f["n"].sum(), 1)
        observed = 1 - rate(without) / max(rate(with_p), 1e-9)
        base = chain.threat
        out.append({"player_id": p, "missed": len(without), "played": len(with_p),
                    "observed_drop": observed,
                    "pred_adapt": 1 - chain.without(p, True).threat / base,
                    "pred_no_adapt": 1 - chain.without(p, False).threat / base})
    return out
