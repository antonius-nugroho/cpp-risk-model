import io

import pandas as pd
import streamlit as st

from app_lib import state, ui

ui.need("results")
cfg, r, ev = state.get("run_cfg"), state.get("results"), state.get("evidence")
res, units, reg = r["res"], list(cfg["units"]), r["register"]
p = res["Plant"]
fy = cfg["forecast_year"]
T = lambda k: sum(cfg["units"][u]["targets"][k] for u in units)

st.title(f"Model resume {fy}")
ui.lede(f"{cfg['name']}. {r['n']:,} simulated years per unit, calibrated on "
        f"{int(ev['event_classes']['exposure_unit_years'].iloc[0]):g} unit-years of failure and production data.")

plan_gross, plan_net, plan_coal = T("gross_production_min_gwh"), T("net_production_min_gwh"), T("coal_max_kt")
p_gross = (p["gross_gwh"] >= plan_gross).mean()
p_net = (p["net_gwh"] >= plan_net).mean()
p_coal = (p["coal_kt"] <= plan_coal).mean()
eaf_t = cfg["units"][units[0]]["targets"]["eaf_min"] * 100

ui.annunciator([
    {"name": "Plant EAF", "value": f"{p['eaf_pct'].mean():.1f} %", "range": f"P10 {p['eaf_pct'].quantile(.1):.1f}  -  P90 {p['eaf_pct'].quantile(.9):.1f}",
     "prob": (p["eaf_pct"] >= eaf_t).mean(), "signal": f"{(p['eaf_pct'] >= eaf_t).mean():.0%} chance of {eaf_t:.0f}%"},
    {"name": "Gross production", "value": f"{p['gross_gwh'].mean():,.0f} GWh", "range": f"Plan {plan_gross:,.0f} GWh",
     "prob": p_gross, "signal": f"{p_gross:.0%} chance of reaching plan"},
    {"name": "Net sales", "value": f"{p['net_gwh'].mean():,.0f} GWh", "range": f"Plan {plan_net:,.0f} GWh",
     "prob": p_net, "signal": f"{p_net:.0%} chance of reaching plan"},
    {"name": "Coal", "value": f"{p['coal_kt'].mean():,.0f} kt", "range": f"Plan {plan_coal:,.0f} kt",
     "prob": p_coal, "signal": f"{p_coal:.0%} chance of staying within plan"},
])

st.markdown('<div class="resume">', unsafe_allow_html=True)

# ---- outlook ------------------------------------------------------------------
st.header("Outlook")
plan = r["plan"]["Plant"]
gap = plan["net_gwh"].iloc[0] - p["net_gwh"].mean()
unit_lines = "; ".join(f"{u} {res[u]['eaf_pct'].mean():.1f}% EAF and {res[u]['gross_gwh'].mean():,.0f} GWh gross" for u in units)
st.markdown(
    f"In {fy} the plant is expected to reach an EAF of **{p['eaf_pct'].mean():.1f}%** "
    f"(P10 {p['eaf_pct'].quantile(.1):.1f}% to P90 {p['eaf_pct'].quantile(.9):.1f}%) and to produce "
    f"**{p['gross_gwh'].mean():,.0f} GWh** gross, with a {p_gross:.0%} chance of reaching the plan of {plan_gross:,.0f} GWh. "
    f"Net sales reach their plan in {p_net:.0%} of simulated years. By unit: {unit_lines}.")
st.markdown(
    f"A plan that assumes no disruptions would give {plan['net_gwh'].iloc[0]:,.0f} GWh net. The expected outcome is "
    f"{gap:,.0f} GWh lower: {p['lost_net_gwh'].mean():,.0f} GWh is lost to unplanned outages and deratings, and the rest to "
    f"planned outages running longer than their most likely duration and to plant performance uncertainty.")

# ---- risks --------------------------------------------------------------------
st.header("Main risks")
lines = []
for _, x in reg.head(3).iterrows():
    lines.append(f"- **{x['Description']}** ({x['Event class']}): about {x['Events per year (plant)']:.1f} events a year, "
                 f"{x['Mean eq. hours per event']:.0f} equivalent hours each, costing {x['Expected net energy loss (GWh/yr)']:.1f} GWh "
                 f"and {x['Expected EAF impact (pp, plant)']:.2f} EAF points a year on average "
                 f"({x['Share of expected event loss']:.0%} of the unplanned loss).")
