"""Session state and cached computations for the Streamlit app."""
from __future__ import annotations

import copy
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

import calibrate as cal
from app_lib.i18n import month, t
import reporting as rp
from model import simulate_plant

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SAMPLE_FAILURE = DATA_DIR / "Failure_Data_highlighted.xlsx"
SAMPLE_PRODUCTION = DATA_DIR / "Data_Pengusahaan.xlsx"
SAMPLE_PRICING = DATA_DIR / "Pricing.xlsx"


# --------------------------------------------------------------------------
# Session helpers
# --------------------------------------------------------------------------
def get(key, default=None):
    return st.session_state.get(key, default)


def clear_from(stage: str):
    """Invalidate everything downstream of a stage: data -> calibration -> results."""
    order = ["data", "calibration", "results"]
    keys = {"data": ["mapping_df"], "calibration": ["cfg", "evidence"], "results": ["results", "run_cfg", "excel_report"]}
    for s in order[order.index(stage):]:
        for k in keys[s]:
            st.session_state.pop(k, None)


def status() -> dict:
    return {
        "data": get("failure_bytes") is not None and get("production_bytes") is not None,
        "calibration": get("cfg") is not None,
        "results": get("results") is not None,
    }


# --------------------------------------------------------------------------
# Data inspection
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def template_bytes(kind: str) -> bytes:
    from app_lib.templates import TEMPLATES
    return TEMPLATES[kind][1]()


def pricing_missing_columns(b: bytes) -> list[str]:
    try:
        return cal.missing_columns(pd.read_excel(cal._src(b), nrows=0), cal.PRICING_COLUMNS)
    except Exception:
        return list(cal.PRICING_COLUMNS)


@st.cache_data(show_spinner=False)
def preview_pricing(b: bytes) -> pd.DataFrame:
    """The pricing file as the model reads it (required columns first, sorted by unit and month)."""
    d = cal.load_pricing(b)
    extra = [c for c in d.columns if c not in cal.PRICING_COLUMNS]
    return d[cal.PRICING_COLUMNS + extra].sort_values(["unit_name", "month"]).reset_index(drop=True)


@st.cache_data(show_spinner=False)
def inspect_failure(b: bytes) -> dict:
    sheet = cal.failure_sheet(b)
    df = cal.read_failure(b)
    missing = cal.missing_columns(df, cal.FAILURE_COLUMNS)
    try:
        has_mapping = "Status Mapping" in pd.ExcelFile(cal._src(b)).sheet_names
    except Exception:
        has_mapping = False
    checks = []
    if not missing:
        df["timestamp_start"] = pd.to_datetime(df["timestamp_start"], errors="coerce")
        df["timestamp_stop"] = pd.to_datetime(df["timestamp_stop"], errors="coerce")
        no_status = df["unit_status"].isna()
        neg = df["failure_duration_hours"] < 0
        bad_time = df["timestamp_start"].isna() | df["timestamp_stop"].isna()
        checks = [
            ("Jumlah baris", f"{len(df):,}", "ok"),
            ("Unit", ", ".join(sorted(df["unit_no"].dropna().astype(str).unique())), "ok"),
            ("Periode", f"{month(df['timestamp_start'].min(), day=True)} s.d. {month(df['timestamp_start'].max(), day=True)}", "ok"),
            ("Baris tanpa unit_status", f"{int(no_status.sum())}", "warn" if no_status.any() else "ok"),
            ("Baris dengan durasi negatif", f"{int(neg.sum())}", "warn" if neg.any() else "ok"),
            ("Baris dengan timestamp tidak terbaca", f"{int(bad_time.sum())}", "warn" if bad_time.any() else "ok"),
            ("Sheet Status Mapping", "ditemukan - kolom Include dipakai" if has_mapping else "tidak ditemukan - pemetaan bawaan dipakai",
             "ok" if has_mapping else "info"),
        ]
    return {"df": df, "sheet": sheet, "missing": missing, "checks": checks, "has_mapping": has_mapping,
            "status_counts": df["unit_status"].value_counts(dropna=False) if "unit_status" in df else pd.Series(dtype=int)}


