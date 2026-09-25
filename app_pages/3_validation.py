import streamlit as st

from app_lib import charts, state, ui

st.title("Model validation")
ui.lede("Three checks: does the failure log agree with the monthly KPI data, does the model reproduce past years, "
        "and what evidence stands behind each calibrated number.")
ui.need("calibration")
cfg, ev, res = state.get("cfg"), state.get("evidence"), state.get("results")

# ---------------------------------------------------------------------------
st.header("Backtest against past years")
if res is None or res["backtest"].empty:
    st.info("Run the simulation with the backtest option on the Build model page to see this check.")
    st.page_link("app_pages/2_build.py", label="Go to Build model", icon=":material/arrow_forward:")
else:
    bt = res["backtest"]
    inside, total = int(bt["Inside P10-P90"].sum()), len(bt)
    eaf_bt = bt[bt["Metric"] == "EAF (%)"]
    mae = (eaf_bt["Actual"] - eaf_bt["P50"]).abs().mean()
    ui.annunciator([
        {"name": "Actual values inside the P10-P90 band", "value": f"{inside} of {total}",
         "range": "A well-calibrated model puts about 80% inside", "prob": None,
         "cls": "green" if 0.6 <= inside / total <= 0.95 else "amber",
         "signal": f"{inside / total:.0%} coverage"},
        {"name": "Mean absolute EAF error (P50 vs actual)", "value": f"{mae:.1f} pp",
         "range": "Across all unit-years", "prob": None, "signal": ""},
        {"name": "Unit-years replayed", "value": f"{len(eaf_bt)}",
         "range": "Actual planned outage and inspection type used", "prob": None, "signal": ""},
    ])
    metric = st.radio("Metric", ["EAF (%)", "EFOR (%)"], horizontal=True, label_visibility="collapsed")
    st.plotly_chart(charts.backtest(bt, metric), width="stretch")
    st.caption("Each past year is replayed with its actual planned outage hours and inspection type. The actual EAF "
               "includes forced outage hours that the KPI classes as outside management control, so it can sit "
               "slightly below the reported KPI. This is an in-sample check: frequencies were estimated from the same years.")
    with st.expander("Backtest table"):
        st.dataframe(bt, hide_index=True, width="stretch",
                     column_config={"Percentile of actual": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=1)})

# ---------------------------------------------------------------------------
st.header("Failure log against the KPI data")
rec = ev["reconciliation"]
st.plotly_chart(charts.reconciliation(rec), width="stretch")
g = rec.groupby("item")[["failure_log", "production_data"]].sum()
g["difference %"] = (g["failure_log"] / g["production_data"] - 1) * 100
st.dataframe(g.round(1), width="stretch")
st.caption("Derating hours in the log are loss MWh divided by the derating reference "
           f"({cfg['constants']['derate_reference_mw']:g} MW). Forced outage differences usually come from statuses "
           "excluded in the mapping, such as FO.SYS, which the KPI data records as outside management control.")
with st.expander("By unit and year"):
    st.dataframe(rec, hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
st.header("Calibration evidence")
t1, t2, t3, t4 = st.tabs(["Event classes", "Plant performance", "Planned outage", "Merged events"])
with t1:
    st.caption("Frequency: Poisson per unit-year pooled over units, with rate uncertainty Gamma(k + 0.5, 1/unit-years). "
               "Duration: empirical for classes with 8 or more events, otherwise a lognormal matched to the observed mean.")
    st.dataframe(ev["event_classes"], hide_index=True, width="stretch", height=460)
with t2:
    cf = ev["continuous_fits"]
    labels = {"nphr_kcal_kwh": "Net plant heat rate (kcal/kWh)", "net_output_factor": "Net output factor",
              "aux_share": "Auxiliary power + transformer losses (share of gross)", "cofiring_share": "Biomass share of heat input"}
    for var, lab in labels.items():
        if var in set(cf["variable"]):
            st.plotly_chart(charts.continuous_fit(cf, var, lab), width="stretch")
    st.caption("The most likely value is the latest year. The best observed year bounds the upside and the downside "
               "extends half the latest-to-best gap beyond the latest value.")
    st.markdown("**Correlations (from the monthly data)**")
    st.dataframe(ev["correlations"], hide_index=True)
with t3:
    st.dataframe(ev["planned_outage"], hide_index=True, width="stretch")
    st.json(cfg["planned_outage_specs"], expanded=False)
with t4:
    st.dataframe(ev["events_merged"], hide_index=True, width="stretch", height=460)

st.header("Known limits")
st.markdown(
    "- Frequencies are pooled over units, so both units share the same event rates. Use the frequency multipliers "
    "on the Build model page to reflect differences.\n"
    "- Plant performance trends are carried forward from the latest year; a multi-year forecast would need an explicit trend.\n"
    "- Starts and biodiesel use are not modelled (about 0.2% of heat input).\n"
    "- EAF and EFOR targets and the coal and biomass prices are placeholders until you enter your own values.")