st.markdown("\n".join(lines))
top_share = reg["Share of expected event loss"].head(3).sum()
st.markdown(f"These three classes account for {top_share:.0%} of the expected unplanned energy loss. "
            f"The main uncertainty drivers of plant production are: "
            + "; ".join(ui.driver_label(x, {k: v["description"] for k, v in cfg["event_classes"].items()}).lower()
                        for x in r["sens_prod"]["Driver"].head(4)) + ".")

# ---- opportunities ------------------------------------------------------------
sc = r["scenarios"]
if not sc.empty:
    st.header("Opportunities and treatments")
    s = sc[sc["Scenario"] != "Base"].copy()
    out = []
    for _, x in s.sort_values("Delta mean net GWh vs base", ascending=False).iterrows():
        parts = []
        if abs(x["Delta mean net GWh vs base"]) >= 0.5:
            parts.append(f"{x['Delta mean net GWh vs base']:+,.1f} GWh net on average ({x['Delta P10 net GWh vs base']:+,.1f} GWh in a bad year)")
        if abs(x["Delta coal (kt) vs base"]) >= 0.5:
            parts.append(f"{x['Delta coal (kt) vs base']:+,.1f} kt coal")
        if parts:
            out.append(f"- **{x['Scenario']}** - {x['Description']}: " + "; ".join(parts) + ".")
    st.markdown("\n".join(out) if out else "No scenario changes the results materially.")

# ---- validation ---------------------------------------------------------------
st.header("Validation")
bt = r["backtest"]
rec = ev["reconciliation"].groupby("item")[["failure_log", "production_data"]].sum()
fd = rec.loc["Forced derating eq. hours"]
if not bt.empty:
    inside = int(bt["Inside P10-P90"].sum())
    st.markdown(f"Replaying the historical unit-years with their actual planned outages, {inside} of {len(bt)} actual EAF and "
                f"EFOR values fall inside the model's P10-P90 band (about 80% is expected for a well-calibrated model). "
                f"This is an in-sample check.")
st.markdown(f"The failure log agrees with the monthly KPI data: forced derating equals {fd['failure_log']:,.0f} equivalent hours "
            f"in the log against {fd['production_data']:,.0f} hours of EFDH ({fd['failure_log'] / fd['production_data'] - 1:+.0%}).")

# ---- method -------------------------------------------------------------------
st.header("How the model works")
events = ev["events_merged"]
st.markdown(
    f"- {int(events['source_rows'].sum()):,} log rows were merged into {len(events):,} events and grouped into "
    f"{len(cfg['event_classes'])} classes by status and failure mode.\n"
    "- Each class has a Poisson frequency pooled over the units, with the uncertainty of the rate itself included, "
    "and a duration distribution taken from the observed events.\n"
    "- Planned outage hours follow the inspection type; heat rate, net output factor, auxiliary share and co-firing "
    "share are centred on the latest year.\n"
    "- EAF, EFOR, production, coal, biomass and CO2 are calculated for every simulated year.")

st.header("Assumptions to confirm")
st.markdown(
    f"- EAF target {eaf_t:.0f}% and EFOR limit {cfg['units'][units[0]]['targets']['efor_max'] * 100:.0f}% are placeholders.\n"
    f"- Production and coal plans ({plan_gross:,.0f} GWh gross, {plan_coal:,.0f} kt coal) default to the latest plan year in the data.\n"
    "- Coal and biomass prices are placeholders; fuel cost in rupiah is illustrative. Lost energy is valued at BPP.\n"
    "- Inspection type: " + ", ".join(f"{u} {cfg['units'][u]['inspection_type']}" for u in units) + ".")
st.markdown("</div>", unsafe_allow_html=True)

# ---- downloads ----------------------------------------------------------------
st.divider()
st.header("Download")
c1, c2, c3 = st.columns(3)
with c1:
    if st.button("Prepare Excel report", width="stretch"):
        with st.spinner("Writing the workbook and charts..."):
            st.session_state["excel_report"] = state.build_excel_report(cfg, r, ev)
    if state.get("excel_report"):
        st.download_button("Download Excel report", state.get("excel_report"), file_name=f"Risk_Model_Results_{fy}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary",
                           width="stretch")
with c2:
    st.download_button("Download model configuration", state.config_yaml(cfg), file_name="model_config.yaml",
                       mime="text/yaml", width="stretch")
with c3:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, t in ev.items():
            t.to_excel(xw, sheet_name=name[:31], index=False)
    st.download_button("Download calibration evidence", buf.getvalue(), file_name="calibration_evidence.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