@st.cache_data(show_spinner=False)
def inspect_production(b: bytes) -> dict:
    raw = pd.read_excel(cal._src(b))
    missing = cal.missing_columns(raw, cal.PRODUCTION_COLUMNS)
    checks = []
    if not missing:
        d = cal.load_production(b)
        dash = int((raw == "-").sum().sum())
        months = d.groupby("unit")["end_of_month"].agg(["count", "min", "max"])
        dmn = cal.detect_dmn(d)
        checks = [("Jumlah baris bulanan", f"{len(d):,}", "ok")]
        for u, r in months.iterrows():
            expected = (r["max"].year - r["min"].year) * 12 + r["max"].month - r["min"].month + 1
            checks.append((f"Bulan {u}", f"{r['count']} ({month(r['min'])} s.d. {month(r['max'])})",
                           "ok" if r["count"] == expected else "warn"))
        checks += [
            ("Daya mampu neto terdeteksi (DMN)", ", ".join(f"{u}: {v:g} MW" for u, v in dmn.items()), "ok"),
            ("Sel berisi '-' (dianggap kosong)", f"{dash}", "info" if dash else "ok"),
        ]
        key = ["kwh_netto_penjualan_kwh", "nilai_kalor_batubara_kcal/kg", "pemakaian_batubara,_hsd/bio_solar,_dan_biomassa_kcal"]
        gaps = int(d[key].isna().sum().sum())
        checks.append(("Nilai kosong di kolom produksi / bahan bakar", f"{gaps}", "warn" if gaps else "ok"))
    preview = raw.replace("-", pd.NA)
    for c in preview.columns:
        if preview[c].dtype == object and c not in ("unit",):
            conv = pd.to_numeric(preview[c], errors="coerce")
            if conv.notna().sum() >= preview[c].notna().sum() * 0.9:
                preview[c] = conv
    return {"df": preview, "missing": missing, "checks": checks}


def mapping_table(b: bytes, failure_df: pd.DataFrame) -> pd.DataFrame:
    from app_lib.status_codes import STATUS_CODES, default_category
    from_file = cal.load_mapping(b)
    present = set(failure_df["unit_status"].dropna().astype(str).str.strip())
    codes = list(STATUS_CODES) + sorted(present - set(STATUS_CODES))
    counts = failure_df["unit_status"].value_counts()
    rows = []
    for c in codes:
        rows.append({"Status": c, "Meaning": t(STATUS_CODES.get(c, ("Not in status list", ""))[0]),
                     "Records": int(counts.get(c, 0)),
                     "Category": from_file.get(c, default_category(c)),
                     "Include": c in from_file})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def calibrate_cached(failure_b: bytes, production_b: bytes, forecast_year: int, mapping_items: tuple, pricing_b: bytes | None = None):
    return cal.build(failure_b, production_b, forecast_year, mapping=dict(mapping_items), pricing_src=pricing_b)


@st.cache_data(show_spinner=False, max_entries=4)
def simulate_cached(cfg_yaml: str, n: int, seed: int, run_backtest: bool, run_scenarios: bool, _evidence, evidence_key: str):
    cfg = yaml.safe_load(cfg_yaml)
    res = simulate_plant(cfg, n, seed)
    plan = simulate_plant(cfg, 1, seed, plan=True)
    out = {
        "res": res, "plan": plan,
        "summary": rp.summary_table(res, plan),
        "targets": rp.target_table(cfg, res),
        "register": rp.risk_register(cfg, res),
        "bridge": rp.loss_bridge(cfg, res, plan),
        "sens_prod": rp.sensitivity(res, "net_gwh"),
        "sens_coal": rp.sensitivity(res, "coal_kt"),
        "backtest": rp.backtest(cfg, _evidence, n, seed) if run_backtest else pd.DataFrame(),
        "n": n, "seed": seed,
    }
    if run_scenarios and cfg.get("scenarios"):
        out["scenarios"], out["scen_res"] = rp.scenarios(cfg, n, seed, res, simulate_plant)
    else:
        out["scenarios"], out["scen_res"] = pd.DataFrame(), {}
    return out


def build_excel_report(cfg: dict, results: dict, evidence: dict) -> bytes:
    import run as cli  # uses the same workbook writer as the command-line tool
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        res, reg = results["res"], results["register"]
        charts = [rp.chart_distributions(cfg, res, tmp), rp.chart_risk_matrix(reg, tmp), rp.chart_pareto(reg, tmp),
                  rp.chart_bridge(results["bridge"], tmp),
                  rp.chart_tornado(results["sens_prod"], tmp, "Drivers of plant net production", "05_tornado.png")]
        if not results["backtest"].empty:
            charts.append(rp.chart_backtest(results["backtest"], tmp))
        if results["scen_res"]:
            charts.append(rp.chart_scenarios(results["scen_res"], tmp))
        path = tmp / "Risk_Model_Results.xlsx"
        cli.write_workbook(path, cfg, results["n"], results["seed"], results["summary"], results["targets"], reg,
                           results["bridge"], results["sens_prod"], results["sens_coal"], results["backtest"],
                           results["scenarios"], evidence, charts)
        return path.read_bytes()


def config_yaml(cfg: dict) -> str:
    return yaml.safe_dump(cal._plain(copy.deepcopy(cfg)), sort_keys=False, allow_unicode=True, width=120)
