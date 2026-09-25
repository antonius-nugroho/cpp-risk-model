import streamlit as st

from app_lib import state, ui
from app_lib.status_codes import CATEGORIES
from app_lib.templates import TEMPLATES

st.title("Data")
ui.lede("Unggah log gangguan dan data produksi bulanan (Data Pengusahaan). "
        "File diperiksa di sini, lalu Anda memilih status unit mana yang dihitung sebagai outage atau derating. "
        "Memakai data sendiri? Unduh template, isi, lalu unggah.")


def template_button(kind: str):
    name = TEMPLATES[kind][0]
    st.download_button("Unduh template", state.template_bytes(kind), file_name=name, icon=":material/download:",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"tpl_{kind}",
                       help="Workbook kosong dengan kolom yang diperlukan; sheet Columns menjelaskan setiap kolom")


c1, c2 = st.columns(2)
with c1:
    st.subheader("Data gangguan")
    st.caption("File Excel dengan satu baris per outage atau derating (mis. Failure_Data.xlsx atau Failure_Data_highlighted.xlsx).")
    template_button("failure")
    f_up = st.file_uploader("Data gangguan", type=["xlsx"], key="failure_upload", label_visibility="collapsed")
with c2:
    st.subheader("Data Pengusahaan")
    st.caption("File Excel dengan satu baris per unit per bulan: jam operasi, KPI, produksi, bahan bakar dan rencana.")
    template_button("production")
    p_up = st.file_uploader("Data Pengusahaan", type=["xlsx"], key="production_upload", label_visibility="collapsed")

with st.expander("BPP (opsional) - menilai energi yang hilang dengan biaya pokok produksi aktual"):
    st.caption("File Excel dengan kolom month, bpp_rp_kwh, unit_name (satu baris per unit per bulan). Bulan dicocokkan "
               "dengan Data Pengusahaan dan dibobot dengan penjualan neto. Tanpa file ini, dipakai harga energi sementara.")
    template_button("bpp")
    b_up = st.file_uploader("BPP", type=["xlsx"], key="bpp_upload", label_visibility="collapsed")
    if b_up is not None and b_up.getvalue() != state.get("bpp_bytes"):
        bpp_missing = state.bpp_missing_columns(b_up.getvalue())
        if bpp_missing:
            st.error("File BPP tidak memiliki kolom wajib: " + ", ".join(bpp_missing))
        else:
            st.session_state["bpp_bytes"], st.session_state["bpp_name"] = b_up.getvalue(), b_up.name
            state.clear_from("calibration")
    if state.get("bpp_bytes") is not None:
        st.caption(f"Memakai {state.get('bpp_name')}.")

if f_up is not None and f_up.getvalue() != state.get("failure_bytes"):
    st.session_state["failure_bytes"], st.session_state["failure_name"] = f_up.getvalue(), f_up.name
    state.clear_from("data")
if p_up is not None and p_up.getvalue() != state.get("production_bytes"):
    st.session_state["production_bytes"], st.session_state["production_name"] = p_up.getvalue(), p_up.name
    state.clear_from("data")

missing_upload = state.get("failure_bytes") is None or state.get("production_bytes") is None
if missing_upload and state.SAMPLE_FAILURE.exists() and state.SAMPLE_PRODUCTION.exists():
    st.divider()
    st.markdown("Belum punya file? Muat data PLTU Tarahan Unit 3 & 4 tahun 2023-2025 yang disertakan dalam proyek.")
    if st.button("Muat data Tarahan bawaan", type="primary"):
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
st.header("Pemeriksaan file")
ok_f = ok_p = False
c1, c2 = st.columns(2)
with c1:
    if fb is not None:
        info = state.inspect_failure(fb)
        st.markdown(f"**{state.get('failure_name')}**  (sheet: {info['sheet']})")
        if info["missing"]:
            st.error("Kolom wajib tidak ada: " + ", ".join(info["missing"]))
        else:
            ui.checklist(info["checks"])
            ok_f = True
with c2:
    if pb is not None:
        pinfo = state.inspect_production(pb)
        st.markdown(f"**{state.get('production_name')}**")
        if pinfo["missing"]:
            st.error("Kolom wajib tidak ada: " + ", ".join(pinfo["missing"]))
        else:
            ui.checklist(pinfo["checks"])
            ok_p = True

if ok_f or ok_p:
    with st.expander("Pratinjau data"):
        t1, t2 = st.tabs(["Data gangguan", "Data Pengusahaan"])
        if ok_f:
            t1.dataframe(info["df"].head(200), width="stretch", height=320)
        if ok_p:
            t2.dataframe(pinfo["df"].head(200), width="stretch", height=320)

if not ok_f:
    st.stop()

st.divider()
st.header("Pemetaan status")
ui.lede("Centang status yang dihitung dan tentukan kategorinya. "
        "Kategori outage (FO, OS, MO, SE) mengurangi jam siap; kategori derating (FD, MD, PD) mengurangi "
        "jam ekuivalen berdasarkan MW yang hilang.")
if state.get("mapping_df") is None:
    st.session_state["mapping_df"] = state.mapping_table(fb, info["df"])
edited = st.data_editor(
    st.session_state["mapping_df"], width="stretch", hide_index=True, height=420, key="mapping_editor",
    disabled=["Status", "Meaning", "Records"],
    column_config={
        "Meaning": st.column_config.TextColumn("Arti"),
        "Include": st.column_config.CheckboxColumn("Dihitung", help="Hitung status ini dalam model"),
        "Category": st.column_config.SelectboxColumn("Kategori", options=CATEGORIES + [""]),
        "Records": st.column_config.NumberColumn("Jumlah baris di file", format="%d"),
    })
bad = edited[edited["Include"] & ~edited["Category"].isin(CATEGORIES)]
if not bad.empty:
    st.warning("Beri kategori untuk status yang dihitung berikut: " + ", ".join(bad["Status"]))
included = edited[edited["Include"] & edited["Category"].isin(CATEGORIES)]
st.caption(f"{int(included['Records'].sum()):,} baris dalam {len(included)} status akan dimodelkan.")

if not edited.equals(st.session_state["mapping_df"]):
    st.session_state["mapping_df"] = edited
    state.clear_from("calibration")

if ok_p and not included.empty:
    st.page_link("app_pages/2_build.py", label="Lanjut ke Bangun model", icon=":material/arrow_forward:")
