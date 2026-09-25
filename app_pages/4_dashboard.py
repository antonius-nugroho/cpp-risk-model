import streamlit as st

from app_lib import charts, i18n, state, ui
from app_lib.i18n import t

ui.need("results")
cfg, r = state.get("run_cfg"), state.get("results")
res, units = r["res"], list(cfg["units"])

st.title(f"Dasbor {cfg['forecast_year']}")
scope = st.segmented_control("Cakupan", ["Plant"] + units, default="Plant", format_func=t,
                             label_visibility="collapsed") or "Plant"
d = res[scope]

if scope == "Plant":
    plan_gross = sum(cfg["units"][u]["targets"]["gross_production_min_gwh"] for u in units)
    plan_coal = sum(cfg["units"][u]["targets"]["coal_max_kt"] for u in units)
    eaf_t, efor_t = [cfg["units"][units[0]]["targets"][k] * 100 for k in ("eaf_min", "efor_max")]
else:
    tg = cfg["units"][scope]["targets"]
    plan_gross, plan_coal, eaf_t, efor_t = tg["gross_production_min_gwh"], tg["coal_max_kt"], tg["eaf_min"] * 100, tg["efor_max"] * 100


def window(name, x, unit, target, higher=True, digits=1):
    p = (x >= target).mean() if higher else (x <= target).mean()
    return {"name": name, "value": f"{x.mean():,.{digits}f} {unit}",
            "range": f"P10 {x.quantile(.1):,.{digits}f}  -  P90 {x.quantile(.9):,.{digits}f}", "prob": p,
            "signal": f"peluang {p:.0%} {'mencapai' if higher else 'tetap di bawah'} {target:,.{digits}f}"}


ui.annunciator([
    window("Faktor ketersediaan ekuivalen (EAF)", d["eaf_pct"], "%", eaf_t),
    window("Laju outage gangguan ekuivalen (EFOR)", d["efor_pct"], "%", efor_t, higher=False),
    window("Produksi bruto", d["gross_gwh"], "GWh", plan_gross, digits=0),
    window("Konsumsi batubara", d["coal_kt"], "kt", plan_coal, higher=False, digits=0),
    {"name": "Energi hilang akibat kejadian tak terencana", "value": f"{d['lost_net_gwh'].mean():,.0f} GWh",
     "range": f"P90 {d['lost_net_gwh'].quantile(.9):,.0f} GWh", "prob": None, "signal": "Energi neto, ekspektasi"},
])
st.caption("Warna panel: hijau peluang mencapai target 70% atau lebih, kuning 40-70%, merah di bawah 40%. "
           "Target EAF dan EFOR masih sementara sampai diatur di halaman Bangun model.")

t1, t2, t3, t4 = st.tabs(["Hasil", "Risiko", "Faktor pendorong", "Skenario"])
with t1:
    a, b = st.columns(2)
    a.plotly_chart(charts.histogram(d["gross_gwh"], "GWh", "Produksi bruto", plan_gross, "Rencana"), width="stretch")
    b.plotly_chart(charts.histogram(d["eaf_pct"], "EAF (%)", "Faktor ketersediaan ekuivalen", eaf_t, "Target"),
                   width="stretch")
    a, b = st.columns(2)
    a.plotly_chart(charts.scurve(d["net_gwh"], "GWh", "Produksi neto (kurva S)",
                                 sum(cfg["units"][u]["targets"]["net_production_min_gwh"] for u in units) if scope == "Plant"
                                 else cfg["units"][scope]["targets"]["net_production_min_gwh"], "Rencana penjualan neto"),
                   width="stretch")
    b.plotly_chart(charts.histogram(d["coal_kt"], "kt", "Konsumsi batubara", plan_coal, "Rencana batubara", higher_is_better=False),
                   width="stretch")
    st.plotly_chart(charts.outage_breakdown(res, units), width="stretch")
    with st.expander("Semua metrik"):
        s = r["summary"]
        st.dataframe(i18n.df(s[s["Scope"] == scope].drop(columns="Scope"), values=["Metric"]), hide_index=True, width="stretch")

with t2:
    reg = r["register"]
    a, b = st.columns([1.05, 1])
    a.plotly_chart(charts.risk_matrix(reg), width="stretch")
    b.plotly_chart(charts.pareto(reg), width="stretch")
    st.subheader("Daftar risiko (pembangkit)")
    view = reg.copy()
    view["Risk score"] = view["Likelihood score (1-5)"] * view["Consequence score (1-5)"]
    view["Rating"] = view["Risk score"].map(lambda s: "Ekstrem" if s >= 15 else "Tinggi" if s >= 10 else "Sedang" if s >= 5 else "Rendah")
    cols = ["Rank", "Event class", "Description", "Events per year (plant)", "Mean eq. hours per event",
            "Expected net energy loss (GWh/yr)", "Expected EAF impact (pp, plant)", "Effect on P10 plant production (GWh)",
            "Share of expected event loss", "Risk score", "Rating"]
    c = i18n.col
    st.dataframe(i18n.df(view[cols], values=["Description"]), hide_index=True, width="stretch", height=440,
                 column_config={c("Share of expected event loss"): st.column_config.ProgressColumn(format="%.2f", min_value=0, max_value=1),
                                c("Events per year (plant)"): st.column_config.NumberColumn(format="%.2f"),
                                c("Mean eq. hours per event"): st.column_config.NumberColumn(format="%.1f"),
                                c("Expected net energy loss (GWh/yr)"): st.column_config.NumberColumn(format="%.2f"),
                                c("Expected EAF impact (pp, plant)"): st.column_config.NumberColumn(format="%.2f"),
                                c("Effect on P10 plant production (GWh)"): st.column_config.NumberColumn(format="%.2f")})
    st.caption("Tingkat = kemungkinan x dampak: 1-4 Rendah, 5-9 Sedang, 10-14 Tinggi, 15-25 Ekstrem. "
               "Urutan peringkat mengikuti ekspektasi energi yang hilang per tahun.")

with t3:
    desc = {k: v["description"] for k, v in cfg["event_classes"].items()}
    sp, scl = r["sens_prod"].copy(), r["sens_coal"].copy()
    sp["Driver"] = sp["Driver"].map(lambda x: ui.driver_label(x, desc))
    scl["Driver"] = scl["Driver"].map(lambda x: ui.driver_label(x, desc))
    st.plotly_chart(charts.bridge(r["bridge"]), width="stretch")
    a, b = st.columns(2)
    a.plotly_chart(charts.tornado(sp, "Faktor pendorong produksi neto pembangkit"), width="stretch")
    b.plotly_chart(charts.tornado(scl, "Faktor pendorong konsumsi batubara pembangkit"), width="stretch")

with t4:
    if r["scen_res"]:
        options = {"Produksi neto (GWh)": "net_gwh", "Konsumsi batubara (kt)": "coal_kt", "EAF (%)": "eaf_pct"}
        metric = st.radio("Bandingkan", list(options), horizontal=True)
        st.plotly_chart(charts.scenarios(r["scen_res"], options[metric], metric), width="stretch")
        st.dataframe(i18n.df(r["scenarios"], values=["Scenario", "Description"]), hide_index=True, width="stretch")
    else:
        st.info("Jalankan simulasi dengan opsi skenario aktif untuk membandingkan tindakan perbaikan dan peluang.")
