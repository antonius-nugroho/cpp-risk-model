"""Calibrate the risk model from plant data.

Inputs
------
data/Failure_Data_highlighted.xlsx   failure/derating log + "Status Mapping" sheet
data/Data_Pengusahaan.xlsx           monthly production & performance data
data/Pricing.xlsx                    monthly coal / biomass price and BPP per unit -> fuel cost, value of lost energy
                                     (optional)

Outputs
-------
config/model_config.yaml             model inputs (edit freely, then run run.py)
config/calibration_evidence.xlsx     the evidence behind every calibrated number

Usage:  python calibrate.py [--failure ...] [--production ...] [--pricing ...] [--forecast-year 2026]
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

MERGE_GAP_MIN = 10            # rows split at month boundaries are merged if the gap <= 10 min
MIN_EVENTS_PER_CLASS = 2      # smaller classes are merged into "<category>_other"
DERATE_REF_MW = 100.0         # gross MW basis of loss_output_mw (matches EFDH/EMDH/EPDH)

# cause-code system (2nd-last part of failure_cause_code) -> failure-mode group
SYSTEM_GROUP = {
    "Boiler Tube Leaks": "tube_leak",
    "Boiler Tube Fireside Slagging or Fouling": "tube_leak",
    "Exciter": "generator_exciter",
    "Controls": "generator_exciter",
    "Electrical": "generator_exciter",
    "Boiler Air and Gas Systems": "fans_air_gas",
    "Boiler Fuel Supply to Bunker": "coal_feeding",
    "Bed Solids Recirculation": "cfb_bed_ash_refractory",
    "Bed Material Removal System": "cfb_bed_ash_refractory",
    "External Fluidized Bed Heat Exchanger": "cfb_bed_ash_refractory",
    "Slag and Ash Removal": "cfb_bed_ash_refractory",
    "Boiler Internals and Structures": "cfb_bed_ash_refractory",
    "Circulating Water Systems": "cooling_water",
    "Feedwater System": "bop_feedwater_aux",
    "Auxiliary Systems": "bop_feedwater_aux",
    "Boiler Piping System": "bop_feedwater_aux",
    "Performance": "performance",
    "Boiler Overhaul and Inspections": "inspection_related",
    "Miscellaneous (Generator)": "inspection_related",
    "Catastrophe": "external",
    "Miscellaneous (External)": "external",
}
GROUP_LABEL = {
    "tube_leak": "Boiler tube leak", "generator_exciter": "Generator, exciter & electrical",
    "fans_air_gas": "Fans, dampers & air/gas system", "coal_feeding": "Coal feeding / fuel supply to bunker",
    "cfb_bed_ash_refractory": "CFB bed, ash, loop seal & refractory", "cooling_water": "Circulating water system",
    "bop_feedwater_aux": "Feedwater, piping & auxiliaries", "performance": "Unit performance limitation",
    "inspection_related": "Inspection-related (overrun / extension / derate)", "external": "External (lightning, grid)",
    "other": "Other causes", "all": "All causes",
}
CAT_LABEL = {"FO": "Forced outage", "MO": "Maintenance outage", "SE": "Scheduled outage extension",
             "OS": "Outage slip", "FD": "Forced derating", "MD": "Maintenance derating", "PD": "Planned derating"}
OUTAGE_CATS = {"FO", "MO", "SE", "OS"}


DEFAULT_MAPPING = {"FO": "FO", "FO.OS": "OS", "MO": "MO", "PE": "SE", "ME": "SE", "FD": "FD", "MD": "MD", "PD": "PD"}
# required columns (the upload templates in app_lib/templates.py list the same columns, in this order)
FAILURE_COLUMNS = ["timestamp_start", "timestamp_stop", "unit_no", "unit_status", "failure_cause_code", "failure_impact",
                   "loss_output_mw", "failure_duration_hours", "loss_output_mwh", "root_cause_failure_analysis"]
PRODUCTION_COLUMNS = ["end_of_month", "unit", "kwh_produksi_kwh", "kwh_netto_penjualan_kwh", "ph_periodehours_jam",
                      "sh_servicehours_jam", "ah_availablehours_jam", "foh_forcedoutagehours_jam",
                      "poh_plannedoutagehours_jam", "moh_maintenanceoutagehours_jam", "fo_omc_forcedoutageomchours_jam",
                      "efdh_equivalentforcedderatinghours_jam", "emdh_equivalentmaintenancederatinghours_jam",
                      "epdh_eqplannedderatinghours_jam", "ncf_netcapacityfactor_pct",
                      "pemakaian_bahan_bakar_batubara_kg", "nilai_kalor_batubara_kcal/kg", "pemakaian_biomassa_kg",
                      "nilai_kalor_biomassa_kcal/kg", "pemakaian_batubara,_hsd/bio_solar,_dan_biomassa_kcal",
                      "rencana_produksi_kwh", "rencana_penjualan_kwh", "rencana_pemakaian_batubara_kg"]
PRICING_COLUMNS = ["month", "coal_price_rp_per_ton", "biomass_price_rp_per_ton", "bpp_rp_kwh", "unit_name"]


def _src(x):
    """Accept a path, a file-like object or raw bytes (e.g. from a web upload)."""
    if isinstance(x, (bytes, bytearray)):
        return io.BytesIO(x)
    if hasattr(x, "seek"):
        x.seek(0)
    return x


def failure_sheet(src) -> str:
    names = pd.ExcelFile(_src(src)).sheet_names
    return "All Unit" if "All Unit" in names else names[0]


def load_mapping(src) -> dict:
    """Status Mapping sheet of the highlighted workbook, or the default mapping."""
    try:
        mp = pd.read_excel(_src(src), sheet_name="Status Mapping", header=3)
        mp = mp[mp["status_code"].notna() & mp["Include in calculation"].isin(["Yes", "No"])]
        return {r.status_code: r["Calc category"] for _, r in mp.iterrows() if r["Include in calculation"] == "Yes"}
    except (ValueError, KeyError):
        return dict(DEFAULT_MAPPING)


def read_failure(src) -> pd.DataFrame:
    return pd.read_excel(_src(src), sheet_name=failure_sheet(src))


def missing_columns(df: pd.DataFrame, required) -> list[str]:
    return [c for c in required if c not in df.columns]


def load_events(src, mapping, derate_ref=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = read_failure(src)
    raw["timestamp_start"] = pd.to_datetime(raw["timestamp_start"])
    raw["timestamp_stop"] = pd.to_datetime(raw["timestamp_stop"])
    raw["category"] = raw["unit_status"].map(mapping)
    x = raw[raw["category"].notna()].sort_values(["unit_no", "timestamp_start"]).copy()
    x["system"] = x["failure_cause_code"].fillna("").str.split(" - ").str[-2].fillna("")
    rows, prev = [], None
    for _, r in x.iterrows():
        same = (prev is not None and r.unit_no == prev["unit"] and r.category == prev["category"]
                and r.failure_cause_code == prev["cause_code"]
                and abs((r.timestamp_start - prev["stop"]).total_seconds()) <= MERGE_GAP_MIN * 60)
        if same:
            prev["hours"] += r.failure_duration_hours
            prev["loss_mwh"] += r.loss_output_mwh
            prev["stop"] = r.timestamp_stop
            prev["source_rows"] += 1
            continue
        if prev:
            rows.append(prev)
        prev = dict(unit=r.unit_no, category=r.category, status=r.unit_status, start=r.timestamp_start,
                    stop=r.timestamp_stop, hours=float(r.failure_duration_hours), loss_mwh=float(r.loss_output_mwh),
                    loss_mw=float(r.loss_output_mw), cause_code=r.failure_cause_code, system=r.system,
                    description=r.root_cause_failure_analysis, source_rows=1)
    if prev:
        rows.append(prev)
    if not rows:
        raise ValueError("No events left after applying the status mapping - include at least one status.")
    ev = pd.DataFrame(rows)
    ev["year"] = ev["start"].dt.year
    ev["group"] = ev["system"].map(SYSTEM_GROUP).fillna("other")
    ev["impact_type"] = np.where(ev["category"].isin(OUTAGE_CATS), "outage", "derate")
    ref = derate_ref or detect_derate_reference(raw)
    ev["eq_hours"] = np.where(ev["impact_type"] == "outage", ev["hours"], ev["loss_mwh"] / ref)
    # classes: category x group, small groups merged into <cat>_other
    ev["event_class"] = ev["category"] + "_" + ev["group"]
    counts = ev["event_class"].value_counts()
    small = ev["event_class"].map(counts) < MIN_EVENTS_PER_CLASS
    ev.loc[small, "event_class"] = ev.loc[small, "category"] + "_other"
    for cat, grp in ev.groupby("category"):
        if grp["event_class"].nunique() == 1:
            ev.loc[grp.index, "event_class"] = f"{cat}_all"
    return ev, raw


def load_production(src) -> pd.DataFrame:
    d = pd.read_excel(_src(src)).replace("-", np.nan)
    d["end_of_month"] = pd.to_datetime(d["end_of_month"])
    for c in d.columns:
        if c not in ("end_of_month", "unit"):
            d[c] = pd.to_numeric(d[c], errors="coerce")
    d["year"] = d["end_of_month"].dt.year
    return d


def detect_dmn(prod: pd.DataFrame) -> dict:
    """Net capable power per unit implied by NCF: net kWh / (PH x NCF)."""
    ok = prod["ncf_netcapacityfactor_pct"] > 1
    dmn = prod[ok]["kwh_netto_penjualan_kwh"] / (prod[ok]["ph_periodehours_jam"]
                                                  * prod[ok]["ncf_netcapacityfactor_pct"] / 100) / 1000
    return {u: round(float(v), 2) for u, v in dmn.groupby(prod[ok]["unit"]).median().items()}


def detect_derate_reference(raw: pd.DataFrame) -> float:
    """Gross MW basis of loss_output_mw: gross realisation + loss (100 MW at Tarahan)."""
    if "power_gross_realization" in raw.columns:
        tot = (raw["power_gross_realization"] + raw["loss_output_mw"]).dropna()
        tot = tot[tot > 0]
        if len(tot):
            return round(float(tot.median()), 1)
    return DERATE_REF_MW


def annual_stats(d: pd.DataFrame, dmn_mw) -> pd.DataFrame:
    f = lambda c: d[c].fillna(0)
    d = d.assign(
        eq_derate=f("efdh_equivalentforcedderatinghours_jam") + f("epdh_eqplannedderatinghours_jam")
        + f("emdh_equivalentmaintenancederatinghours_jam"),
        coal_kcal=f("pemakaian_bahan_bakar_batubara_kg") * f("nilai_kalor_batubara_kcal/kg"),
        bio_kcal=f("pemakaian_biomassa_kg") * f("nilai_kalor_biomassa_kcal/kg"),
    )
    d["eah"] = f("ah_availablehours_jam") - d["eq_derate"]
    g = d.groupby(["unit", "year"]).agg(
        months=("end_of_month", "size"), ph=("ph_periodehours_jam", "sum"), sh=("sh_servicehours_jam", "sum"),
        poh=("poh_plannedoutagehours_jam", "sum"), foh=("foh_forcedoutagehours_jam", "sum"),
        moh=("moh_maintenanceoutagehours_jam", "sum"), fo_omc=("fo_omc_forcedoutageomchours_jam", "sum"),
        efdh=("efdh_equivalentforcedderatinghours_jam", "sum"), emdh=("emdh_equivalentmaintenancederatinghours_jam", "sum"),
        epdh=("epdh_eqplannedderatinghours_jam", "sum"), eah=("eah", "sum"),
        gross_kwh=("kwh_produksi_kwh", "sum"), net_kwh=("kwh_netto_penjualan_kwh", "sum"),
        fuel_kcal=("pemakaian_batubara,_hsd/bio_solar,_dan_biomassa_kcal", "sum"),
        coal_kg=("pemakaian_bahan_bakar_batubara_kg", "sum"), coal_kcal=("coal_kcal", "sum"),
        bio_kg=("pemakaian_biomassa_kg", "sum"), bio_kcal=("bio_kcal", "sum"),
        plan_gross_kwh=("rencana_produksi_kwh", "sum"), plan_net_kwh=("rencana_penjualan_kwh", "sum"),
        plan_coal_kg=("rencana_pemakaian_batubara_kg", "sum"),
    )
    g["eaf"] = g["eah"] / g["ph"]
    g["efor"] = (g["foh"] + g["efdh"]) / (g["sh"] + g["foh"])
    dmn = pd.Series([dmn_mw[u] if isinstance(dmn_mw, dict) else dmn_mw for u, _ in g.index], index=g.index)
    g["dmn_mw"] = dmn
    g["net_output_factor"] = g["net_kwh"] / (dmn * 1000 * g["eah"])
    g["aux_share"] = 1 - g["net_kwh"] / g["gross_kwh"]
    g["nphr"] = g["fuel_kcal"] / g["net_kwh"]
    g["coal_gcv"] = g["coal_kcal"] / g["coal_kg"]
    g["bio_gcv"] = g["bio_kcal"] / g["bio_kg"]
    g["cofiring_share"] = g["bio_kcal"] / g["fuel_kcal"]
    g["hsd_share"] = 1 - (g["bio_kcal"] + g["coal_kcal"]) / g["fuel_kcal"]
    return g


def monthly_correlations(d: pd.DataFrame, dmn_mw) -> dict:
    f = lambda c: d[c].fillna(0)
    eah = f("ah_availablehours_jam") - f("efdh_equivalentforcedderatinghours_jam") \
        - f("epdh_eqplannedderatinghours_jam") - f("emdh_equivalentmaintenancederatinghours_jam")
    m = pd.DataFrame({
        "unit": d["unit"],
        "net_output_factor": d["kwh_netto_penjualan_kwh"] / (d["unit"].map(dmn_mw) * 1000 * eah),
        "nphr_kcal_kwh": d["pemakaian_batubara,_hsd/bio_solar,_dan_biomassa_kcal"] / d["kwh_netto_penjualan_kwh"],
        "aux_share": 1 - d["kwh_netto_penjualan_kwh"] / d["kwh_produksi_kwh"],
        "cofiring_share": f("pemakaian_biomassa_kg") * f("nilai_kalor_biomassa_kcal/kg")
        / d["pemakaian_batubara,_hsd/bio_solar,_dan_biomassa_kcal"],
    })[eah > 300]  # months with meaningful operation only
    cols = ["net_output_factor", "nphr_kcal_kwh", "aux_share", "cofiring_share"]
    c = sum(g[cols].corr(method="spearman") for _, g in m.groupby("unit")) / m["unit"].nunique()
    pairs = []
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            rho = round(float(c.loc[a, b]) * 20) / 20
            if abs(rho) >= 0.2:
                pairs.append([a, b, rho])
    # make sure the matrix is positive definite (shrink if needed)
    for shrink in np.linspace(1, 0.3, 15):
        mat = np.eye(len(cols))
        for a, b, r in pairs:
            mat[cols.index(a), cols.index(b)] = mat[cols.index(b), cols.index(a)] = r * shrink
        if np.all(np.linalg.eigvalsh(mat) > 1e-6):
            return [[a, b, round(r * shrink, 2)] for a, b, r in pairs]
    return []


# --------------------------------------------------------------------------
EMPIRICAL_MIN_EVENTS = 8     # classes with >= 8 events resample the observed durations


def fit_duration(values: np.ndarray, pooled_sigma: float) -> dict:
    """Hours (or equivalent derated hours) per event.

    >= 8 events : empirical distribution of the observed values.
    <  8 events : lognormal whose mean equals the observed mean; the spread
                  comes from the class itself (>= 3 events) or from the pooled
                  spread of classes of the same impact type.
    """
    v = np.asarray(values, float)
    v = v[v > 0]
    if len(v) >= EMPIRICAL_MIN_EVENTS:
        return {"type": "empirical", "values": [round(float(x), 3) for x in np.sort(v)]}
    sigma = float(np.clip(np.log(v).std(ddof=1), 0.3, 1.5)) if len(v) >= 3 else pooled_sigma
    mean = float(v.mean())
    sd = float(mean * np.sqrt(np.exp(sigma ** 2) - 1))
    cap = float(min(max(3 * v.max(), 2 * mean), 2500))
    return {"type": "lognormal", "mean": round(mean, 3), "sd": round(sd, 3), "max": round(cap, 1)}


def pert_from_years(series: pd.Series, better: str, digits: int) -> dict:
    """Mode = latest year; the best observed year bounds the upside and the
    downside extends half the latest-vs-best gap beyond the latest value."""
    vals = series.sort_index()
    latest = float(vals.iloc[-1])
    best = float(vals.min() if better == "low" else vals.max())
    gap = abs(latest - best)
    if gap < 1e-12:
        gap = float(vals.std(ddof=1)) if len(vals) > 1 else abs(latest) * 0.02
    if better == "low":
        lo, hi = min(best, latest), latest + gap / 2
    else:
        lo, hi = latest - gap / 2, max(best, latest)
    r = lambda x: round(x, digits)
    return {"type": "pert", "min": r(lo), "mode": r(latest), "max": r(hi)}


def classify_inspections(raw: pd.DataFrame) -> dict:
    po = raw[raw["unit_status"] == "PO"].copy()
    po["year"] = po["timestamp_start"].dt.year
    txt = po["root_cause_failure_analysis"].fillna("").str.lower()
    po["serious"] = txt.str.contains("serious|seious")
    return {(u, y): ("serious" if g["serious"].any() else "simple") for (u, y), g in po.groupby(["unit_no", "year"])}


# --------------------------------------------------------------------------
def reconciliation(ev: pd.DataFrame, ann: pd.DataFrame, ref: float) -> pd.DataFrame:
    """Failure log vs monthly KPI data, per unit-year."""
    rows = []
    for (u, y), r in ann.iterrows():
        e = ev[(ev["unit"] == u) & (ev["year"] == y)]
        pairs = [
            ("Forced outage hours", e.loc[e["category"] == "FO", "hours"].sum(), r["foh"] + r["fo_omc"], "FOH + FO OMC"),
            ("Maintenance outage hours", e.loc[e["category"] == "MO", "hours"].sum(), r["moh"], "MOH"),
            ("Forced derating eq. hours", e.loc[e["category"] == "FD", "loss_mwh"].sum() / ref, r["efdh"], "EFDH"),
            ("Maintenance derating eq. hours", e.loc[e["category"] == "MD", "loss_mwh"].sum() / ref, r["emdh"], "EMDH"),
            ("Planned derating eq. hours", e.loc[e["category"] == "PD", "loss_mwh"].sum() / ref, r["epdh"], "EPDH"),
        ]
        for item, log, kpi, kpi_name in pairs:
            rows.append({"unit": u, "year": y, "item": item, "failure_log": log, "production_data": kpi,
                         "production_field": kpi_name, "difference": log - kpi})
    return pd.DataFrame(rows)


# price column -> (config key, production column that weights each month)
PRICE_FIELDS = {
    "bpp_rp_kwh": ("energy_value_rp_kwh", "kwh_netto_penjualan_kwh"),
    "coal_price_rp_per_ton": ("coal_price_rp_t", "pemakaian_bahan_bakar_batubara_kg"),
    "biomass_price_rp_per_ton": ("biomass_price_rp_t", "pemakaian_biomassa_kg"),
}


def load_pricing(src) -> pd.DataFrame:
    """Monthly prices per unit: month, coal_price_rp_per_ton, biomass_price_rp_per_ton, bpp_rp_kwh, unit_name."""
    b = pd.read_excel(_src(src))
    missing = missing_columns(b, PRICING_COLUMNS)
    if missing:
        raise ValueError("Pricing file is missing columns: " + ", ".join(missing))
    b["month"] = pd.to_datetime(b["month"])
    for c in PRICE_FIELDS:
        b[c] = pd.to_numeric(b[c], errors="coerce")
    b["unit_name"] = b["unit_name"].astype(str).str.strip()
    return b.dropna(subset=["month"])


def prices_from_pricing(prod: pd.DataFrame, pricing: pd.DataFrame, year: int):
    """Match prices to the production months (unit + calendar month) and weight each month by the quantity the
    price applies to: BPP by net sales, coal price by coal burned, biomass price by biomass burned.

    Returns ({unit: {config key: value for `year`}}, {config key: plant value for `year`}, monthly table, annual table).
    """
    weights = [w for _, w in PRICE_FIELDS.values()]
    p = prod[["end_of_month", "unit", "year"] + weights].copy()
    p["period"] = p["end_of_month"].dt.to_period("M")
    b = pricing.assign(period=pricing["month"].dt.to_period("M"))[["period", "unit_name"] + list(PRICE_FIELDS)]
    m = p.merge(b, left_on=["period", "unit"], right_on=["period", "unit_name"], how="left").drop(columns="unit_name")
    for w in weights:
        m[w] = m[w].fillna(0).clip(lower=0)
    m["period"] = m["period"].astype(str)

    def wavg(g, col):
        g = g[g[col].notna()]
        w = g[PRICE_FIELDS[col][1]].sum()
        if w > 0:
            return float((g[col] * g[PRICE_FIELDS[col][1]]).sum() / w)
        return float(g[col].mean()) if len(g) else float("nan")

    annual = pd.DataFrame([
        {"unit": u, "year": y, "months_matched": int(g["bpp_rp_kwh"].notna().sum()), "months_in_production": len(g),
         **{f"{c}_weighted": wavg(g, c) for c in PRICE_FIELDS}}
        for (u, y), g in m.groupby(["unit", "year"])])
    latest = m[m["year"] == year]
    per_unit = {u: {key: round(wavg(g, c), 2) for c, (key, _) in PRICE_FIELDS.items() if g[c].notna().any()}
                for u, g in latest.groupby("unit")}
    plant = {key: round(wavg(latest, c), 2) for c, (key, _) in PRICE_FIELDS.items() if latest[c].notna().any()}
    return per_unit, plant, m, annual


def build(failure_src, production_src, forecast_year, mapping=None, dmn_mw=None, pricing_src=None):
    """Calibrate the model. Sources may be paths, file objects or bytes."""
    mapping = mapping if mapping is not None else load_mapping(failure_src)
    prod = load_production(production_src)
    dmn = dmn_mw or detect_dmn(prod)
    raw_probe = read_failure(failure_src)
    ref = detect_derate_reference(raw_probe)
    ev, raw = load_events(failure_src, mapping, ref)
    ev = ev[ev["unit"].isin(prod["unit"].unique())]
    ann = annual_stats(prod, dmn)

    exposure = float(prod.groupby("unit").size().sum() / 12)       # unit-years
    units = sorted(prod["unit"].unique())
    period_hours = 8784 if (forecast_year % 4 == 0) else 8760

    insp_all = classify_inspections(raw)
    # ---- event classes -------------------------------------------------------
    pooled_sigma = {}
    for itype, g in ev.groupby("impact_type"):
        s = [np.log(x[x > 0]).std(ddof=1) for _, x in g.groupby("event_class")["eq_hours"] if (x > 0).sum() >= 3]
        pooled_sigma[itype] = float(np.clip(np.mean(s) if s else 1.0, 0.5, 1.5))
    classes, evidence = {}, []
    for cls, g in ev.groupby("event_class"):
        cat, itype = g["category"].iloc[0], g["impact_type"].iloc[0]
        group = cls[len(cat) + 1:]
        k = len(g)
        impact_key = "outage_hours" if itype == "outage" else "derate_eq_hours"
        dur = fit_duration(g["eq_hours"].values, pooled_sigma[itype])
        occurrence = {"type": "poisson",
                      "rate": {"type": "gamma", "shape": round(k + 0.5, 3), "scale": round(1 / exposure, 6)}}
        if cat == "SE":
            # extensions belong to planned outages: probability per inspection type (Jeffreys estimate)
            occurrence = {"type": "bernoulli", "probability_by_inspection": {}}
            for t in ("simple", "serious"):
                n_t = sum(1 for v in insp_all.values() if v == t)
                k_t = sum(1 for (u, y), v in insp_all.items() if v == t and ((g["unit"] == u) & (g["year"] == y)).any())
                occurrence["probability_by_inspection"][t] = round((k_t + 0.5) / (n_t + 1), 3)
        classes[cls] = {
            "category": cat,
            "description": f"{CAT_LABEL.get(cat, cat)} - {GROUP_LABEL.get(group, group)}",
            "occurrence": occurrence,
            "rate_multiplier": 1.0,
            "impacts": {impact_key: dur},
        }
        evidence.append({
            "event_class": cls, "category": cat, "impact": impact_key, "description": classes[cls]["description"],
            "events": k, "exposure_unit_years": exposure,
            "rate_per_unit_year": (k + 0.5) / exposure if cat != "SE" else np.nan,
            "occurrence_model": ("Poisson, rate ~ Gamma(k+0.5, 1/T)" if cat != "SE"
                                 else f"Bernoulli by inspection type {occurrence['probability_by_inspection']}"),
            **{f"{u} events": int((g["unit"] == u).sum()) for u in sorted(ev["unit"].unique())},
            "mean_hours_or_eq_hours": g["eq_hours"].mean(), "median": g["eq_hours"].median(),
            "max": g["eq_hours"].max(), "total_loss_mwh": g["loss_mwh"].sum(),
            "duration_model": dur["type"],
            "fitted_mean": dur.get("mean", float(np.mean(dur.get("values", [np.nan])))),
            "fitted_sd": dur.get("sd", np.nan), "cap": dur.get("max", np.nan),
        })
    evidence = pd.DataFrame(evidence).sort_values("total_loss_mwh", ascending=False)

    # ---- planned outage (excluding extensions, which are an event class) -------
    insp = classify_inspections(raw)
    se_hours = ev[ev["category"] == "SE"].groupby(["unit", "year"])["hours"].sum()
    po_rows = []
    for (u, y), r in ann.iterrows():
        planned = r["poh"] - se_hours.get((u, y), 0.0)
        po_rows.append({"unit": u, "year": y, "inspection_type": insp.get((u, y), "none"),
                        "POH_reported": r["poh"], "extension_hours": se_hours.get((u, y), 0.0), "planned_hours_model": planned})
    po_df = pd.DataFrame(po_rows)
    po_specs = {}
    for t, g in po_df.groupby("inspection_type"):
        v = np.sort(g["planned_hours_model"].values)
        mode = float(np.median(v)) if len(v) >= 3 else float(v.mean())
        po_specs[t] = {"type": "triangular", "min": round(float(v.min()), 1), "mode": round(mode, 1), "max": round(float(v.max()), 1)}

    # next inspection type from each unit's cycle (serious every 3 years in the data)
    unit_cfg, cont_rows = {}, []
    corr = monthly_correlations(prod, dmn)
    for u in units:
        a = ann.loc[u]
        hist = {y: insp.get((u, y), "none") for y in a.index}
        serious_years = [y for y, t in hist.items() if t == "serious"]
        nxt = "serious" if serious_years and (forecast_year - max(serious_years)) % 3 == 0 else "simple"
        spec = {
            "nphr_kcal_kwh": pert_from_years(a["nphr"], "low", 1),
            "net_output_factor": pert_from_years(a["net_output_factor"], "high", 4),
            "aux_share": pert_from_years(a["aux_share"], "low", 4),
            "cofiring_share": {"type": "pert", "min": round(float(a["cofiring_share"].min()), 4),
                               "mode": round(float(a["cofiring_share"].iloc[-1]), 4),
                               "max": round(float(a["cofiring_share"].max()), 4)},
        }
        latest = a.index.max()
        unit_cfg[u] = {
            "dmn_mw": float(dmn[u]),
            "inspection_type": nxt,
            "planned_outage_hours": po_specs.get(nxt, po_specs.get("simple")),
            "biomass_gcv_kcal_kg": round(float(a["bio_kcal"].sum() / a["bio_kg"].sum()), 1),
            "hsd_share": round(float(1 - (a["bio_kcal"].sum() + a["coal_kcal"].sum()) / a["fuel_kcal"].sum()), 5),
            "uncertainties": spec,
            "correlations": corr,
            "targets": {
                "eaf_min": 0.85,
                "efor_max": 0.05,
                "gross_production_min_gwh": round(float(a.loc[latest, "plan_gross_kwh"]) / 1e6, 2),
                "net_production_min_gwh": round(float(a.loc[latest, "plan_net_kwh"]) / 1e6, 2),
                "coal_max_kt": round(float(a.loc[latest, "plan_coal_kg"]) / 1e6, 2),
            },
        }
        for var, s in spec.items():
            cont_rows.append({"unit": u, "variable": var, **{str(y): float(v) for y, v in a[
                {"nphr_kcal_kwh": "nphr", "net_output_factor": "net_output_factor",
                 "aux_share": "aux_share", "cofiring_share": "cofiring_share"}[var]].items()},
                "fitted": f"{s['type']}({s['min']}, {s['mode']}, {s['max']})"})

    # coal GCV is common to both units (same supply)
    mg = prod.dropna(subset=["nilai_kalor_batubara_kcal/kg"])
    gcv_mean = float((mg["pemakaian_bahan_bakar_batubara_kg"] * mg["nilai_kalor_batubara_kcal/kg"]).sum()
                     / mg["pemakaian_bahan_bakar_batubara_kg"].sum())
    gcv_sd = float(mg["nilai_kalor_batubara_kcal/kg"].std())

    cfg = {
        "name": f"{' & '.join(units)} - calibrated risk model",
        "forecast_year": forecast_year,
        "period_hours": period_hours,
        "simulation": {"iterations": 20000, "seed": 42},
        "constants": {"derate_reference_mw": ref, "emission_factor_coal_tco2_tj": 96.1},
        "shared_uncertainties": {"coal_gcv_kcal_kg": {"type": "normal", "mean": round(gcv_mean, 1), "sd": round(gcv_sd, 1)}},
        "economics": {
            "_note": "PLACEHOLDER prices - replace with actual contract values",
            "coal_price_rp_t": 950000, "biomass_price_rp_t": 750000, "energy_value_rp_kwh": 1200,
        },
        "event_classes": classes,
        "planned_outage_specs": po_specs,
        "units": unit_cfg,
        "scenarios": {},
    }
    # ---- prices from the monthly pricing file (latest data year) ----------------
    price_tables = {}
    if pricing_src is not None:
        price_year = int(prod["year"].max())
        per_unit, plant_prices, price_monthly, price_annual = prices_from_pricing(prod, load_pricing(pricing_src), price_year)
        if plant_prices:
            eco = cfg["economics"]
            eco.update(plant_prices)
            eco["_note"] = (f"Prices from the pricing file, {price_year}: coal weighted by coal burned, biomass by biomass "
                            "burned, BPP (value of lost energy) by net sales. Plant values here; per-unit values under units.<unit>")
            eco["price_source"] = f"Pricing {price_year}, quantity weighted"
            for u, vals in per_unit.items():
                unit_cfg[u].update(vals)
        price_tables = {"prices_annual": price_annual, "prices_monthly": price_monthly}
    # ---- scenarios (treatments / opportunities) --------------------------------
    sc = cfg["scenarios"]
    if "serious" in po_specs:
        u0 = next((u for u in units if unit_cfg[u]["inspection_type"] != "serious"), None)
        if u0:
            sc[f"Serious inspection at {u0}"] = {
                "description": f"{u0} performs a serious inspection in the forecast year",
                "overrides": {f"units.{u0}.planned_outage_hours": po_specs["serious"],
                              f"units.{u0}.inspection_type": "serious"}}
    tube = [c for c in classes if c.endswith("tube_leak")]
    if tube:
        sc["Tube leaks -50%"] = {"description": "Tube-leak prevention (thickness survey, erosion shields) halves tube-leak frequency",
                                 "overrides": {f"event_classes.{c}.rate_multiplier": 0.5 for c in tube}}
    coal = [c for c in classes if c.endswith("coal_feeding")]
    if coal:
        sc["Coal feeding -50%"] = {"description": "Coal handling / feeder reliability programme halves coal-feeding deratings",
                                   "overrides": {f"event_classes.{c}.rate_multiplier": 0.5 for c in coal}}
    gen = [c for c in classes if c.endswith("generator_exciter")]
    if gen:
        sc["Generator/exciter -50%"] = {"description": "AVR/exciter reliability fix halves generator-side trips",
                                        "overrides": {f"event_classes.{c}.rate_multiplier": 0.5 for c in gen}}
    hr = {}
    for u in units:
        best = float(ann.loc[u, "nphr"].min())
        s = unit_cfg[u]["uncertainties"]["nphr_kcal_kwh"]
        hr[f"units.{u}.uncertainties.nphr_kcal_kwh"] = {"type": "pert", "min": round(best * 0.99, 1),
                                                         "mode": round(best, 1), "max": s["mode"]}
    sc["Heat rate recovery"] = {"description": "Net plant heat rate brought back to each unit's best observed year",
                                "overrides": hr}
    sc["Co-firing 10%"] = {"description": "Biomass share held at 8-12% of heat input on both units",
                           "overrides": {f"units.{u}.uncertainties.cofiring_share":
                                         {"type": "pert", "min": 0.08, "mode": 0.10, "max": 0.12} for u in units}}

    # ---- evidence tables -------------------------------------------------------
    fo_fail = ev[ev["category"] == "FO"].groupby(["unit", "year"])["hours"].sum()
    ann_out = ann.copy()
    ann_out["FO_hours_failure_log"] = [fo_fail.get(i, 0.0) for i in ann.index]
    ann_out["FO_OMC_in_log"] = (ann_out["FO_hours_failure_log"] - ann_out["foh"]).clip(lower=0)
    ann_out["eaf_incl_omc"] = ann_out["eaf"] - ann_out["FO_OMC_in_log"] / ann_out["ph"]
    ann_out["inspection_type"] = [insp.get(i, "none") for i in ann.index]
    evid = {
        "event_classes": evidence,
        "events_merged": ev.drop(columns=["system"]),
        "annual_stats": ann_out.reset_index(),
        "continuous_fits": pd.DataFrame(cont_rows),
        "planned_outage": po_df,
        "correlations": pd.DataFrame(corr, columns=["variable_a", "variable_b", "rho"]),
        "status_mapping_used": pd.DataFrame(sorted(mapping.items()), columns=["status_code", "category"]),
        "reconciliation": reconciliation(ev, ann, ref),
        **price_tables,
    }
    return cfg, evid


def _plain(o):
    """Convert numpy scalars to plain Python for YAML."""
    if isinstance(o, dict):
        return {k: _plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_plain(v) for v in o]
    if isinstance(o, np.generic):
        return o.item()
    return o


def main():
    ap = argparse.ArgumentParser(description="Calibrate the risk model from plant data")
    ap.add_argument("--failure", default="data/Failure_Data_highlighted.xlsx")
    ap.add_argument("--production", default="data/Data_Pengusahaan.xlsx")
    ap.add_argument("--pricing", default="data/Pricing.xlsx",
                    help="monthly coal / biomass price and BPP per unit; placeholders are used if the file is missing")
    ap.add_argument("--forecast-year", type=int, default=2026)
    ap.add_argument("--out", default="config")
    args = ap.parse_args()

    pricing = args.pricing if args.pricing and Path(args.pricing).exists() else None
    cfg, evid = build(args.failure, args.production, args.forecast_year, pricing_src=pricing)
    out = Path(args.out)
    out.mkdir(exist_ok=True)
    header = ("# Generated by calibrate.py from plant data. Edit values as needed, then run: python run.py\n"
              "# Targets eaf_min / efor_max are PLACEHOLDERS - set your own. Prices come from the pricing file when given.\n")
    (out / "model_config.yaml").write_text(header + yaml.safe_dump(_plain(cfg), sort_keys=False, allow_unicode=True,
                                                                     width=120), encoding="utf-8")
    with pd.ExcelWriter(out / "calibration_evidence.xlsx", engine="openpyxl") as xw:
        for name, t in evid.items():
            t.to_excel(xw, sheet_name=name[:31], index=False)
    ev = evid["events_merged"]
    print(f"Events: {int(ev['source_rows'].sum())} log rows merged into {len(ev)} events, "
          f"{ev['event_class'].nunique()} event classes")
    eco = cfg["economics"]
    src = eco.get("price_source", "PLACEHOLDERS - no pricing file")
    print(f"Prices ({src}): coal {eco['coal_price_rp_t']:,.0f} Rp/t, biomass {eco['biomass_price_rp_t']:,.0f} Rp/t, "
          f"lost energy {eco['energy_value_rp_kwh']:,.2f} Rp/kWh")
    print(f"Written: {out / 'model_config.yaml'} and {out / 'calibration_evidence.xlsx'}")


if __name__ == "__main__":
    main()
