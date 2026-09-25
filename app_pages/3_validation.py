import streamlit as st

from app_lib import charts, i18n, state, ui

st.title("Validasi model")
ui.lede("Tiga pemeriksaan: apakah log gangguan sesuai dengan data KPI bulanan, apakah model dapat mereproduksi "
        "tahun-tahun sebelumnya, dan bukti apa yang mendasari setiap angka hasil kalibrasi.")
ui.need("calibration")
cfg, ev, res = state.get("cfg"), state.get("evidence"), state.get("results")

# ---------------------------------------------------------------------------
st.header("Backtest terhadap tahun-tahun sebelumnya")
if res is None or res["backtest"].empty:
    st.info("Jalankan simulasi dengan opsi backtest di halaman Bangun model untuk melihat pemeriksaan ini.")
    st.page_link("app_pages/2_build.py", label="Ke Bangun model", icon=":material/arrow_forward:")
else:
    bt = res["backtest"]
    inside, total = int(bt["Inside P10-P90"].sum()), len(bt)
    eaf_bt = bt[bt["Metric"] == "EAF (%)"]
    mae = (eaf_bt["Actual"] - eaf_bt["P50"]).abs().mean()
    ui.annunciator([
        {"name": "Nilai aktual di dalam rentang P10-P90", "value": f"{inside} dari {total}",
         "range": "Model yang terkalibrasi baik menempatkan sekitar 80% di dalamnya", "prob": None,
         "cls": "green" if 0.6 <= inside / total <= 0.95 else "amber",
         "signal": f"cakupan {inside / total:.0%}"},
        {"name": "Rata-rata galat absolut EAF (P50 vs aktual)", "value": f"{mae:.1f} poin %",
         "range": "Seluruh unit-tahun", "prob": None, "signal": ""},
        {"name": "Unit-tahun yang diulang", "value": f"{len(eaf_bt)}",
         "range": "Memakai outage terencana dan jenis inspeksi aktual", "prob": None, "signal": ""},
    ])
    metric = st.radio("Metrik", ["EAF (%)", "EFOR (%)"], horizontal=True, label_visibility="collapsed")
    st.plotly_chart(charts.backtest(bt, metric), width="stretch")
    st.caption("Setiap tahun historis diulang dengan jam outage terencana dan jenis inspeksi aktualnya. EAF aktual "
               "memasukkan jam outage gangguan yang oleh KPI digolongkan di luar kendali manajemen (OMC), sehingga bisa "
               "sedikit di bawah KPI yang dilaporkan. Ini pemeriksaan in-sample: frekuensi diestimasi dari tahun yang sama.")
    with st.expander("Tabel backtest"):
        st.dataframe(i18n.df(bt, values=["Inspection"]), hide_index=True, width="stretch",
                     column_config={i18n.col("Percentile of actual"):
                                    st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=1)})

# ---------------------------------------------------------------------------
st.header("Log gangguan terhadap data KPI")
rec = ev["reconciliation"]
st.plotly_chart(charts.reconciliation(rec), width="stretch")
g = rec.groupby("item")[["failure_log", "production_data"]].sum()
g["difference %"] = (g["failure_log"] / g["production_data"] - 1) * 100
st.dataframe(i18n.df(g.round(1), index=True), width="stretch")
st.caption("Jam derating di log adalah MWh yang hilang dibagi referensi derating "
           f"({cfg['constants']['derate_reference_mw']:g} MW). Selisih outage gangguan biasanya berasal dari status "
           "yang tidak dihitung dalam pemetaan, seperti FO.SYS, yang dicatat di data KPI sebagai di luar kendali manajemen.")
with st.expander("Per unit dan tahun"):
    st.dataframe(i18n.df(rec, values=["item"]), hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
st.header("Bukti kalibrasi")
t1, t2, t3, t4 = st.tabs(["Kelas kejadian", "Kinerja pembangkit", "Outage terencana", "Kejadian gabungan"])
with t1:
    st.caption("Frekuensi: Poisson per unit-tahun digabung antar unit, dengan ketidakpastian laju Gamma(k + 0,5, 1/unit-tahun). "
               "Durasi: empiris untuk kelas dengan 8 kejadian atau lebih, selain itu lognormal yang disesuaikan dengan rata-rata observasi.")
    st.dataframe(i18n.df(ev["event_classes"], values=["description"]), hide_index=True, width="stretch", height=460)
with t2:
    cf = ev["continuous_fits"]
    labels = {"nphr_kcal_kwh": "Net plant heat rate (kcal/kWh)", "net_output_factor": "Net output factor",
              "aux_share": "Pemakaian sendiri + susut trafo (porsi dari bruto)", "cofiring_share": "Porsi biomassa dari masukan panas"}
    for var, lab in labels.items():
        if var in set(cf["variable"]):
            st.plotly_chart(charts.continuous_fit(cf, var, lab), width="stretch")
    st.caption("Nilai paling mungkin adalah tahun terakhir. Tahun terbaik yang teramati membatasi sisi atas, dan sisi bawah "
               "diperpanjang setengah dari selisih tahun terakhir ke tahun terbaik di luar nilai tahun terakhir.")
    st.markdown("**Korelasi (dari data bulanan)**")
    st.dataframe(i18n.df(ev["correlations"], values=["variable_a", "variable_b"]), hide_index=True)
with t3:
    st.dataframe(i18n.df(ev["planned_outage"], values=["inspection_type"]), hide_index=True, width="stretch")
    st.json({i18n.t(k): v for k, v in cfg["planned_outage_specs"].items()}, expanded=False)
with t4:
    st.dataframe(i18n.df(ev["events_merged"]), hide_index=True, width="stretch", height=460)

st.header("Keterbatasan yang diketahui")
st.markdown(
    "- Frekuensi digabung antar unit, sehingga kedua unit memiliki laju kejadian yang sama. Gunakan pengali frekuensi "
    "di halaman Bangun model untuk mencerminkan perbedaan.\n"
    "- Tren kinerja pembangkit diteruskan dari tahun terakhir; prakiraan beberapa tahun memerlukan tren yang eksplisit.\n"
    "- Start unit dan pemakaian biodiesel tidak dimodelkan (sekitar 0,2% dari masukan panas).\n"
    "- Target EAF dan EFOR serta harga batubara dan biomassa masih sementara sampai Anda memasukkan nilai sendiri.")
