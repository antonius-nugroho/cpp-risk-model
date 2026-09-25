import copy
import datetime as dt

import pandas as pd
import streamlit as st

from app_lib import state, ui
from app_lib.status_codes import CATEGORIES

st.title("Build model")
ui.lede("Calibrate the model from the uploaded data, adjust the forecast assumptions, then run the Monte Carlo simulation.")
ui.need("data")

mapping_df = state.get("mapping_df")
if mapping_df is None:
    mapping_df = state.mapping_table(state.get("failure_bytes"), state.inspect_failure(state.get("failure_bytes"))["df"])
    st.session_state["mapping_df"] = mapping_df
inc = mapping_df[mapping_df["Include"] & mapping_df["Category"].isin(CATEGORIES)]
mapping_items = tuple(sorted(zip(inc["Status"], inc["Category"])))

# ---------------------------------------------------------------------------
st.header("Calibrate")
c1, c2 = st.columns([1, 3])
with c1:
    last_year = int(state.inspect_production(state.get("production_bytes"))["df"]["end_of_month"].pipe(pd.to_datetime).dt.year.max())
    fy = st.number_input("Forecast year", min_value=2000, max_value=2100, step=1,
                         value=int(state.get("forecast_year", last_year + 1)),
                         help="Defaults to the year after the last month in Data Pengusahaan")
with c2:
    st.write("")
    st.write("")
    go = st.button("Calibrate model", type="primary", disabled=not mapping_items)
if not mapping_items:
    st.warning("No statuses are included. Choose at least one on the Data page.")

if go or (state.get("cfg") is not None and state.get("forecast_year") != fy):
    with st.spinner("Merging events, fitting frequencies and durations..."):
        try:
            cfg, ev = state.calibrate_cached(state.get("failure_bytes"), state.get("production_bytes"), int(fy), mapping_items,
                                            state.get("bpp_bytes"))
        except Exception as exc:  # show the reason, keep the app alive
            st.error(f"Calibration failed: {exc}")
            st.stop()
    st.session_state.update(cfg=cfg, evidence=ev, forecast_year=fy)
    state.clear_from("results")
    for k in [k for k in st.session_state if k.startswith("w_")]:
        del st.session_state[k]

cfg, ev = state.get("cfg"), state.get("evidence")
if cfg is None:
    st.stop()

events = ev["events_merged"]
ui.checklist([
    ("Log rows merged into events", f"{int(events['source_rows'].sum()):,} rows -> {len(events):,} events", "ok"),
    ("Event classes", f"{ev['event_classes'].shape[0]}", "ok"),
    ("Exposure", f"{ev['event_classes']['exposure_unit_years'].iloc[0]:g} unit-years", "ok"),
    ("Units and DMN", ", ".join(f"{u}: {c['dmn_mw']:g} MW" for u, c in cfg["units"].items()), "ok"),
    ("Derating reference (gross MW)", f"{cfg['constants']['derate_reference_mw']:g} MW", "ok"),
])

# ---------------------------------------------------------------------------
st.header("Forecast assumptions")
ui.lede("Values come from the calibration. Change them to test what-if cases; the defaults marked as placeholders "
        "should be replaced with your KPI contract and prices.")
work = copy.deepcopy(cfg)

tabs = st.tabs(list(cfg["units"]) + ["Prices", "Event frequencies", "Scenarios"])
for tab, (u, uc) in zip(tabs, cfg["units"].items()):
    with tab:
        a, b = st.columns(2)
        with a:
            st.markdown("**Planned outage**")
            specs = cfg["planned_outage_specs"]
            types = list(specs)
            itype = st.selectbox("Inspection type", types, index=types.index(uc["inspection_type"]) if uc["inspection_type"] in types else 0,
                                 key=f"w_{u}_insp", help="Suggested from each unit's inspection cycle in the data")
            sp = specs[itype]
            x1, x2, x3 = st.columns(3)
            lo = x1.number_input("Min hours", value=float(sp["min"]), key=f"w_{u}_{itype}_min")
            mo = x2.number_input("Most likely", value=float(sp["mode"]), key=f"w_{u}_{itype}_mode")
            hi = x3.number_input("Max hours", value=float(sp["max"]), key=f"w_{u}_{itype}_max")
            if not lo <= mo <= hi:
                st.error("Planned outage hours need min <= most likely <= max.")
                st.stop()
            work["units"][u]["inspection_type"] = itype
            work["units"][u]["planned_outage_hours"] = {"type": "triangular", "min": lo, "mode": mo, "max": hi}
        with b:
            st.markdown("**Targets**")
            t = uc["targets"]
            y1, y2 = st.columns(2)
            eaf = y1.number_input("EAF target (%) - placeholder", value=t["eaf_min"] * 100, step=0.5, key=f"w_{u}_eaf")
            efor = y2.number_input("EFOR limit (%) - placeholder", value=t["efor_max"] * 100, step=0.5, key=f"w_{u}_efor")
            gross = y1.number_input("Gross production plan (GWh)", value=float(t["gross_production_min_gwh"]), key=f"w_{u}_gross")
            net = y2.number_input("Net sales plan (GWh)", value=float(t["net_production_min_gwh"]), key=f"w_{u}_net")
            coal = y1.number_input("Coal plan (kt)", value=float(t["coal_max_kt"]), key=f"w_{u}_coal")
            st.caption("Production and coal plans default to the latest year in Data Pengusahaan.")
            work["units"][u]["targets"] = {"eaf_min": eaf / 100, "efor_max": efor / 100, "gross_production_min_gwh": gross,
                                           "net_production_min_gwh": net, "coal_max_kt": coal}
        with st.expander("Plant performance distributions (from the annual data)"):
            cf = ev["continuous_fits"]
            st.dataframe(cf[cf["unit"] == u].drop(columns="unit"), hide_index=True, width="stretch")

