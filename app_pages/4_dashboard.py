import streamlit as st

from app_lib import charts, state, ui

ui.need("results")
cfg, r = state.get("run_cfg"), state.get("results")
res, units = r["res"], list(cfg["units"])

st.title(f"Dashboard {cfg['forecast_year']}")
scope = st.segmented_control("Scope", ["Plant"] + units, default="Plant", label_visibility="collapsed") or "Plant"
d = res[scope]

if scope == "Plant":
    plan_gross = sum(cfg["units"][u]["targets"]["gross_production_min_gwh"] for u in units)
    plan_coal = sum(cfg["units"][u]["targets"]["coal_max_kt"] for u in units)
    eaf_t, efor_t = [cfg["units"][units[0]]["targets"][k] * 100 for k in ("eaf_min", "efor_max")]
else:
    t = cfg["units"][scope]["targets"]
    plan_gross, plan_coal, eaf_t, efor_t = t["gross_production_min_gwh"], t["coal_max_kt"], t["eaf_min"] * 100, t["efor_max"] * 100


def window(name, x, unit, target, higher=True, digits=1):
    p = (x >= target).mean() if higher else (x <= target).mean()
    return {"name": name, "value": f"{x.mean():,.{digits}f} {unit}",
            "range": f"P10 {x.quantile(.1):,.{digits}f}  -  P90 {x.quantile(.9):,.{digits}f}", "prob": p,
            "signal": f"{p:.0%} chance of {'reaching' if higher else 'staying within'} {target:,.{digits}f}"}


ui.annunciator([
    window("Equivalent availability (EAF)", d["eaf_pct"], "%", eaf_t),
    window("Equivalent forced outage rate", d["efor_pct"], "%", efor_t, higher=False),
    window("Gross production", d["gross_gwh"], "GWh", plan_gross, digits=0),
    window("Coal consumption", d["coal_kt"], "kt", plan_coal, higher=False, digits=0),
    {"name": "Energy lost to unplanned events", "value": f"{d['lost_net_gwh'].mean():,.0f} GWh",
     "range": f"P90 {d['lost_net_gwh'].quantile(.9):,.0f} GWh", "prob": None, "signal": "Net energy, expected"},
])
st.caption("Window colour: green 70% or more chance of meeting the target, amber 40-70%, red below 40%. "
           "EAF and EFOR targets are placeholders until set on the Build model page.")

t1, t2, t3, t4 = st.tabs(["Outcomes", "Risks", "Drivers", "Scenarios"])
with t1:
    a, b = st.columns(2)
    a.plotly_chart(charts.histogram(d["gross_gwh"], "GWh", "Gross production", plan_gross, "Plan"), width="stretch")
    b.plotly_chart(charts.histogram(d["eaf_pct"], "EAF (%)", "Equivalent availability factor", eaf_t, "Target"),
                   width="stretch")
    a, b = st.columns(2)
    a.plotly_chart(charts.scurve(d["net_gwh"], "GWh", "Net production (S-curve)",
                                 sum(cfg["units"][u]["targets"]["net_production_min_gwh"] for u in units) if scope == "Plant"
                                 else cfg["units"][scope]["targets"]["net_production_min_gwh"], "Net sales plan"),
                   width="stretch")
    b.plotly_chart(charts.histogram(d["coal_kt"], "kt", "Coal consumption", plan_coal, "Coal plan", higher_is_better=False),
                   width="stretch")
    st.plotly_chart(charts.outage_breakdown(res, units), width="stretch")
    with st.expander("All metrics"):
        s = r["summary"]
        st.dataframe(s[s["Scope"] == scope].drop(columns="Scope"), hide_index=True, width="stretch")

with t2:
    reg = r["register"]
    a, b = st.columns([1.05, 1])
    a.plotly_chart(charts.risk_matrix(reg), width="stretch")
    b.plotly_chart(charts.pareto(reg), width="stretch")
    st.subheader("Risk register (plant)")
    view = reg.copy()
    view["Risk score"] = view["Likelihood score (1-5)"] * view["Consequence score (1-5)"]
    view["Rating"] = view["Risk score"].map(lambda s: "Extreme" if s >= 15 else "High" if s >= 10 else "Medium" if s >= 5 else "Low")
    cols = ["Rank", "Event class", "Description", "Events per year (plant)", "Mean eq. hours per event",
            "Expected net energy loss (GWh/yr)", "Expected EAF impact (pp, plant)", "Effect on P10 plant production (GWh)",
            "Share of expected event loss", "Risk score", "Rating"]
    st.dataframe(view[cols], hide_index=True, width="stretch", height=440,
                 column_config={"Share of expected event loss": st.column_config.ProgressColumn(format="%.2f", min_value=0, max_value=1),
                                "Events per year (plant)": st.column_config.NumberColumn(format="%.2f"),
                                "Mean eq. hours per event": st.column_config.NumberColumn(format="%.1f"),
                                "Expected net energy loss (GWh/yr)": st.column_config.NumberColumn(format="%.2f"),
                                "Expected EAF impact (pp, plant)": st.column_config.NumberColumn(format="%.2f"),
                                "Effect on P10 plant production (GWh)": st.column_config.NumberColumn(format="%.2f")})
    st.caption("Rating = likelihood x consequence: 1-4 Low, 5-9 Medium, 10-14 High, 15-25 Extreme. "
               "The ranking itself follows the expected annual energy loss.")

with t3:
    desc = {k: v["description"] for k, v in cfg["event_classes"].items()}
    sp, scl = r["sens_prod"].copy(), r["sens_coal"].copy()
    sp["Driver"] = sp["Driver"].map(lambda x: ui.driver_label(x, desc))
    scl["Driver"] = scl["Driver"].map(lambda x: ui.driver_label(x, desc))
    st.plotly_chart(charts.bridge(r["bridge"]), width="stretch")
    a, b = st.columns(2)
    a.plotly_chart(charts.tornado(sp, "Drivers of plant net production"), width="stretch")
    b.plotly_chart(charts.tornado(scl, "Drivers of plant coal consumption"), width="stretch")

with t4:
    if r["scen_res"]:
        metric = st.radio("Compare", ["Net production (GWh)", "Coal consumption (kt)", "EAF (%)"], horizontal=True)
        col = {"Net production (GWh)": "net_gwh", "Coal consumption (kt)": "coal_kt", "EAF (%)": "eaf_pct"}[metric]
        st.plotly_chart(charts.scenarios(r["scen_res"], col, metric), width="stretch")
        st.dataframe(r["scenarios"], hide_index=True, width="stretch")
    else:
        st.info("Run the simulation with scenarios switched on to compare treatments and opportunities.")
