"""Tables and charts for the calibrated risk model."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from model import apply_overrides, simulate_unit

METRICS = [
    ("eaf_pct", "EAF (%)"), ("efor_pct", "EFOR (%)"),
    ("gross_gwh", "Gross production (GWh)"), ("net_gwh", "Net production / sales (GWh)"),
    ("lost_net_gwh", "Net energy lost to unplanned events (GWh)"),
    ("poh_h", "Planned outage (h)"), ("foh_h", "Forced outage (h)"), ("moh_h", "Maintenance outage (h)"),
    ("seh_h", "Outage extension (h)"), ("efdh_h", "EFDH (h)"), ("emdh_h", "EMDH (h)"), ("epdh_h", "EPDH (h)"),
    ("nphr_kcal_kwh", "Net plant heat rate (kcal/kWh)"), ("coal_kt", "Coal consumption (kt)"),
    ("biomass_kt", "Biomass consumption (kt)"), ("co2_kt", "CO2 from coal (kt)"),
    ("fuel_cost_rp_bn", "Fuel cost (Rp bn)"),
    ("lost_energy_value_rp_bn", "Value of lost energy (Rp bn) - at BPP"),
]
RED, GREEN, GREY, BLUE, ORANGE = "#c0392b", "#27ae60", "#7f8c8d", "#2980b9", "#e67e22"
LIKELIHOOD_BANDS = [0.2, 0.5, 1.0, 3.0]          # plant events per year -> score 1..5
CONSEQUENCE_BANDS = [200, 1000, 5000, 15000]     # net MWh lost per event -> score 1..5


def _score(x, bands):
    return int(np.searchsorted(bands, x, side="right") + 1)


# --------------------------------------------------------------------------
def summary_table(res, plan):
    rows = []
    for scope, df in res.items():
        for col, label in METRICS:
            x = df[col]
            rows.append({"Scope": scope, "Metric": label, "Plan (deterministic)": plan[scope][col].iloc[0],
                         "Mean": x.mean(), "P10": x.quantile(.1), "P50": x.median(), "P90": x.quantile(.9),
                         "Std dev": x.std()})
    return pd.DataFrame(rows)


def target_table(cfg, res):
    rows = []
    tot = {"gross_production_min_gwh": 0, "net_production_min_gwh": 0, "coal_max_kt": 0}
    for u, uc in cfg["units"].items():
        t, d = uc["targets"], res[u]
        for k in tot:
            tot[k] += t[k]
        rows += [
            (u, f"EAF >= {t['eaf_min']:.0%}  (placeholder)", (d["eaf_pct"] >= t["eaf_min"] * 100).mean()),
            (u, f"EFOR <= {t['efor_max']:.0%}  (placeholder)", (d["efor_pct"] <= t["efor_max"] * 100).mean()),
            (u, f"Gross production >= plan {t['gross_production_min_gwh']:,.1f} GWh",
             (d["gross_gwh"] >= t["gross_production_min_gwh"]).mean()),
            (u, f"Net sales >= plan {t['net_production_min_gwh']:,.1f} GWh",
             (d["net_gwh"] >= t["net_production_min_gwh"]).mean()),
            (u, f"Coal <= plan {t['coal_max_kt']:,.1f} kt", (d["coal_kt"] <= t["coal_max_kt"]).mean()),
        ]
    p = res["Plant"]
    rows += [
        ("Plant", f"Gross production >= plan {tot['gross_production_min_gwh']:,.1f} GWh",
         (p["gross_gwh"] >= tot["gross_production_min_gwh"]).mean()),
        ("Plant", f"Net sales >= plan {tot['net_production_min_gwh']:,.1f} GWh",
         (p["net_gwh"] >= tot["net_production_min_gwh"]).mean()),
        ("Plant", f"Coal <= plan {tot['coal_max_kt']:,.1f} kt", (p["coal_kt"] <= tot["coal_max_kt"]).mean()),
    ]
    return pd.DataFrame(rows, columns=["Scope", "Target", "Probability of meeting"])


def risk_register(cfg, res):
    """Plant-level register from the additive per-class decomposition."""
    p = res["Plant"]
    ph = float(cfg["period_hours"])
    n_units = len(cfg["units"])
    p10 = p["net_gwh"].quantile(.1)
    total_event_loss = sum(p[f"gwh:{c}"].mean() for c in cfg["event_classes"])
    rows = []
    for name, ev in cfg["event_classes"].items():
        n, h, g = p[f"n:{name}"], p[f"h:{name}"], p[f"gwh:{name}"]
        freq = n.mean()
        per_event_mwh = (g.sum() / n.sum() * 1000) if n.sum() > 0 else 0.0
        per_event_h = (h.sum() / n.sum()) if n.sum() > 0 else 0.0
        rows.append({
            "Event class": name, "Category": ev["category"], "Description": ev["description"],
            "Events per year (plant)": freq, "P(at least one per year)": (n > 0).mean(),
            "Mean eq. hours per event": per_event_h, "Mean net MWh lost per event": per_event_mwh,
            "Expected eq. hours per year (plant)": h.mean(),
            "Expected EAF impact (pp, plant)": h.mean() / (ph * n_units) * 100,
            "Expected net energy loss (GWh/yr)": g.mean(),
            "P90 annual loss from this class (GWh)": g.quantile(.9),
            "Effect on P10 plant production (GWh)": (p["net_gwh"] + g).quantile(.1) - p10,
            "Share of expected event loss": g.mean() / total_event_loss if total_event_loss else 0,
            "Likelihood score (1-5)": _score(freq, LIKELIHOOD_BANDS),
            "Consequence score (1-5)": _score(per_event_mwh, CONSEQUENCE_BANDS),
        })
    df = pd.DataFrame(rows).sort_values("Expected net energy loss (GWh/yr)", ascending=False).reset_index(drop=True)
    df.insert(0, "Rank", np.arange(1, len(df) + 1))
    return df


def loss_bridge(cfg, res, plan):
    """Plan -> expected net production, decomposed (plant)."""
    p, pl = res["Plant"], plan["Plant"]
    cats = {}
    for name, ev in cfg["event_classes"].items():
        cats[ev["category"]] = cats.get(ev["category"], 0) + p[f"gwh:{name}"].mean()
    planned_extra = p["gwh:planned_outage"].mean() - pl["gwh:planned_outage"].iloc[0]
    items = [("Plan (deterministic)", pl["net_gwh"].iloc[0]),
             ("Planned outage longer than mode", -planned_extra)]
    labels = {"FO": "Forced outages", "MO": "Maintenance outages", "SE": "Outage extensions", "OS": "Outage slips",
              "FD": "Forced deratings", "MD": "Maintenance deratings", "PD": "Planned deratings"}
    for c in ["FO", "MO", "SE", "OS", "FD", "MD", "PD"]:
        if c in cats:
            items.append((labels[c], -cats[c]))
    resid = p["net_gwh"].mean() - sum(v for _, v in items)
    items.append(("Output factor & other uncertainty", resid))
    items.append(("Expected (mean)", p["net_gwh"].mean()))
    return pd.DataFrame(items, columns=["Step", "Net production (GWh)"])


def sensitivity(res, target="net_gwh", scope="Plant", top=15):
    d = res[scope]
    cols = [c for c in d.columns if c.startswith(("in:", "n:")) and d[c].std() > 0]
    rho = d[cols + [target]].corr(method="spearman")[target].drop(target)
    out = pd.DataFrame({"Driver": [c.replace("in:", "").replace("n:", "events: ") for c in rho.index],
                        "Rank correlation": rho.values})
    out["Contribution to variance"] = out["Rank correlation"] ** 2 / (out["Rank correlation"] ** 2).sum()
    return out.reindex(out["Rank correlation"].abs().sort_values(ascending=False).index).head(top).reset_index(drop=True)


def backtest(cfg, evidence, n, seed):
    """Replay each historical unit-year with its actual planned outage hours and
    inspection type; compare actual EAF/EFOR with the simulated band.
    In-sample check: the event rates were estimated from the same years."""
    ann, po = evidence["annual_stats"], evidence["planned_outage"]
    rows = []
    for _, r in ann.iterrows():
        u, y = r["unit"], int(r["year"])
        prow = po[(po["unit"] == u) & (po["year"] == y)].iloc[0]
        c = apply_overrides(cfg, {f"units.{u}.planned_outage_hours": {"type": "constant", "value": float(prow["planned_hours_model"])},
                                  f"units.{u}.inspection_type": prow["inspection_type"],
                                  "period_hours": float(r["ph"])})
        d = simulate_unit(c, u, n, seed + y)
        for metric, col, actual in [("EAF (%)", "eaf_pct", r["eaf_incl_omc"] * 100),
                                    ("EFOR (%)", "efor_pct", r["efor"] * 100)]:
            x = d[col]
            rows.append({"Unit": u, "Year": y, "Inspection": prow["inspection_type"], "Metric": metric,
                         "Actual": actual, "Reported KPI": r["eaf"] * 100 if col == "eaf_pct" else r["efor"] * 100,
                         "P10": x.quantile(.1), "P50": x.median(), "P90": x.quantile(.9),
                         "Percentile of actual": (x <= actual).mean(),
                         "Inside P10-P90": bool(x.quantile(.1) <= actual <= x.quantile(.9))})
    return pd.DataFrame(rows)


def scenarios(cfg, n, seed, base_res, simulate_plant):
    keep = ["eaf_pct", "net_gwh", "gross_gwh", "coal_kt", "co2_kt", "nphr_kcal_kwh", "fuel_cost_rp_bn"]
    rows, results = [], {"Base": base_res["Plant"][keep]}
    for name, sc in (cfg.get("scenarios") or {}).items():
        results[name] = simulate_plant(apply_overrides(cfg, sc["overrides"]), n, seed)["Plant"][keep]
    b = results["Base"]
    plan_gross = sum(u["targets"]["gross_production_min_gwh"] for u in cfg["units"].values())
    for name, d in results.items():
        rows.append({
            "Scenario": name, "Description": (cfg.get("scenarios", {}).get(name) or {}).get("description", "Calibrated forecast"),
            "Mean EAF (%)": d["eaf_pct"].mean(), "Mean net GWh": d["net_gwh"].mean(),
            "P10 net GWh": d["net_gwh"].quantile(.1), "P90 net GWh": d["net_gwh"].quantile(.9),
            "Delta mean net GWh vs base": d["net_gwh"].mean() - b["net_gwh"].mean(),
            "Delta P10 net GWh vs base": d["net_gwh"].quantile(.1) - b["net_gwh"].quantile(.1),
            "P(gross >= plan)": (d["gross_gwh"] >= plan_gross).mean(),
            "Mean NPHR (kcal/kWh)": d["nphr_kcal_kwh"].mean(), "Mean coal (kt)": d["coal_kt"].mean(),
            "Mean CO2 (kt)": d["co2_kt"].mean(),
            "Delta coal (kt) vs base": d["coal_kt"].mean() - b["coal_kt"].mean(),
        })
    return pd.DataFrame(rows), results


# --------------------------------------------------------------------------
# Charts
# --------------------------------------------------------------------------
def _save(fig, out_dir, name):
    fig.tight_layout()
    path = Path(out_dir) / name
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def chart_distributions(cfg, res, out_dir):
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    p = res["Plant"]
    plan = sum(u["targets"]["gross_production_min_gwh"] for u in cfg["units"].values())
    ax = axes[0]
    ax.hist(p["gross_gwh"], bins=80, color=BLUE, alpha=.75)
    ax.axvline(plan, color=RED, lw=2, label=f"Plan {plan:,.0f} GWh  P(meet) = {(p['gross_gwh'] >= plan).mean():.0%}")
    for q, ls in [(.1, ":"), (.5, "--"), (.9, ":")]:
        ax.axvline(p["gross_gwh"].quantile(q), color="k", ls=ls, lw=1)
    ax.set_title("Plant gross production (dotted = P10/P90, dashed = P50)")
    ax.set_xlabel("GWh")
    ax.legend(fontsize=8)
    ax = axes[1]
    for u, c in zip(cfg["units"], [BLUE, ORANGE]):
        ax.hist(res[u]["eaf_pct"], bins=80, alpha=.55, color=c, label=f"{u} (mean {res[u]['eaf_pct'].mean():.1f}%)")
    t = next(iter(cfg["units"].values()))["targets"]["eaf_min"] * 100
    ax.axvline(t, color=RED, lw=2, label=f"EAF target {t:.0f}% (placeholder)")
    ax.set_title("Unit EAF distribution")
    ax.set_xlabel("EAF (%)")
    ax.legend(fontsize=8)
    return _save(fig, out_dir, "01_production_and_eaf.png")


def chart_risk_matrix(reg, out_dir):
    fig, ax = plt.subplots(figsize=(9, 7.5))
    colors = np.array([[1, 2, 3, 4, 5]]).T @ np.array([[1, 2, 3, 4, 5]])
    # same bands as the register rating: 1-4 Low, 5-9 Medium, 10-14 High, 15-25 Extreme
    cmap = plt.matplotlib.colors.ListedColormap(["#c6e0b4", "#ffeb84", "#f8a870", "#f8696b"])
    norm = plt.matplotlib.colors.BoundaryNorm([0, 4.5, 9.5, 14.5, 26], 4)
    ax.imshow(colors, origin="lower", cmap=cmap, norm=norm, extent=[.5, 5.5, .5, 5.5], alpha=.8)
    rng = np.random.default_rng(1)
    for (lk, cq), grp in reg.groupby(["Likelihood score (1-5)", "Consequence score (1-5)"]):
        k = len(grp)
        for i, (_, r) in enumerate(grp.iterrows()):
            dx = (i % 2 - .5) * .45 if k > 1 else 0
            dy = ((i // 2) - (k - 1) / 4) * .22 if k > 1 else 0
            ax.scatter(cq + dx * .5, lk + dy, s=40 + 400 * r["Share of expected event loss"], color="k", zorder=3)
            ax.annotate(f"{r['Rank']}", (cq + dx * .5, lk + dy), xytext=(5, 3), textcoords="offset points", fontsize=8)
    ax.set_xticks(range(1, 6), ["<0.2", "0.2-1", "1-5", "5-15", ">15"])
    ax.set_yticks(range(1, 6), ["<0.2", "0.2-0.5", "0.5-1", "1-3", ">3"])
    ax.set_xlabel("Consequence: net GWh lost per event")
    ax.set_ylabel("Likelihood: events per year (plant)")
    ax.set_title("Risk matrix (numbers = rank in the risk register; dot size = share of expected loss)")
    return _save(fig, out_dir, "02_risk_matrix.png")


def chart_pareto(reg, out_dir, top=12):
    r = reg.head(top)
    fig, ax = plt.subplots(figsize=(11, 5))
    colors = [RED if c in ("FO", "FD") else ORANGE if c in ("MO", "MD", "SE") else GREY for c in r["Category"]]
    ax.bar(r["Event class"], r["Expected net energy loss (GWh/yr)"], color=colors)
    ax.set_ylabel("Expected net energy loss (GWh/yr, plant)")
    ax2 = ax.twinx()
    ax2.plot(r["Event class"], reg["Share of expected event loss"].cumsum().head(top) * 100, color="k", marker="o")
    ax2.set_ylabel("Cumulative share (%)")
    ax2.set_ylim(0, 105)
    ax.set_xticks(range(len(r)), r["Event class"], rotation=40, ha="right", fontsize=8)
    ax.set_title("Pareto of unplanned-event losses (red = forced, orange = maintenance/extension)")
    return _save(fig, out_dir, "03_pareto_event_losses.png")


def chart_bridge(bridge, out_dir):
    fig, ax = plt.subplots(figsize=(11, 5))
    vals = bridge["Net production (GWh)"].tolist()
    labels = bridge["Step"].tolist()
    run = 0
    for i, (lab, v) in enumerate(zip(labels, vals)):
        if i in (0, len(vals) - 1):
            ax.bar(i, v, color=GREY)
            ax.text(i, v, f"{v:,.0f}", ha="center", va="bottom", fontsize=8)
            run = v if i == 0 else run
            continue
        ax.bar(i, v, bottom=run, color=GREEN if v >= 0 else RED)
        ax.text(i, run + v, f"{v:+,.1f}", ha="center", va="bottom" if v >= 0 else "top", fontsize=8)
        run += v
    lo = min(np.cumsum(vals[:-1]).min(), vals[-1]) * .95
    ax.set_ylim(lo, vals[0] * 1.02)
    ax.set_xticks(range(len(labels)), labels, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Plant net production (GWh)")
    ax.set_title("Bridge: deterministic plan -> expected net production")
    return _save(fig, out_dir, "04_production_bridge.png")


def chart_tornado(sens, out_dir, title, name):
    s = sens.iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, .42 * len(s) + 1.5))
    ax.barh(s["Driver"], s["Rank correlation"], color=[GREEN if v > 0 else RED for v in s["Rank correlation"]])
    ax.axvline(0, color="k", lw=.8)
    ax.set_xlabel("Spearman rank correlation")
    ax.set_title(title)
    ax.tick_params(axis="y", labelsize=8)
    return _save(fig, out_dir, name)


def chart_backtest(bt, out_dir):
    b = bt[bt["Metric"] == "EAF (%)"].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(10, 4.8))
    x = np.arange(len(b))
    ax.vlines(x, b["P10"], b["P90"], color=BLUE, lw=8, alpha=.4, label="Simulated P10-P90")
    ax.scatter(x, b["P50"], color=BLUE, marker="_", s=300, label="Simulated P50")
    ax.scatter(x, b["Actual"], color=RED, zorder=3, label="Actual EAF (incl. OMC outages)")
    ax.scatter(x, b["Reported KPI"], color="k", marker="x", zorder=3, label="Reported EAF KPI")
    ax.set_xticks(x, [f"{u}\n{y}\n({t})" for u, y, t in zip(b["Unit"], b["Year"], b["Inspection"])], fontsize=8)
    ax.set_ylabel("EAF (%)")
    ax.set_title("Backtest: actual EAF vs model band (given actual planned outage)")
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=4)
    return _save(fig, out_dir, "06_backtest_eaf.png")


def chart_scenarios(results, out_dir):
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.boxplot([d["net_gwh"].values for d in results.values()], whis=(10, 90), showfliers=False, showmeans=True)
    ax.set_xticks(range(1, len(results) + 1), list(results), rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("Plant net production (GWh)")
    ax.set_title("Scenarios (box = P25-P75, whiskers = P10-P90, triangle = mean)")
    ax.grid(axis="y", alpha=.3)
    return _save(fig, out_dir, "07_scenarios.png")
