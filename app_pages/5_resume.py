import io

import pandas as pd
import streamlit as st

from app_lib import state, ui
from app_lib.i18n import t

ui.need("results")
cfg, r, ev = state.get("run_cfg"), state.get("results"), state.get("evidence")
res, units, reg = r["res"], list(cfg["units"]), r["register"]
p = res["Plant"]
fy = cfg["forecast_year"]
T = lambda k: sum(cfg["units"][u]["targets"][k] for u in units)

st.title(f"Ringkasan model {fy}")
ui.lede(f"{cfg['name']}. {r['n']:,} tahun simulasi per unit, dikalibrasi dari "
        f"{int(ev['event_classes']['exposure_unit_years'].iloc[0]):g} unit-tahun data gangguan dan produksi.")

plan_gross, plan_net, plan_coal = T("gross_production_min_gwh"), T("net_production_min_gwh"), T("coal_max_kt")
p_gross = (p["gross_gwh"] >= plan_gross).mean()
p_net = (p["net_gwh"] >= plan_net).mean()
p_coal = (p["coal_kt"] <= plan_coal).mean()
eaf_t = cfg["units"][units[0]]["targets"]["eaf_min"] * 100

ui.annunciator([
    {"name": "EAF pembangkit", "value": f"{p['eaf_pct'].mean():.1f} %", "range": f"P10 {p['eaf_pct'].quantile(.1):.1f}  -  P90 {p['eaf_pct'].quantile(.9):.1f}",
     "prob": (p["eaf_pct"] >= eaf_t).mean(), "signal": f"peluang {(p['eaf_pct'] >= eaf_t).mean():.0%} mencapai {eaf_t:.0f}%"},
    {"name": "Produksi bruto", "value": f"{p['gross_gwh'].mean():,.0f} GWh", "range": f"Rencana {plan_gross:,.0f} GWh",
     "prob": p_gross, "signal": f"peluang {p_gross:.0%} mencapai rencana"},
    {"name": "Penjualan neto", "value": f"{p['net_gwh'].mean():,.0f} GWh", "range": f"Rencana {plan_net:,.0f} GWh",
     "prob": p_net, "signal": f"peluang {p_net:.0%} mencapai rencana"},
    {"name": "Batubara", "value": f"{p['coal_kt'].mean():,.0f} kt", "range": f"Rencana {plan_coal:,.0f} kt",
     "prob": p_coal, "signal": f"peluang {p_coal:.0%} tetap dalam rencana"},
])

st.markdown('<div class="resume">', unsafe_allow_html=True)

# ---- outlook ------------------------------------------------------------------
st.header("Prospek")
plan = r["plan"]["Plant"]
gap = plan["net_gwh"].iloc[0] - p["net_gwh"].mean()
unit_lines = "; ".join(f"{u} EAF {res[u]['eaf_pct'].mean():.1f}% dan {res[u]['gross_gwh'].mean():,.0f} GWh bruto" for u in units)
st.markdown(
    f"Pada {fy} pembangkit diperkirakan mencapai EAF **{p['eaf_pct'].mean():.1f}%** "
    f"(P10 {p['eaf_pct'].quantile(.1):.1f}% sampai P90 {p['eaf_pct'].quantile(.9):.1f}%) dan memproduksi "
    f"**{p['gross_gwh'].mean():,.0f} GWh** bruto, dengan peluang {p_gross:.0%} mencapai rencana {plan_gross:,.0f} GWh. "
    f"Penjualan neto mencapai rencana pada {p_net:.0%} tahun simulasi. Per unit: {unit_lines}.")
st.markdown(
    f"Rencana yang mengasumsikan tanpa gangguan menghasilkan {plan['net_gwh'].iloc[0]:,.0f} GWh neto. Hasil yang diharapkan "
    f"{gap:,.0f} GWh lebih rendah: {p['lost_net_gwh'].mean():,.0f} GWh hilang akibat outage dan derating tak terencana, "
    f"sisanya akibat outage terencana yang lebih lama dari durasi paling mungkin dan ketidakpastian kinerja pembangkit.")

# ---- risks --------------------------------------------------------------------
st.header("Risiko utama")
lines = []
for _, x in reg.head(3).iterrows():
    lines.append(f"- **{t(x['Description'])}** ({x['Event class']}): sekitar {x['Events per year (plant)']:.1f} kejadian per tahun, "
                 f"masing-masing {x['Mean eq. hours per event']:.0f} jam ekuivalen, mengakibatkan kehilangan rata-rata "
                 f"{x['Expected net energy loss (GWh/yr)']:.1f} GWh dan {x['Expected EAF impact (pp, plant)']:.2f} poin EAF per tahun "
                 f"({x['Share of expected event loss']:.0%} dari kehilangan tak terencana).")
st.markdown("\n".join(lines))
top_share = reg["Share of expected event loss"].head(3).sum()
st.markdown(f"Ketiga kelas ini menyumbang {top_share:.0%} dari ekspektasi energi yang hilang secara tak terencana. "
            f"Faktor pendorong utama ketidakpastian produksi pembangkit adalah: "
            + "; ".join(ui.driver_label(x, {k: v["description"] for k, v in cfg["event_classes"].items()}).lower()
                        for x in r["sens_prod"]["Driver"].head(4)) + ".")

