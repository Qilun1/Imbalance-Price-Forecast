"""Mixture maths of the structural model (no data needed)."""
import numpy as np

from imbalance.mixture import GRID, LEVELS, _quantile_fn, mixture, mixture_quantile


def _const(v, n=3):
    return np.full((n, len(GRID)), float(v))


def test_quantile_fn_hits_the_knots():
    knots = np.array([[-30.0, -20, -10, 0, 10, 20, 30]])
    qf = _quantile_fn(knots)
    for lv, k in zip(LEVELS, knots[0]):
        assert abs(np.interp(lv, GRID, qf[0]) - k) < 1.0
    assert np.all(np.diff(qf[0]) >= 0)


def test_pure_side_returns_that_side():
    n = 3
    vals, cw = mixture(np.ones(n), np.zeros(n), np.zeros(n), _const(80), _const(-20))
    assert np.allclose(mixture_quantile(vals, cw, 0.5), 80)


def test_two_modes():
    n = 3
    p_up = np.full(n, 0.3)
    vals, cw = mixture(p_up, 1 - p_up, np.zeros(n), _const(100), _const(-20))
    assert np.allclose(mixture_quantile(vals, cw, 0.1), -20)    # 70 % of the mass is down
    assert np.allclose(mixture_quantile(vals, cw, 0.5), -20)
    assert np.allclose(mixture_quantile(vals, cw, 0.9), 100)    # top 30 % is up
    w = np.diff(np.concatenate([np.zeros((n, 1)), cw], 1), axis=1)
    assert np.allclose((w * (vals > 50)).sum(1), 0.3)           # P(spike high) = P(up) here
