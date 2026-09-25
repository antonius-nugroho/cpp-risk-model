"""Probability distribution helpers (inverse-CDF sampling).

Sampling through the inverse CDF lets the model apply correlations
(Gaussian copula) and reuse identical random numbers across scenarios
("common random numbers"), so scenario differences reflect the decision
rather than sampling noise.

Specs (YAML):
    5                                  constant
    [a, m, b]                          triangular(min, mode, max)
    {type: constant,   value}
    {type: normal,     mean, sd, min?, max?}
    {type: uniform,    min, max}
    {type: triangular, min, mode, max}
    {type: pert,       min, mode, max, lambda?}
    {type: lognormal,  mean, sd, max?}        # mean/sd in real units
    {type: gamma,      shape, scale}          # used for uncertain event rates
    {type: empirical,  values: [...]}         # resample observed data (interpolated quantiles)
"""
from __future__ import annotations

import numpy as np
from scipy import stats


def as_spec(x) -> dict:
    if isinstance(x, dict):
        return x
    if isinstance(x, (int, float)):
        return {"type": "constant", "value": float(x)}
    if isinstance(x, (list, tuple)) and len(x) == 3:
        return {"type": "triangular", "min": x[0], "mode": x[1], "max": x[2]}
    raise ValueError(f"Cannot interpret distribution spec: {x!r}")


def ppf(spec, u) -> np.ndarray:
    spec = as_spec(spec)
    t = spec["type"].lower()
    u = np.asarray(u, dtype=float)
    if t == "constant":
        return np.full_like(u, float(spec["value"]))
    if t == "normal":
        x = stats.norm.ppf(u, loc=spec["mean"], scale=spec["sd"])
        return np.clip(x, spec.get("min", -np.inf), spec.get("max", np.inf))
    if t == "uniform":
        a, b = float(spec["min"]), float(spec["max"])
        return a + u * (b - a)
    if t in ("triangular", "pert"):
        a, m, b = float(spec["min"]), float(spec["mode"]), float(spec["max"])
        if not a <= m <= b:
            raise ValueError(f"{t} needs min <= mode <= max, got {spec}")
        if b == a:
            return np.full_like(u, a)
        if t == "triangular":
            return stats.triang.ppf(u, (m - a) / (b - a), loc=a, scale=b - a)
        lam = float(spec.get("lambda", 4.0))
        return a + (b - a) * stats.beta.ppf(
            u, 1 + lam * (m - a) / (b - a), 1 + lam * (b - m) / (b - a))
    if t == "lognormal":
        mean, sd = float(spec["mean"]), float(spec["sd"])
        s2 = np.log(1 + (sd / mean) ** 2)
        x = stats.lognorm.ppf(u, s=np.sqrt(s2), scale=np.exp(np.log(mean) - s2 / 2))
        return np.minimum(x, spec.get("max", np.inf))
    if t == "gamma":
        return stats.gamma.ppf(u, a=float(spec["shape"]), scale=float(spec["scale"]))
    if t == "empirical":
        v = np.sort(np.asarray(spec["values"], dtype=float))
        return np.interp(u, (np.arange(len(v)) + 0.5) / len(v), v)
    raise ValueError(f"Unknown distribution type '{t}'")


def central(spec) -> float:
    """Value a deterministic plan would use (mode / mean)."""
    spec = as_spec(spec)
    t = spec["type"].lower()
    if t == "constant":
        return float(spec["value"])
    if t in ("normal", "lognormal"):
        return float(spec["mean"])
    if t == "uniform":
        return (float(spec["min"]) + float(spec["max"])) / 2
    if t in ("triangular", "pert"):
        return float(spec["mode"])
    if t == "gamma":
        return float(spec["shape"]) * float(spec["scale"])
    if t == "empirical":
        return float(np.median(spec["values"]))
    raise ValueError(f"Unknown distribution type '{t}'")
