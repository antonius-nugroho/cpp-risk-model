"""Interactive Plotly charts for the Streamlit dashboard (labels in Bahasa Indonesia)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from app_lib.i18n import t
from app_lib.ui import AMBER, BLUE, GREEN, GREY, INK, RED

FONT = "Barlow, Segoe UI, Roboto, sans-serif"
GRID = "rgba(138,150,158,.25)"   # reads on light and dark backgrounds
CAT_COLOR = {"FO": RED, "OS": RED, "FD": "#E07A5F", "MO": AMBER, "SE": "#B07D12", "MD": "#E9C46A", "PD": GREY}


def _layout(fig, title=None, height=380, **kw):
    fig.update_layout(
        # text colour and backgrounds are left to the Streamlit theme, so charts follow light / dark mode
        title=dict(text=title, x=0, font=dict(size=15)) if title else None,
        font=dict(family=FONT, size=13), height=height, margin=dict(l=10, r=10, t=46 if title else 12, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=-0.18), **kw)
    fig.update_xaxes(gridcolor=GRID, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


def histogram(x: pd.Series, xlabel: str, title: str, target=None, target_label="Target", higher_is_better=True):
    fig = go.Figure(go.Histogram(x=x, nbinsx=70, marker_color=BLUE, opacity=0.8, name="Tahun simulasi",
                                 hovertemplate="%{x}<br>%{y} iterasi<extra></extra>"))
    for q, dash in [(0.1, "dot"), (0.5, "dash"), (0.9, "dot")]:
        fig.add_vline(x=x.quantile(q), line=dict(color=GREY, dash=dash, width=1))
    sub = f"P10 {x.quantile(.1):,.1f}, P50 {x.median():,.1f}, P90 {x.quantile(.9):,.1f}"
    if target is not None:
        p = (x >= target).mean() if higher_is_better else (x <= target).mean()
        fig.add_vline(x=target, line=dict(color=RED, width=2.5))
        sub += f"<br><span style='color:{RED}'>{target_label} {target:,.1f}: peluang {p:.0%} tercapai</span>"
    fig.update_xaxes(title=xlabel)
    fig.update_yaxes(title="Iterasi")
    fig = _layout(fig, f"{title}<br><span style='font-size:12px;color:{GREY}'>{sub}</span>", height=400, showlegend=False)
    fig.update_layout(margin=dict(t=78))
    return fig


def scurve(x: pd.Series, xlabel: str, title: str, target=None, target_label="Rencana"):
    v = np.sort(x.dropna().values)
    p = np.arange(1, len(v) + 1) / len(v) * 100
    step = max(1, len(v) // 800)
    fig = go.Figure(go.Scatter(x=v[::step], y=p[::step], mode="lines", line=dict(color=BLUE, width=2.5),
                               hovertemplate="%{x:,.1f}<br>%{y:.0f}% tahun pada atau di bawah nilai ini<extra></extra>"))
    if target is not None:
        fig.add_vline(x=target, line=dict(color=RED, dash="dash"),
                      annotation_text=f"{target_label} {target:,.1f}: {(v >= target).mean():.0%} tahun mencapainya",
                      annotation_font_color=RED)
    fig.update_xaxes(title=xlabel)
    fig.update_yaxes(title="Probabilitas kumulatif (%)", range=[0, 100])
    return _layout(fig, title, showlegend=False)


def risk_matrix(reg: pd.DataFrame):
    score = np.outer(np.arange(1, 6), np.arange(1, 6))
    band = np.select([score >= 15, score >= 10, score >= 5], [3, 2, 1], 0)   # Low / Medium / High / Extreme
    colors = [[0, "#C6E0B4"], [0.25, "#C6E0B4"], [0.25, "#FFE699"], [0.5, "#FFE699"],
              [0.5, "#F8B98B"], [0.75, "#F8B98B"], [0.75, "#F28B82"], [1, "#F28B82"]]
    fig = go.Figure(go.Heatmap(z=band, x=[1, 2, 3, 4, 5], y=[1, 2, 3, 4, 5], colorscale=colors, zmin=-0.5, zmax=3.5,
                               showscale=False, hoverinfo="skip"))
    rng = np.random.default_rng(3)
    jx = rng.uniform(-0.3, 0.3, len(reg))
    jy = rng.uniform(-0.3, 0.3, len(reg))
    fig.add_trace(go.Scatter(
        x=reg["Consequence score (1-5)"] + jx, y=reg["Likelihood score (1-5)"] + jy, mode="markers+text",
        text=reg["Rank"].astype(str), textposition="middle right", textfont=dict(size=11, color=INK),
        marker=dict(size=8 + 60 * np.sqrt(reg["Share of expected event loss"]), color=INK, opacity=0.85,
                    line=dict(color="white", width=1)),
        customdata=np.stack([reg["Event class"], reg["Events per year (plant)"],
                             reg["Mean net MWh lost per event"], reg["Expected net energy loss (GWh/yr)"]], axis=1),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]:.2f} kejadian/thn<br>"
                      "%{customdata[2]:,.0f} MWh per kejadian<br>ekspektasi %{customdata[3]:.1f} GWh/thn<extra></extra>"))
    fig.update_xaxes(tickvals=[1, 2, 3, 4, 5], ticktext=["< 0.2", "0.2-1", "1-5", "5-15", "> 15"],
                     title="Dampak: GWh neto hilang per kejadian", range=[0.5, 5.5], showgrid=False)
    fig.update_yaxes(tickvals=[1, 2, 3, 4, 5], ticktext=["< 0.2", "0.2-0.5", "0.5-1", "1-3", "> 3"],
                     title="Kemungkinan: kejadian per tahun (pembangkit)", range=[0.5, 5.5], showgrid=False)
    return _layout(fig, "Matriks risiko (label = peringkat, ukuran = porsi ekspektasi kehilangan)", height=520, showlegend=False)


def pareto(reg: pd.DataFrame, top=12):
    r = reg.head(top).copy()
    r["label"] = [f"{k}. {c} {t(dsc.split(' - ')[-1]).lower()}" for k, c, dsc in zip(r["Rank"], r["Category"], r["Description"])]
    cum = reg["Share of expected event loss"].cumsum().head(top) * 100
    fig = go.Figure(go.Bar(x=r["label"], y=r["Expected net energy loss (GWh/yr)"],
                           marker_color=[CAT_COLOR.get(c, GREY) for c in r["Category"]],
                           customdata=r["Description"].map(t), name="Ekspektasi kehilangan",
                           hovertemplate="<b>%{x}</b><br>%{customdata}<br>%{y:.1f} GWh/thn<extra></extra>"))
    fig.add_trace(go.Scatter(x=r["label"], y=cum, yaxis="y2", mode="lines+markers", name="Porsi kumulatif",
                             line=dict(color=GREY), hovertemplate="%{y:.0f}% kumulatif<extra></extra>"))
    fig = _layout(fig, "Asal kehilangan energi tak terencana", height=520)
    fig.update_layout(yaxis=dict(title="Ekspektasi energi neto hilang (GWh/thn)"),
                      yaxis2=dict(overlaying="y", side="right", range=[0, 105], dtick=20, title="Porsi kumulatif (%)",
                                  showgrid=False),
                      margin=dict(b=150), legend=dict(y=-0.55))
    fig.update_xaxes(tickangle=-40, tickfont=dict(size=11))
    return fig


def bridge(b: pd.DataFrame):
    measure = ["absolute"] + ["relative"] * (len(b) - 2) + ["total"]
    fig = go.Figure(go.Waterfall(
        x=b["Step"].map(t), y=b["Net production (GWh)"], measure=measure,
        text=[f"{v:,.0f}" if m != "relative" else f"{v:+,.1f}" for v, m in zip(b["Net production (GWh)"], measure)],
        textposition="outside", connector=dict(line=dict(color=GREY, width=1)),
        increasing=dict(marker_color=GREEN), decreasing=dict(marker_color=RED), totals=dict(marker_color=GREY)))
    lo = min(b["Net production (GWh)"].iloc[-1], b["Net production (GWh)"].cumsum().iloc[:-1].min())
    fig.update_yaxes(range=[lo * 0.96, b["Net production (GWh)"].iloc[0] * 1.02], title="Produksi neto pembangkit (GWh)")
    fig.update_xaxes(tickangle=-30)
    fig = _layout(fig, "Dari rencana deterministik ke hasil yang diharapkan", height=500, showlegend=False)
    fig.update_layout(margin=dict(b=130))
    return fig


def tornado(s: pd.DataFrame, title: str):
    s = s.iloc[::-1]
    fig = go.Figure(go.Bar(x=s["Rank correlation"], y=s["Driver"], orientation="h",
                           marker_color=[GREEN if v > 0 else RED for v in s["Rank correlation"]],
                           customdata=s["Contribution to variance"],
                           hovertemplate="%{y}<br>rho %{x:.2f}<br>%{customdata:.0%} dari varians<extra></extra>"))
    fig.update_xaxes(title="Korelasi peringkat (hijau menaikkan hasil, merah menurunkannya)", range=[-1, 1])
    return _layout(fig, title, height=90 + 26 * len(s), showlegend=False)


def backtest(bt: pd.DataFrame, metric="EAF (%)"):
    b = bt[bt["Metric"] == metric].reset_index(drop=True)
    lab = [f"{u}<br>{y} ({t(i)})" for u, y, i in zip(b["Unit"], b["Year"], b["Inspection"])]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=lab, y=b["P90"] - b["P10"], base=b["P10"], marker_color="rgba(30,95,168,0.25)",
                         name="Model P10-P90", width=0.45, hovertemplate="P10 %{base:.1f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=lab, y=b["P50"], mode="markers", marker=dict(symbol="line-ew", size=26, color=BLUE,
                             line=dict(width=3, color=BLUE)), name="Model P50"))
    fig.add_trace(go.Scatter(x=lab, y=b["Actual"], mode="markers", marker=dict(size=12, color=RED), name="Aktual",
                             customdata=b["Percentile of actual"],
                             hovertemplate="Aktual %{y:.2f}<br>persentil %{customdata:.0%}<extra></extra>"))
    if metric.startswith("EAF"):
        fig.add_trace(go.Scatter(x=lab, y=b["Reported KPI"], mode="markers", name="KPI dilaporkan",
                                 marker=dict(symbol="x", size=10, color=GREY)))
    fig.update_yaxes(title=metric)
    return _layout(fig, f"Backtest: {metric.split(' ')[0]} aktual terhadap rentang model", height=430)


def scenarios(results: dict, col="net_gwh", label="Produksi neto pembangkit (GWh)"):
    fig = go.Figure()
    for i, (name, d) in enumerate(results.items()):
        x = d[col]
        q = x.quantile([0.1, 0.25, 0.5, 0.75, 0.9]).values
        fig.add_trace(go.Box(name=t(name), q1=[q[1]], median=[q[2]], q3=[q[3]], lowerfence=[q[0]], upperfence=[q[4]],
                             mean=[x.mean()], marker_color=GREY if i == 0 else BLUE, boxpoints=False))
    fig.update_yaxes(title=label)
    return _layout(fig, "Skenario (kotak P25-P75, garis P10-P90, garis putus-putus = rata-rata)", height=440, showlegend=False)


def outage_breakdown(res: dict, units: list[str]):
    cols = [("poh_h", "Outage terencana", "#9FB3C2"), ("seh_h", "Perpanjangan outage", "#B07D12"),
            ("moh_h", "Outage pemeliharaan", AMBER), ("foh_h", "Outage gangguan", RED),
            ("efdh_h", "Derating gangguan (ekuiv.)", "#E07A5F"), ("emdh_h", "Derating pemeliharaan (ekuiv.)", "#E9C46A"),
            ("epdh_h", "Derating terencana (ekuiv.)", GREY)]
    fig = go.Figure()
    for c, name, color in cols:
        fig.add_trace(go.Bar(x=units, y=[res[u][c].mean() for u in units], name=name, marker_color=color,
                             hovertemplate=f"{name}: %{{y:,.0f}} h<extra></extra>"))
    fig.update_layout(barmode="stack")
    fig.update_yaxes(title="Rata-rata jam per tahun")
    return _layout(fig, "Ke mana jam-jam tersebut (nilai ekspektasi)", height=420)


def continuous_fit(cf: pd.DataFrame, variable: str, title: str):
    d = cf[cf["variable"] == variable]
    years = [c for c in d.columns if str(c).isdigit()]
    fig = go.Figure()
    for i, (_, r) in enumerate(d.iterrows()):
        spec = r["fitted"].split("(")[1].rstrip(")").split(",")
        lo, mode, hi = [float(v) for v in spec]
        fig.add_trace(go.Scatter(x=[lo, hi], y=[r["unit"]] * 2, mode="lines", line=dict(color="rgba(30,95,168,.35)", width=14),
                                 name="Rentang prakiraan", showlegend=i == 0, hovertemplate=f"{lo:g} s.d. {hi:g}<extra></extra>"))
        fig.add_trace(go.Scatter(x=[mode], y=[r["unit"]], mode="markers", marker=dict(symbol="line-ns", size=22,
                                 line=dict(width=3, color=BLUE)), name=f"Paling mungkin ({years[-1]})" if years else "Paling mungkin", showlegend=i == 0))
        fig.add_trace(go.Scatter(x=[r[y] for y in years], y=[r["unit"]] * len(years), mode="markers+text",
                                 text=years, textposition="top center", textfont=dict(size=10),
                                 marker=dict(size=9, color=GREY), name="Tahun teramati", showlegend=i == 0))
    return _layout(fig, title, height=230)


def reconciliation(rec: pd.DataFrame):
    g = rec.groupby("item")[["failure_log", "production_data"]].sum().reset_index()
    fig = go.Figure([go.Bar(y=g["item"].map(t), x=g["failure_log"], orientation="h", name="Log gangguan", marker_color=BLUE),
                     go.Bar(y=g["item"].map(t), x=g["production_data"], orientation="h", name="Data produksi", marker_color=GREY)])
    fig.update_layout(barmode="group")
    fig.update_xaxes(title="Jam, semua unit dan tahun")
    return _layout(fig, "Log gangguan terhadap data KPI bulanan", height=360)
