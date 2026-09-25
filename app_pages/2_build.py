import copy

import pandas as pd
import streamlit as st

from app_lib import i18n, state, ui
from app_lib.i18n import t
from app_lib.status_codes import CATEGORIES

st.title("Bangun model")
ui.lede("Kalibrasi model dari data yang diunggah, sesuaikan asumsi prakiraan, lalu jalankan simulasi Monte Carlo.")
ui.need("data")

mapping_df = state.get("mapping_df")
if mapping_df is None:
    mapping_df = state.mapping_table(state.get("failure_bytes"), state.inspect_failure(state.get("failure_bytes"))["df"])
    st.session_state["mapping_df"] = mapping_df
inc = mapping_df[mapping_df["Include"] & mapping_df["Category"].isin(CATEGORIES)]
mapping_items = tuple(sorted(zip(inc["Status"], inc["Category"])))

# ---------------------------------------------------------------------------
st.header("Kalibrasi")
c1, c2 = st.columns([1, 3])
with c1:
    last_year = int(state.inspect_production(state.get("production_bytes"))["df"]["end_of_month"].pipe(pd.to_datetime).dt.year.max())
    fy = st.number_input("Tahun prakiraan", min_value=2000, max_value=2100, step=1,
                         value=int(state.get("forecast_year", last_year + 1)),
                         help="Bawaan: tahun setelah bulan terakhir di Data Pengusahaan")
with c2:
    st.write("")
    st.write("")
    go = st.button("Kalibrasi model", type="primary", disabled=not mapping_items)
if not mapping_items:
    st.warning("Belum ada status yang dihitung. Pilih minimal satu di halaman Data.")

if go or (state.get("cfg") is not None and state.get("forecast_year") != fy):
    with st.spinner("Menggabungkan kejadian, menyesuaikan frekuensi dan durasi..."):
        try:
            cfg, ev = state.calibrate_cached(state.get("failure_bytes"), state.get("production_bytes"), int(fy), mapping_items,
                                            state.get("bpp_bytes"))
        except Exception as exc:  # show the reason, keep the app alive
            st.error(f"Kalibrasi gagal: {exc}")
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
    ("Baris log digabung menjadi kejadian", f"{int(events['source_rows'].sum()):,} baris -> {len(events):,} kejadian", "ok"),
    ("Kelas kejadian", f"{ev['event_classes'].shape[0]}", "ok"),
    ("Eksposur", f"{ev['event_classes']['exposure_unit_years'].iloc[0]:g} unit-tahun", "ok"),
    ("Unit dan DMN", ", ".join(f"{u}: {c['dmn_mw']:g} MW" for u, c in cfg["units"].items()), "ok"),
    ("Referensi derating (MW bruto)", f"{cfg['constants']['derate_reference_mw']:g} MW", "ok"),
])

# ---------------------------------------------------------------------------
st.header("Asumsi prakiraan")
ui.lede("Nilai berasal dari kalibrasi. Ubah untuk menguji kasus what-if; nilai bawaan yang ditandai sementara "
        "sebaiknya diganti dengan kontrak KPI dan harga Anda.")
work = copy.deepcopy(cfg)

tabs = st.tabs(list(cfg["units"]) + ["Harga", "Frekuensi kejadian", "Skenario"])
for tab, (u, uc) in zip(tabs, cfg["units"].items()):
    with tab:
        a, b = st.columns(2)
        with a:
            st.markdown("**Outage terencana**")
            specs = cfg["planned_outage_specs"]
            types = list(specs)
            itype = st.selectbox("Jenis inspeksi", types, index=types.index(uc["inspection_type"]) if uc["inspection_type"] in types else 0,
                                 format_func=t, key=f"w_{u}_insp", help="Disarankan dari siklus inspeksi tiap unit di data")
            sp = specs[itype]
            x1, x2, x3 = st.columns(3)
            lo = x1.number_input("Jam minimum", value=float(sp["min"]), key=f"w_{u}_{itype}_min")
            mo = x2.number_input("Paling mungkin", value=float(sp["mode"]), key=f"w_{u}_{itype}_mode")
            hi = x3.number_input("Jam maksimum", value=float(sp["max"]), key=f"w_{u}_{itype}_max")
            if not lo <= mo <= hi:
                st.error("Jam outage terencana harus memenuhi minimum <= paling mungkin <= maksimum.")
                st.stop()
            work["units"][u]["inspection_type"] = itype
            work["units"][u]["planned_outage_hours"] = {"type": "triangular", "min": lo, "mode": mo, "max": hi}
        with b:
            st.markdown("**Target**")
            tg = uc["targets"]
            y1, y2 = st.columns(2)
            eaf = y1.number_input("Target EAF (%) - sementara", value=tg["eaf_min"] * 100, step=0.5, key=f"w_{u}_eaf")
            efor = y2.number_input("Batas EFOR (%) - sementara", value=tg["efor_max"] * 100, step=0.5, key=f"w_{u}_efor")
            gross = y1.number_input("Rencana produksi bruto (GWh)", value=float(tg["gross_production_min_gwh"]), key=f"w_{u}_gross")
            net = y2.number_input("Rencana penjualan neto (GWh)", value=float(tg["net_production_min_gwh"]), key=f"w_{u}_net")
            coal = y1.number_input("Rencana batubara (kt)", value=float(tg["coal_max_kt"]), key=f"w_{u}_coal")
            st.caption("Rencana produksi dan batubara mengikuti tahun terakhir di Data Pengusahaan.")
            work["units"][u]["targets"] = {"eaf_min": eaf / 100, "efor_max": efor / 100, "gross_production_min_gwh": gross,
                                           "net_production_min_gwh": net, "coal_max_kt": coal}
        with st.expander("Distribusi kinerja pembangkit (dari data tahunan)"):
            cf = ev["continuous_fits"]
            st.dataframe(i18n.df(cf[cf["unit"] == u].drop(columns="unit"), values=["variable"]), hide_index=True, width="stretch")