with tabs[len(cfg["units"])]:
    st.caption("Prices only affect the rupiah figures, not EAF, energy or coal quantities. Coal and biomass prices are placeholders.")
    e = cfg["economics"]
    p1, p2, p3 = st.columns(3)
    work["economics"]["coal_price_rp_t"] = p1.number_input("Coal price (Rp/t)", value=float(e["coal_price_rp_t"]), step=10000.0, key="w_coal_price")
    work["economics"]["biomass_price_rp_t"] = p2.number_input("Biomass price (Rp/t)", value=float(e["biomass_price_rp_t"]), step=10000.0, key="w_bio_price")
    per_unit = {u: uc["energy_value_rp_kwh"] for u, uc in cfg["units"].items() if "energy_value_rp_kwh" in uc}
    if per_unit:
        st.markdown(f"**Value of lost energy (Rp/kWh)** - {e.get('energy_value_source', 'BPP')}")
        for col, (u, v) in zip(st.columns(len(per_unit)), per_unit.items()):
            work["units"][u]["energy_value_rp_kwh"] = col.number_input(u, value=float(v), step=10.0, key=f"w_{u}_energy_value")
    else:
        work["economics"]["energy_value_rp_kwh"] = p3.number_input("Value of lost energy (Rp/kWh) - placeholder", value=float(e["energy_value_rp_kwh"]),
                                                                   step=10.0, key="w_energy_value",
                                                                   help="Upload BPP on the Data page to use the actual cost of generation")

with tabs[len(cfg["units"]) + 1]:
    st.caption("Frequencies are pooled over all units. A multiplier of 0.5 halves the frequency of a class; 1.5 raises it by half.")
    ec = ev["event_classes"].set_index("event_class")
    tbl = pd.DataFrame({
        "Event class": list(cfg["event_classes"]),
        "Description": [c["description"] for c in cfg["event_classes"].values()],
        "Events in data": [int(ec.loc[k, "events"]) for k in cfg["event_classes"]],
        "Mean hours per event": [float(ec.loc[k, "mean_hours_or_eq_hours"]) for k in cfg["event_classes"]],
        "Frequency multiplier": [float(c.get("rate_multiplier", 1.0)) for c in cfg["event_classes"].values()],
    })
    ed = st.data_editor(tbl, hide_index=True, width="stretch", key="w_multipliers", height=420,
                        disabled=["Event class", "Description", "Events in data", "Mean hours per event"],
                        column_config={"Frequency multiplier": st.column_config.NumberColumn(min_value=0.0, max_value=5.0, step=0.1),
                                       "Mean hours per event": st.column_config.NumberColumn(format="%.1f")})
    for _, r in ed.iterrows():
        work["event_classes"][r["Event class"]]["rate_multiplier"] = float(r["Frequency multiplier"])

with tabs[len(cfg["units"]) + 2]:
    names = list(cfg.get("scenarios", {}))
    chosen = st.multiselect("Scenarios to compare with the base case", names, default=names, key="w_scen")
    for nm in names:
        st.markdown(f"**{nm}**: {cfg['scenarios'][nm]['description']}")
    work["scenarios"] = {k: v for k, v in cfg.get("scenarios", {}).items() if k in chosen}

# ---------------------------------------------------------------------------
st.header("Run simulation")
r1, r2, r3, r4 = st.columns([1, 1, 1, 1.4])
n = r1.select_slider("Iterations", options=[2000, 5000, 10000, 20000], value=10000, key="w_n")
seed = r2.number_input("Random seed", value=42, step=1, key="w_seed")
do_bt = r3.checkbox("Backtest", value=True, help="Replays 2023-2025 to validate the model", key="w_bt")
do_sc = r3.checkbox("Scenarios", value=True, key="w_sc")
with r4:
    st.write("")
    run = st.button("Run simulation", type="primary", width="stretch")

if run:
    with st.spinner(f"Simulating {n:,} years per unit..."):
        ev_key = str(hash(tuple(ev["events_merged"]["hours"].round(4))))
        res = state.simulate_cached(state.config_yaml(work), int(n), int(seed), do_bt, do_sc, ev, ev_key)
    st.session_state.update(results=res, run_cfg=work)
    st.session_state.pop("excel_report", None)
    st.success("Simulation finished. Open the dashboard, the validation or the resume.")

if state.get("results") is not None:
    c1, c2, c3 = st.columns(3)
    c1.page_link("app_pages/3_validation.py", label="Model validation", icon=":material/fact_check:")
    c2.page_link("app_pages/4_dashboard.py", label="Dashboard", icon=":material/monitoring:")
    c3.page_link("app_pages/5_resume.py", label="Model resume", icon=":material/summarize:")
    if state.get("run_cfg") != work:
        st.warning("Assumptions changed since the last run. Run the simulation again to update the results.")

st.download_button("Download model configuration (YAML)", state.config_yaml(work), file_name="model_config.yaml",
                   mime="text/yaml")
