"""Hand-checkable tests for the FCA engine + projection.  Run:  python tests/test_sfca.py"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import sfca  # noqa: E402
from geo import latlon_to_svy21, svy21_to_latlon  # noqa: E402


def test_classic_2sfca_hand_example():
    # 3 demand points on a line, 2 centres; d0 = 1000 m
    dxy = np.array([[0, 0], [800, 0], [2000, 0]], float)
    sxy = np.array([[0, 0], [1500, 0]], float)
    P = np.array([1000, 2000, 500], float)
    S = np.array([30, 10], float)
    D = sfca.distance_matrix(dxy, sxy)
    A, R, dem = sfca.run(P, S, D, 1000, "2sfca")
    # centre 0 reaches i0 (0 m), i1 (800 m)            -> demand 3000, R0 = 30/3000 = 0.01
    # centre 1 reaches i1 (700 m), i2 (500 m)          -> demand 2500, R1 = 10/2500 = 0.004
    assert np.allclose(dem, [3000, 2500])
    assert np.allclose(R, [0.01, 0.004])
    # A0 = R0 = .01 ; A1 = R0 + R1 = .014 ; A2 = R1 = .004
    assert np.allclose(A, [0.01, 0.014, 0.004])
    assert np.isclose((P * A).sum(), S.sum())


def test_conservation_all_methods_and_closure():
    rng = np.random.default_rng(0)
    dxy = rng.uniform(0, 5000, (400, 2))
    sxy = rng.uniform(0, 5000, (12, 2))
    P = rng.integers(50, 2000, 400).astype(float)
    S = rng.integers(20, 120, 12).astype(float)
    D = sfca.distance_matrix(dxy, sxy)
    for m in ["2sfca", "e2sfca_gauss", "3sfca_gauss"]:
        A, R, dem = sfca.run(P, S, D, 1000, m)
        reachable = dem > 0
        assert np.isclose((P * A).sum(), S[reachable].sum()), m
        mask = np.ones(12)
        mask[3] = 0
        A2, R2, _ = sfca.run(P, S, D, 1000, m, open_mask=mask)
        assert R2[3] == 0
        assert (A2 <= A + 1e-12).all() or m == "3sfca_gauss"


def test_gauss_weights():
    W = sfca.weight_matrix(np.array([[0.0, 500.0, 1000.0, 1200.0]]), 1000, "gauss")
    assert np.isclose(W[0, 0], 1) and np.isclose(W[0, 2], 0) and W[0, 3] == 0 and 0 < W[0, 1] < 1


def test_svy21_known_point():
    # Tiong Bahru Market: NEA master file gives both systems
    x, y = latlon_to_svy21(1.2847855982150984, 103.83218154655142)
    assert abs(x - 27873.45773709) < 0.5 and abs(y - 29690.58348755) < 0.5
    lat, lon = svy21_to_latlon(x, y)
    assert abs(lat - 1.2847856) < 1e-6 and abs(lon - 103.8321815) < 1e-6


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
