"""Monte Carlo engine for the calibrated power plant risk model (v2).

One iteration = one forecast year for one unit.

  planned outage hours      (inspection type)             -> POH
  outage events  FO/MO/SE/OS  (hours per event)            -> FOH, MOH, SEH
  derating events FD/MD/PD  (equivalent derated hours)     -> EFDH, EMDH, EPDH
  EAF  = (PH - POH - SEH - MOH - FOH - EFDH - EMDH - EPDH) / PH
  EFOR = (FOH + EFDH) / (SH + FOH)
  net production  = DMN x EAF x PH x net output factor
  gross production = net / (1 - aux share)
  fuel heat = net x NPHR  -> coal (GCV) and biomass (co-firing share)

Random numbers use labelled streams, so every scenario sees identical draws
("common random numbers"); each unit has its own event and plant streams,
while shared market variables (coal GCV) use one stream for all units.
"""
from __future__ import annotations

import copy
import zlib

import numpy as np
import pandas as pd
from scipy import stats

from distributions import as_spec, central, ppf

KCAL_TO_TJ = 4.1868e-9
EPS = 1e-12
MAX_OCCURRENCES = 80


def _slot_count(occ) -> int:
    """Fixed number of pre-drawn impact slots per event class (independent of
    scenario multipliers, so common random numbers are preserved)."""
    if occ["type"] != "poisson":
        return 1
    rate = occ["rate"]
    hi = ppf(rate, np.array([0.9999]))[0] if isinstance(rate, dict) else float(rate)
    return int(np.clip(stats.poisson.ppf(1 - 1e-7, 4 * hi + 1) + 1, 5, MAX_OCCURRENCES))
OUTAGE_CATS = ("FO", "MO", "SE", "OS")
DERATE_CATS = ("FD", "MD", "PD")


def _rng(seed, label):
    return np.random.default_rng(np.random.SeedSequence([int(seed), zlib.crc32(label.encode())]))


def _u(seed, label, shape):
    return np.clip(_rng(seed, label).random(shape), EPS, 1 - EPS)


def _unit_uniforms(names, pairs, n, seed, unit):
    k = len(names)
    idx = {nm: i for i, nm in enumerate(names)}
    corr = np.eye(k)
    for a, b, rho in pairs or []:
        if a in idx and b in idx:
            corr[idx[a], idx[b]] = corr[idx[b], idx[a]] = float(rho)
    chol = np.linalg.cholesky(corr)
    z = _rng(seed, f"{unit}:copula").standard_normal((n, k))
    return np.clip(stats.norm.cdf(z @ chol.T), EPS, 1 - EPS)