with tabs[len(cfg["units"])]:
    st.caption("Harga hanya memengaruhi angka rupiah, bukan EAF, energi atau jumlah batubara. Harga batubara dan biomassa masih sementara.")
    e = cfg["economics"]
    p1, p2, p3 = st.columns(3)
    work["economics"]["coal_price_rp_t"] = p1.number_input("Harga batubara (Rp/t)", value=float(e["coal_price_rp_t"]), step=10000.0, key="w_coal_price")
    work["economics"]["biomass_price_rp_t"] = p2.number_input("Harga biomassa (Rp/t)", value=float(e["biomass_price_rp_t"]), step=10000.0, key="w_bio_price")
    per_unit = {u: uc["energy_value_rp_kwh"] for u, uc in cfg["units"].items() if "energy_value_rp_kwh" in uc}
    if per_unit:
        st.markdown(f"**Nilai energi yang hilang (Rp/kWh)** - {t(e.get('energy_value_source', 'BPP'))}")
        for col, (u, v) in zip(st.columns(len(per_unit)), per_unit.items()):
            work["units"][u]["energy_value_rp_kwh"] = col.number_input(u, value=float(v), step=10.0, key=f"w_{u}_energy_value")
    else:
        work["economics"]["energy_value_rp_kwh"] = p3.number_input("Nilai energi yang hilang (Rp/kWh) - sementara", value=float(e["energy_value_rp_kwh"]),
                                                                   step=10.0, key="w_energy_value",
                                                                   help="Unggah BPP di halaman Data untuk memakai biaya pokok produksi aktual")

with tabs[len(cfg["units"]) + 1]:
    st.caption("Frekuensi digabung untuk semua unit. Pengali 0,5 membuat frekuensi suatu kelas menjadi separuhnya; 1,5 menaikkannya separuh.")
    ec = ev["event_classes"].set_index("event_class")
    tbl = pd.DataFrame({
        "Event class": list(cfg["event_classes"]),
        "Description": [t(c["description"]) for c in cfg["event_classes"].values()],
        "Events in data": [int(ec.loc[k, "events"]) for k in cfg["event_classes"]],
        "Mean hours per event": [float(ec.loc[k, "mean_hours_or_eq_hours"]) for k in cfg["event_classes"]],
        "Frequency multiplier": [float(c.get("rate_multiplier", 1.0)) for c in cfg["event_classes"].values()],
    })
    ed = st.data_editor(tbl, hide_index=True, width="stretch", key="w_multipliers", height=420,
                        disabled=["Event class", "Description", "Events in data", "Mean hours per event"],
                        column_config={"Event class": st.column_config.TextColumn("Kelas kejadian"),
                                       "Description": st.column_config.TextColumn("Deskripsi"),
                                       "Events in data": st.column_config.NumberColumn("Kejadian di data"),
                                       "Frequency multiplier": st.column_config.NumberColumn("Pengali frekuensi", min_value=0.0, max_value=5.0, step=0.1),
                                       "Mean hours per event": st.column_config.NumberColumn("Rata-rata jam per kejadian", format="%.1f")})
    for _, r in ed.iterrows():
        work["event_classes"][r["Event class"]]["rate_multiplier"] = float(r["Frequency multiplier"])

with tabs[len(cfg["units"]) + 2]:
    names = list(cfg.get("scenarios", {}))
    chosen = st.multiselect("Skenario yang dibandingkan dengan kasus dasar", names, default=names, format_func=t, key="w_scen")
    for nm in names:
        st.markdown(f"**{t(nm)}**: {t(cfg['scenarios'][nm]['description'])}")
    work["scenarios"] = {k: v for k, v in cfg.get("scenarios", {}).items() if k in chosen}

# ---------------------------------------------------------------------------
st.header("Jalankan simulasi")
r1, r2, r3, r4 = st.columns([1, 1, 1, 1.4])
n = r1.select_slider("Iterasi", options=[2000, 5000, 10000, 20000], value=10000, key="w_n")
seed = r2.number_input("Seed acak", value=42, step=1, key="w_seed")
do_bt = r3.checkbox("Backtest", value=True, help="Mengulang tahun-tahun historis untuk memvalidasi model", key="w_bt")
do_sc = r3.checkbox("Skenario", value=True, key="w_sc")
with r4:
    st.write("")
    run = st.button("Jalankan simulasi", type="primary", width="stretch")

if run:
    with st.spinner(f"Menyimulasikan {n:,} tahun per unit..."):
        ev_key = str(hash(tuple(ev["events_merged"]["hours"].round(4))))
        res = state.simulate_cached(state.config_yaml(work), int(n), int(seed), do_bt, do_sc, ev, ev_key)
    st.session_state.update(results=res, run_cfg=work)
    st.session_state.pop("excel_report", None)
    st.success("Simulasi selesai. Buka dasbor, validasi atau ringkasan.")

if state.get("results") is not None:
    c1, c2, c3 = st.columns(3)
    c1.page_link("app_pages/3_validation.py", label="Validasi model", icon=":material/fact_check:")
    c2.page_link("app_pages/4_dashboard.py", label="Dasbor", icon=":material/monitoring:")
    c3.page_link("app_pages/5_resume.py", label="Ringkasan model", icon=":material/summarize:")
    if state.get("run_cfg") != work:
        st.warning("Asumsi berubah sejak simulasi terakhir. Jalankan simulasi lagi untuk memperbarui hasil.")

st.download_button("Unduh konfigurasi model (YAML)", state.config_yaml(work), file_name="model_config.yaml",
                   mime="text/yaml")
