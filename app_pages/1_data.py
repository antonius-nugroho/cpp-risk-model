import pandas as pd
import streamlit as st

from app_lib import state, ui
from app_lib.status_codes import CATEGORIES

st.title("Data")
ui.lede("Upload the failure log and the monthly production data (Data Pengusahaan). "
        "The files are checked here, and you choose which unit statuses count as outages or deratings.")

c1, c2 = st.columns(2)
with c1:
    st.subheader("Failure data")
    st.caption("Excel file with one row per outage or derating (e.g. Failure_Data.xlsx or Failure_Data_highlighted.xlsx).")
    f_up = st.file_uploader("Failure data", type=["xlsx"], key="failure_upload", label_visibility="collapsed")
with c2:
    st.subheader("Data Pengusahaan")
    st.caption("Excel file with one row per unit per month: hours, KPIs, production, fuel and plans.")
    p_up = st.file_uploader("Data Pengusahaan", type=["xlsx"], key="production_upload", label_visibility="collapsed")

with st.expander("BPP (optional) - values the lost energy at the actual cost of generation"):
    st.caption("Excel file with columns month, bpp_rp_kwh, unit_name (one row per unit per month). Months are matched to "
               "Data Pengusahaan and weighted by net sales. Without it, a placeholder energy price is used.")
    b_up = st.file_uploader("BPP", type=["xlsx"], key="bpp_upload", label_visibility="collapsed")
if b_up is not None and b_up.getvalue() != state.get("bpp_bytes"):
    st.session_state["bpp_bytes"], st.session_state["bpp_name"] = b_up.getvalue(), b_up.name
    state.clear_from("calibration")

if f_up is not None and f_up.getvalue() != state.get("failure_bytes"):
    st.session_state["failure_bytes"], st.session_state["failure_name"] = f_up.getvalue(), f_up.name
    state.clear_from("data")
if p_up is not None and p_up.getvalue() != state.get("production_bytes"):
    st.session_state["production_bytes"], st.session_state["production_name"] = p_up.getvalue(), p_up.name
    state.clear_from("data")

if state.get("failure_bytes") is None or state.get("production_bytes") is None:
    st.divider()
    st.markdown("No files yet? Load the Tarahan Units 3 & 4 data for 2023-2025 that ships with the project.")
    if st.button("Load bundled Tarahan data", type="primary"):
        st.session_state["failure_bytes"] = state.SAMPLE_FAILURE.read_bytes()
        st.session_state["failure_name"] = state.SAMPLE_FAILURE.name
        st.session_state["production_bytes"] = state.SAMPLE_PRODUCTION.read_bytes()
        st.session_state["production_name"] = state.SAMPLE_PRODUCTION.name
        if state.SAMPLE_BPP.exists():
            st.session_state["bpp_bytes"] = state.SAMPLE_BPP.read_bytes()
            st.session_state["bpp_name"] = state.SAMPLE_BPP.name
        state.clear_from("data")
        st.rerun()

fb, pb = state.get("failure_bytes"), state.get("production_bytes")
if fb is None and pb is None:
    st.stop()

st.divider()
st.header("File checks")
ok_f = ok_p = False
c1, c2 = st.columns(2)
with c1:
    if fb is not None:
        info = state.inspect_failure(fb)
        st.markdown(f"**{state.get('failure_name')}**  (sheet: {info['sheet']})")
        if info["missing"]:
            st.error("Missing required columns: " + ", ".join(info["missing"]))
        else:
            ui.checklist(info["checks"])
            ok_f = True
with c2:
    if pb is not None:
        pinfo = state.inspect_production(pb)
        st.markdown(f"**{state.get('production_name')}**")
        if pinfo["missing"]:
            st.error("Missing required columns: " + ", ".join(pinfo["missing"]))
        else:
            ui.checklist(pinfo["checks"])
            ok_p = True

if ok_f or ok_p:
    with st.expander("Preview the data"):
        t1, t2 = st.tabs(["Failure data", "Data Pengusahaan"])
        if ok_f:
            t1.dataframe(info["df"].head(200), width="stretch", height=320)
        if ok_p:
            t2.dataframe(pinfo["df"].head(200), width="stretch", height=320)

if not ok_f:
    st.stop()

st.divider()
st.header("Status mapping")
ui.lede("Tick the statuses to include and set the category each one counts as. "
        "Outage categories (FO, OS, MO, SE) remove available hours; derating categories (FD, MD, PD) remove "
        "equivalent hours based on the MW lost.")
if state.get("mapping_df") is None:
    st.session_state["mapping_df"] = state.mapping_table(fb, info["df"])
edited = st.data_editor(
    st.session_state["mapping_df"], width="stretch", hide_index=True, height=420, key="mapping_editor",
    disabled=["Status", "Meaning", "Records"],
    column_config={
        "Include": st.column_config.CheckboxColumn("Include", help="Count this status in the model"),
        "Category": st.column_config.SelectboxColumn("Category", options=CATEGORIES + [""]),
        "Records": st.column_config.NumberColumn("Records in file", format="%d"),
    })
bad = edited[edited["Include"] & ~edited["Category"].isin(CATEGORIES)]
if not bad.empty:
    st.warning("Give these included statuses a category: " + ", ".join(bad["Status"]))
included = edited[edited["Include"] & edited["Category"].isin(CATEGORIES)]
st.caption(f"{int(included['Records'].sum()):,} records in {len(included)} statuses will be modelled.")

if not edited.equals(st.session_state["mapping_df"]):
    st.session_state["mapping_df"] = edited
    state.clear_from("calibration")

if ok_p and not included.empty:
    st.page_link("app_pages/2_build.py", label="Continue to Build model", icon=":material/arrow_forward:")