# --------------------------------------------------------------------------
def simulate_unit(cfg, unit, n, seed, disabled=frozenset(), plan=False):
    """Simulate n forecast years for one unit. plan=True gives the deterministic
    budget case (central values, no unplanned events)."""
    uc = cfg["units"][unit]
    ph = float(cfg["period_hours"])
    const = cfg.get("constants", {})

    # ---- continuous uncertainties ------------------------------------------
    unc = uc["uncertainties"]
    names = list(unc)
    if plan:
        x = {nm: np.full(n, central(unc[nm])) for nm in names}
        gcv = np.full(n, central(cfg["shared_uncertainties"]["coal_gcv_kcal_kg"]))
        poh = np.full(n, central(uc["planned_outage_hours"]))
    else:
        u = _unit_uniforms(names, uc.get("correlations"), n, seed, unit)
        x = {nm: ppf(unc[nm], u[:, i]) for i, nm in enumerate(names)}
        gcv = ppf(cfg["shared_uncertainties"]["coal_gcv_kcal_kg"], _u(seed, "shared:coal_gcv", n))
        poh = ppf(uc["planned_outage_hours"], _u(seed, f"{unit}:planned_outage", n))

    # ---- events ----------------------------------------------------------------
    hours = {c: np.zeros(n) for c in OUTAGE_CATS + DERATE_CATS}
    counts, class_hours = {}, {}
    for name, ev in cfg["event_classes"].items():
        n_slots = _slot_count(ev["occurrence"])
        occ = ev["occurrence"]
        mult = float(ev.get("rate_multiplier", 1.0)) * float(uc.get("event_rate_multiplier", 1.0))
        u_occ = _u(seed, f"{unit}:{name}:occ", n)
        u_rate = _u(seed, f"{unit}:{name}:rate", n)
        if plan or name in disabled:
            k = np.zeros(n, dtype=int)
        elif occ["type"] == "poisson":
            rate = occ["rate"]
            lam = (ppf(rate, u_rate) if isinstance(rate, dict) else np.full(n, float(rate))) * mult
            k = np.where(lam > 0, stats.poisson.ppf(u_occ, np.maximum(lam, EPS)), 0)
            k = np.minimum(k, n_slots).astype(int)
        elif occ["type"] == "bernoulli":
            p = occ.get("probability_by_inspection", {}).get(uc.get("inspection_type"), occ.get("probability", 0))
            k = (u_occ < min(float(p) * mult, 1.0)).astype(int)
        else:
            raise ValueError(f"{name}: unknown occurrence type {occ['type']}")
        counts[name] = k
        mask = np.arange(n_slots)[None, :] < k[:, None]
        class_hours[name] = np.zeros(n)
        for key, spec in ev["impacts"].items():
            pool = _u(seed, f"{unit}:{name}:{key}", (n, n_slots))
            class_hours[name] += (ppf(spec, pool) * mask).sum(axis=1)
        hours[ev["category"]] += class_hours[name]

    # ---- availability -------------------------------------------------------
    outage = poh + hours["SE"] + hours["MO"] + hours["FO"] + hours["OS"]
    avail = np.clip(ph - outage, 0, ph)
    derate_total = hours["FD"] + hours["MD"] + hours["PD"]
    scale = np.where(derate_total > avail, avail / np.maximum(derate_total, EPS), 1.0)
    efdh, emdh, epdh = hours["FD"] * scale, hours["MD"] * scale, hours["PD"] * scale
    eah = avail - efdh - emdh - epdh
    eaf = eah / ph
    foh = np.minimum(hours["FO"] + hours["OS"], ph)
    efor = (foh + efdh) / np.maximum(avail + foh, EPS)

    # ---- production and fuel -------------------------------------------------
    dmn = float(uc["dmn_mw"])
    net_mwh = dmn * eah * x["net_output_factor"]
    gross_mwh = net_mwh / (1 - x["aux_share"])
    potential_net_mwh = dmn * np.clip(ph - poh, 0, ph) * x["net_output_factor"]
    heat_kcal = net_mwh * 1000 * x["nphr_kcal_kwh"]
    bio_share = np.clip(x["cofiring_share"], 0, 1)
    coal_kg = heat_kcal * (1 - bio_share - float(uc.get("hsd_share", 0))) / gcv
    bio_kg = heat_kcal * bio_share / float(uc["biomass_gcv_kcal_kg"])
    co2_t = coal_kg * gcv * KCAL_TO_TJ * float(const.get("emission_factor_coal_tco2_tj", 96.1))

    eco = cfg.get("economics", {})
    price = lambda key: float(uc.get(key, eco.get(key, 0)))  # unit price from the pricing file, else plant value
    fuel_cost = (coal_kg / 1000 * price("coal_price_rp_t") + bio_kg / 1000 * price("biomass_price_rp_t")) / 1e9
    # BPP = Biaya Pokok Penyediaan; configs written before v3.6 name it energy_value_rp_kwh
    bpp = float(uc.get("bpp_rp_kwh", uc.get("energy_value_rp_kwh",
                                            eco.get("bpp_rp_kwh", eco.get("energy_value_rp_kwh", 0)))))
    opportunity_loss = (potential_net_mwh - net_mwh) * 1000 * bpp / 1e9   # lost net energy x BPP

    out = pd.DataFrame({
        "eaf_pct": eaf * 100, "efor_pct": efor * 100,
        "poh_h": poh, "foh_h": foh, "moh_h": hours["MO"], "seh_h": hours["SE"],
        "efdh_h": efdh, "emdh_h": emdh, "epdh_h": epdh,
        "net_gwh": net_mwh / 1000, "gross_gwh": gross_mwh / 1000,
        "lost_net_gwh": (potential_net_mwh - net_mwh) / 1000,
        "nphr_kcal_kwh": x["nphr_kcal_kwh"], "coal_kt": coal_kg / 1e6, "biomass_kt": bio_kg / 1e6,
        "co2_kt": co2_t / 1000, "co2_intensity_t_mwh": co2_t / np.maximum(net_mwh, EPS),
        "fuel_cost_rp_bn": fuel_cost, "opportunity_loss_rp_bn": opportunity_loss,
    })
    for nm, arr in x.items():
        out[f"in:{nm}"] = arr
    out["in:coal_gcv_kcal_kg"] = gcv
    out["in:planned_outage_hours"] = poh
    for nm, k in counts.items():
        out[f"n:{nm}"] = k
    # equivalent full-outage hours and net energy lost per event class (additive decomposition)
    for nm, h in class_hours.items():
        out[f"h:{nm}"] = h
        out[f"gwh:{nm}"] = h * dmn * x["net_output_factor"] / 1000
    out["gwh:planned_outage"] = poh * dmn * x["net_output_factor"] / 1000
    return out