# ---- opportunities ------------------------------------------------------------
sc = r["scenarios"]
if not sc.empty:
    st.header("Peluang dan tindakan perbaikan")
    s = sc[sc["Scenario"] != "Base"].copy()
    out = []
    for _, x in s.sort_values("Delta mean net GWh vs base", ascending=False).iterrows():
        parts = []
        if abs(x["Delta mean net GWh vs base"]) >= 0.5:
            parts.append(f"{x['Delta mean net GWh vs base']:+,.1f} GWh neto rata-rata ({x['Delta P10 net GWh vs base']:+,.1f} GWh pada tahun buruk)")
        if abs(x["Delta coal (kt) vs base"]) >= 0.5:
            parts.append(f"{x['Delta coal (kt) vs base']:+,.1f} kt batubara")
        if parts:
            out.append(f"- **{t(x['Scenario'])}** - {t(x['Description'])}: " + "; ".join(parts) + ".")
    st.markdown("\n".join(out) if out else "Tidak ada skenario yang mengubah hasil secara berarti.")

# ---- validation ---------------------------------------------------------------
st.header("Validasi")
bt = r["backtest"]
rec = ev["reconciliation"].groupby("item")[["failure_log", "production_data"]].sum()
fd = rec.loc["Forced derating eq. hours"]
if not bt.empty:
    inside = int(bt["Inside P10-P90"].sum())
    st.markdown(f"Dengan mengulang unit-tahun historis memakai outage terencana aktualnya, {inside} dari {len(bt)} nilai EAF dan "
                f"EFOR aktual berada di dalam rentang P10-P90 model (sekitar 80% diharapkan untuk model yang terkalibrasi baik). "
                f"Ini pemeriksaan in-sample.")
st.markdown(f"Log gangguan sesuai dengan data KPI bulanan: derating gangguan setara {fd['failure_log']:,.0f} jam ekuivalen "
            f"di log dibandingkan {fd['production_data']:,.0f} jam EFDH ({fd['failure_log'] / fd['production_data'] - 1:+.0%}).")

# ---- method -------------------------------------------------------------------
st.header("Cara kerja model")
events = ev["events_merged"]
st.markdown(
    f"- {int(events['source_rows'].sum()):,} baris log digabung menjadi {len(events):,} kejadian dan dikelompokkan ke dalam "
    f"{len(cfg['event_classes'])} kelas berdasarkan status dan mode kegagalan.\n"
    "- Setiap kelas memiliki frekuensi Poisson yang digabung antar unit, termasuk ketidakpastian lajunya, "
    "dan distribusi durasi dari kejadian yang teramati.\n"
    "- Jam outage terencana mengikuti jenis inspeksi; heat rate, net output factor, porsi pemakaian sendiri dan porsi "
    "co-firing berpusat pada tahun terakhir.\n"
    "- EAF, EFOR, produksi, batubara, biomassa dan CO2 dihitung untuk setiap tahun simulasi.")

st.header("Asumsi yang perlu dikonfirmasi")
st.markdown(
    f"- Target EAF {eaf_t:.0f}% dan batas EFOR {cfg['units'][units[0]]['targets']['efor_max'] * 100:.0f}% masih sementara.\n"
    f"- Rencana produksi dan batubara ({plan_gross:,.0f} GWh bruto, {plan_coal:,.0f} kt batubara) mengikuti tahun rencana terakhir di data.\n"
    + ("- Harga batubara, harga biomassa dan BPP berasal dari file harga "
       f"({t(cfg['economics']['price_source'])}).\n" if "price_source" in cfg["economics"] else
       "- Harga batubara, harga biomassa dan BPP (Biaya Pokok Penyediaan) masih sementara; angka rupiah bersifat ilustratif.\n") +
    "- Jenis inspeksi: " + ", ".join(f"{u} {t(cfg['units'][u]['inspection_type'])}" for u in units) + ".")
st.markdown("</div>", unsafe_allow_html=True)

# ---- downloads ----------------------------------------------------------------
st.divider()
st.header("Unduh")
st.caption("Laporan Excel, konfigurasi dan bukti kalibrasi memakai label bahasa Inggris, sama dengan alat baris perintah.")
c1, c2, c3 = st.columns(3)
with c1:
    if st.button("Siapkan laporan Excel", width="stretch"):
        with st.spinner("Menulis workbook dan grafik..."):
            st.session_state["excel_report"] = state.build_excel_report(cfg, r, ev)
    if state.get("excel_report"):
        st.download_button("Unduh laporan Excel", state.get("excel_report"), file_name=f"Risk_Model_Results_{fy}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary",
                           width="stretch")
with c2:
    st.download_button("Unduh konfigurasi model", state.config_yaml(cfg), file_name="model_config.yaml",
                       mime="text/yaml", width="stretch")
with c3:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, tbl in ev.items():
            tbl.to_excel(xw, sheet_name=name[:31], index=False)
    st.download_button("Unduh bukti kalibrasi", buf.getvalue(), file_name="calibration_evidence.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
