"""THE INTERACTION TEST - the experiment that decides whether the thesis holds.

Claim under test: a defensive vulnerability should be dangerous IN PROPORTION to
whether the attacking team can exploit it. A high line should hurt against teams
that run in behind, and not much against teams that do not. If a vulnerability
predicts danger uniformly regardless of who is attacking, we have not built a
match-up engine, we have rebuilt a generic xG model with extra steps.

STATISTICAL NOTE, and it is the whole ballgame here. Ability is a TEAM-level
quantity: it varies across 32 teams, not across 95,160 snapshots. Treating
snapshots as independent observations inflates the effective sample size by
three orders of magnitude and produces p-values that are meaningless. An earlier
run of this test did exactly that and reported a "significant" interaction which
does not survive a correct null.

So significance here comes from a PERMUTATION NULL AT THE TEAM LEVEL: reassign
whole ability profiles between teams and recompute the interaction. That
preserves the within-team correlation structure and asks the only question that
matters - could this association arise by chance from 32 teams?

Guards against circularity:
  * vulnerability comes from the DEFENDING shape, ability from the ATTACKING
    team's own passes - different data;
  * ability is estimated leave-one-match-out;
  * the interaction must beat both main effects and ball position.
"""
import sys
sys.path.insert(0, "src")
import numpy as np
from sklearn.linear_model import LogisticRegression

RNG = np.random.default_rng(0)
N_PERM = 400

d = np.load("data/cache/table.npz", allow_pickle=True)
y, ball, F, P = d["y"], d["ball"], d["F"], d["P"]
attacking = d["attacking"]
fnames = list(d["feature_names"])
pnames = list(d["profile_names"])
fi = {n: i for i, n in enumerate(fnames)}
pi = {n: i for i, n in enumerate(pnames)}
n_teams = len(d["teams"])

print("rows %d | teams %d | shot rate %.3f" % (len(y), n_teams, y.mean()))
print("effective sample size for a team-level effect is %d, not %d\n"
      % (n_teams, len(y)))


def z(v):
    return (v - v.mean()) / (v.std() + 1e-9)


# One ability value per team, so permutation can reassign whole profiles.
team_ability = np.full((n_teams, P.shape[1]), np.nan)
for t in range(n_teams):
    m = attacking == t
    if m.any():
        team_ability[t] = P[m][0]

zx, zy = z(ball[:, 0]), z(ball[:, 1])


def interaction_coef(v, a):
    X = np.column_stack([zx, zy, v, a, v * a])
    m = LogisticRegression(C=np.inf, max_iter=400).fit(X, y)
    return float(m.coef_[0][-1])


PAIRS = [
    ("line_height", "behind_rate", "high line x runs in behind"),
    ("space_behind", "behind_rate", "space behind x runs in behind"),
    ("max_lateral_gap", "behind_rate", "lateral seam x runs in behind"),
    ("ballside_ratio", "switch_rate", "ball-side overload x switching"),
    ("block_width", "cross_rate", "stretched block x crossing"),
    ("between_lines_gap", "directness", "between-lines gap x directness"),
]

print("%-34s %9s %9s %9s" % ("interaction", "coef", "perm p", "verdict"))
print("-" * 72)
results = []
for vf, pf, label in PAIRS:
    v = z(F[:, fi[vf]])
    col = pi[pf]
    a_obs = z(team_ability[attacking, col])
    obs = interaction_coef(v, a_obs)

    null = np.empty(N_PERM)
    for k in range(N_PERM):
        perm = RNG.permutation(n_teams)
        null[k] = interaction_coef(v, z(team_ability[perm[attacking], col]))
    p = float((np.abs(null) >= abs(obs)).mean())
    results.append((label, obs, p))
    verdict = "SUPPORTS" if p < 0.05 else "no effect"
    print("%-34s %+9.4f %9.3f %9s" % (label, obs, p, verdict))

print()
sig = [r for r in results if r[2] < 0.05]
bonf = 0.05 / len(PAIRS)
print("tests run: %d   Bonferroni threshold: p < %.4f" % (len(PAIRS), bonf))
print("passing uncorrected: %d   passing corrected: %d"
      % (len(sig), sum(1 for r in results if r[2] < bonf)))
print("\nnaive per-snapshot p-values would be ~1000x smaller and are not reported,")
print("because 95,160 snapshots carry only 32 independent ability values.")