SUM_COLS = ["poh_h", "foh_h", "moh_h", "seh_h", "efdh_h", "emdh_h", "epdh_h", "net_gwh", "gross_gwh",
            "lost_net_gwh", "coal_kt", "biomass_kt", "co2_kt", "fuel_cost_rp_bn", "opportunity_loss_rp_bn"]


def simulate_plant(cfg, n, seed, disabled=frozenset(), plan=False):
    """Returns {unit: df, ..., 'Plant': df}. Plant EAF/EFOR are capacity-weighted."""
    res = {u: simulate_unit(cfg, u, n, seed, disabled, plan) for u in cfg["units"]}
    dmn = {u: float(cfg["units"][u]["dmn_mw"]) for u in cfg["units"]}
    w = {u: dmn[u] / sum(dmn.values()) for u in dmn}
    plant = pd.DataFrame({c: sum(res[u][c] for u in res) for c in SUM_COLS})
    plant["eaf_pct"] = sum(res[u]["eaf_pct"] * w[u] for u in res)
    plant["efor_pct"] = sum(res[u]["efor_pct"] * w[u] for u in res)
    plant["nphr_kcal_kwh"] = (sum(res[u]["nphr_kcal_kwh"] * res[u]["net_gwh"] for u in res)
                              / np.maximum(plant["net_gwh"], EPS))
    plant["co2_intensity_t_mwh"] = plant["co2_kt"] / np.maximum(plant["net_gwh"], EPS)
    ev_cols = [c for c in res[next(iter(res))].columns if c.startswith(("n:", "h:", "gwh:"))]
    for c in ev_cols:
        plant[c] = sum(res[u][c] for u in res)
    for u in res:
        for c in res[u].columns:
            if c.startswith("in:"):
                plant[f"{c}[{u}]"] = res[u][c]
    res["Plant"] = plant
    return res


def apply_overrides(cfg, overrides):
    """Dotted-path overrides, e.g. {'event_classes.FO_tube_leak.rate_multiplier': 0.5}."""
    c = copy.deepcopy(cfg)
    for path, value in (overrides or {}).items():
        keys, node = path.split("."), c
        for k in keys[:-1]:
            if k not in node:
                raise KeyError(f"Override path not found: {path}")
            node = node[k]
        node[keys[-1]] = value
    return c
