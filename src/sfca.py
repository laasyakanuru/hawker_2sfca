"""
Floating Catchment Area engine (pure numpy, fully vectorised).

Notation (README section 5):
    i  demand point (HDB block / condo project / landed cell / centroid), population P_i
    j  hawker centre, supply S_j = cooked-food stalls
    d_ij straight-line distance in metres (x DETOUR_FACTOR), d0 = catchment radius
    W(d) distance-decay weight, 0 beyond d0

    Step 1  R_j = S_j / sum_i  W_ij * P_i                 (stalls per resident in j's catchment)
    Step 2  A_i = sum_j  W_ij * R_j                        (stalls per resident reachable from i)

    3SFCA (Wan et al., 2012) adds a selection weight G_ij = W_ij / sum_k W_ik so a
    resident's demand is split between competing centres instead of being counted in full
    at every centre:
            R_j = S_j / sum_i G_ij W_ij P_i ;   A_i = sum_j G_ij W_ij R_j

Property used as a unit test: sum_i P_i A_i == sum_j S_j over centres that have any
demand in reach (supply is fully "distributed" to the population).
"""
from __future__ import annotations

import numpy as np

_E = np.exp(-0.5)


def distance_matrix(dxy: np.ndarray, sxy: np.ndarray, detour: float = 1.0) -> np.ndarray:
    d = np.sqrt(((dxy[:, None, :] - sxy[None, :, :]) ** 2).sum(-1))
    return d * detour


def weight_matrix(D: np.ndarray, d0: float, kind: str) -> np.ndarray:
    inside = D <= d0
    if kind == "binary":
        return inside.astype(float)
    if kind == "gauss":  # Dai (2010) Gaussian: 1 at d=0, 0 at d=d0
        g = (np.exp(-0.5 * (D / d0) ** 2) - _E) / (1 - _E)
        return np.where(inside, g, 0.0)
    raise ValueError(kind)


def fca(P: np.ndarray, S: np.ndarray, W: np.ndarray, three_step: bool = False):
    """Return (A_i, R_j, demand_j). P (n,), S (m,), W (n,m). Closed centres: S_j = 0 and
    their column in W should be zeroed so they neither serve nor attract demand."""
    if three_step:
        rs = W.sum(1, keepdims=True)
        G = np.divide(W, rs, out=np.zeros_like(W), where=rs > 0)
        K = G * W
    else:
        K = W
    demand = K.T @ P                      # effective catchment population of each centre
    R = np.divide(S, demand, out=np.zeros_like(S, dtype=float), where=demand > 0)
    A = K @ R
    return A, R, demand


def method_spec(method: str):
    return {"2sfca": ("binary", False), "e2sfca_gauss": ("gauss", False),
            "3sfca_gauss": ("gauss", True)}[method]


def run(P, S, D, d0, method, open_mask=None):
    kind, three = method_spec(method)
    W = weight_matrix(D, d0, kind)
    S = S.astype(float).copy()
    if open_mask is not None:
        W = W * open_mask[None, :]
        S = S * open_mask
    return fca(P, S, W, three)
