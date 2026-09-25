"""Interactive Plotly charts for the Streamlit dashboard."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from app_lib.ui import AMBER, BLUE, GREEN, GREY, INK, RED

FONT = "Barlow, Segoe UI, Roboto, sans-serif"
CAT_COLOR = {"FO": RED, "OS": RED, "FD": "#E07A5F", "MO": AMBER, "SE": "#B07D12", "MD": "#E9C46A", "PD": GREY}


def _layout(fig, title=None, height=380, **kw):
    fig.update_layout(
        title=dict(text=title, x=0, font=dict(size=15, color=INK)) if title else None,
        font=dict(family=FONT, size=13, color=INK), height=height, margin=dict(l=10, r=10, t=46 if title else 12, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#FFFFFF", legend=dict(orientation="h", y=-0.18), **kw)
    fig.update_xaxes(gridcolor="#E4E9EC", zeroline=False)
    fig.update_yaxes(gridcolor="#E4E9EC", zeroline=False)
    return fig


def histogram(x: pd.Series, xlabel: str, title: str, target=None, target_label="Target", higher_is_better=True):
    fig = go.Figure(go.Histogram(x=x, nbinsx=70, marker_color=BLUE, opacity=0.8, name="Simulated years",
                                 hovertemplate="%{x}<br>%{y} iterations<extra></extra>"))
    for q, dash in [(0.1, "dot"), (0.5, "dash"), (0.9, "dot")]:
        fig.add_vline(x=x.quantile(q), line=dict(color=INK, dash=dash, width=1))
    sub = f"P10 {x.quantile(.1):,.1f}, P50 {x.median():,.1f}, P90 {x.quantile(.9):,.1f}"
    if target is not None:
        p = (x >= target).mean() if higher_is_better else (x <= target).mean()
        fig.add_vline(x=target, line=dict(color=RED, width=2.5))
        sub += f"<br><span style='color:{RED}'>{target_label} {target:,.1f}: {p:.0%} chance of meeting it</span>"
    fig.update_xaxes(title=xlabel)
    fig.update_yaxes(title="Iterations")
    fig = _layout(fig, f"{title}<br><span style='font-size:12px;color:#41525E'>{sub}</span>", height=400, showlegend=False)
    fig.update_layout(margin=dict(t=78))
    return fig


def scurve(x: pd.Series, xlabel: str, title: str, target=None, target_label="Plan"):
    v = np.sort(x.dropna().values)
    p = np.arange(1, len(v) + 1) / len(v) * 100
    step = max(1, len(v) // 800)
    fig = go.Figure(go.Scatter(x=v[::step], y=p[::step], mode="lines", line=dict(color=BLUE, width=2.5),
                               hovertemplate="%{x:,.1f}<br>%{y:.0f}% of years at or below<extra></extra>"))
    if target is not None:
        fig.add_vline(x=target, line=dict(color=RED, dash="dash"),
                      annotation_text=f"{target_label} {target:,.1f}: {(v >= target).mean():.0%} of years reach it",
                      annotation_font_color=RED)
    fig.update_xaxes(title=xlabel)
    fig.update_yaxes(title="Cumulative probability (%)", range=[0, 100])
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
        text=reg["Rank"].astype(str), textposition="middle right", textfont=dict(size=11),
        marker=dict(size=8 + 60 * np.sqrt(reg["Share of expected event loss"]), color=INK, opacity=0.85,
                    line=dict(color="white", width=1)),
        customdata=np.stack([reg["Event class"], reg["Events per year (plant)"],
                             reg["Mean net MWh lost per event"], reg["Expected net energy loss (GWh/yr)"]], axis=1),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]:.2f} events/yr<br>"
                      "%{customdata[2]:,.0f} MWh per event<br>%{customdata[3]:.1f} GWh/yr expected<extra></extra>"))
    fig.update_xaxes(tickvals=[1, 2, 3, 4, 5], ticktext=["< 0.2", "0.2-1", "1-5", "5-15", "> 15"],
                     title="Consequence: net GWh lost per event", range=[0.5, 5.5], showgrid=False)
    fig.update_yaxes(tickvals=[1, 2, 3, 4, 5], ticktext=["< 0.2", "0.2-0.5", "0.5-1", "1-3", "> 3"],
                     title="Likelihood: events per year (plant)", range=[0.5, 5.5], showgrid=False)
    return _layout(fig, "Risk matrix (label = rank, size = share of expected loss)", height=520, showlegend=False)


def short_name(cls: str) -> str:
    cat, _, rest = cls.partition("_")
    return f"{cat} {rest.replace('_', ' ')}"


def pareto(reg: pd.DataFrame, top=12):
    r = reg.head(top).copy()
    r["label"] = [f"{k}. {short_name(c)}" for k, c in zip(r["Rank"], r["Event class"])]
    cum = reg["Share of expected event loss"].cumsum().head(top) * 100
    fig = go.Figure(go.Bar(x=r["label"], y=r["Expected net energy loss (GWh/yr)"],
                           marker_color=[CAT_COLOR.get(c, GREY) for c in r["Category"]],
                           customdata=r["Description"], name="Expected loss",
                           hovertemplate="<b>%{x}</b><br>%{customdata}<br>%{y:.1f} GWh/yr<extra></extra>"))
    fig.add_trace(go.Scatter(x=r["label"], y=cum, yaxis="y2", mode="lines+markers", name="Cumulative share",
                             line=dict(color=INK), hovertemplate="%{y:.0f}% cumulative<extra></extra>"))
    fig = _layout(fig, "Where the unplanned energy loss comes from", height=520)
    fig.update_layout(yaxis=dict(title="Expected net energy loss (GWh/yr)"),
                      yaxis2=dict(overlaying="y", side="right", range=[0, 105], dtick=20, title="Cumulative share (%)",
                                  showgrid=False),
                      margin=dict(b=150), legend=dict(y=-0.55))
    fig.update_xaxes(tickangle=-40, tickfont=dict(size=11))
    return fig


def bridge(b: pd.DataFrame):
    measure = ["absolute"] + ["relative"] * (len(b) - 2) + ["total"]
    fig = go.Figure(go.Waterfall(
        x=b["Step"], y=b["Net production (GWh)"], measure=measure,
        text=[f"{v:,.0f}" if m != "relative" else f"{v:+,.1f}" for v, m in zip(b["Net production (GWh)"], measure)],
        textposition="outside", connector=dict(line=dict(color=GREY, width=1)),
        increasing=dict(marker_color=GREEN), decreasing=dict(marker_color=RED), totals=dict(marker_color=GREY)))
    lo = min(b["Net production (GWh)"].iloc[-1], b["Net production (GWh)"].cumsum().iloc[:-1].min())
    fig.update_yaxes(range=[lo * 0.96, b["Net production (GWh)"].iloc[0] * 1.02], title="Plant net production (GWh)")
    fig.update_xaxes(tickangle=-30)
    fig = _layout(fig, "From the deterministic plan to the expected outcome", height=500, showlegend=False)
    fig.update_layout(margin=dict(b=130))
    return fig


def tornado(s: pd.DataFrame, title: str):
    s = s.iloc[::-1]
    fig = go.Figure(go.Bar(x=s["Rank correlation"], y=s["Driver"], orientation="h",
                           marker_color=[GREEN if v > 0 else RED for v in s["Rank correlation"]],
                           customdata=s["Contribution to variance"],
                           hovertemplate="%{y}<br>rho %{x:.2f}<br>%{customdata:.0%} of variance<extra></extra>"))
    fig.update_xaxes(title="Rank correlation (green raises the result, red lowers it)", range=[-1, 1])
    return _layout(fig, title, height=90 + 26 * len(s), showlegend=False)


def backtest(bt: pd.DataFrame, metric="EAF (%)"):
    b = bt[bt["Metric"] == metric].reset_index(drop=True)
    lab = [f"{u}<br>{y} ({t})" for u, y, t in zip(b["Unit"], b["Year"], b["Inspection"])]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=lab, y=b["P90"] - b["P10"], base=b["P10"], marker_color="rgba(30,95,168,0.25)",
                         name="Model P10-P90", width=0.45, hovertemplate="P10 %{base:.1f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=lab, y=b["P50"], mode="markers", marker=dict(symbol="line-ew", size=26, color=BLUE,
                             line=dict(width=3, color=BLUE)), name="Model P50"))
    fig.add_trace(go.Scatter(x=lab, y=b["Actual"], mode="markers", marker=dict(size=12, color=RED), name="Actual",
                             customdata=b["Percentile of actual"],
                             hovertemplate="Actual %{y:.2f}<br>percentile %{customdata:.0%}<extra></extra>"))
    if metric.startswith("EAF"):
        fig.add_trace(go.Scatter(x=lab, y=b["Reported KPI"], mode="markers", name="Reported KPI",
                                 marker=dict(symbol="x", size=10, color=INK)))
    fig.update_yaxes(title=metric)
    return _layout(fig, f"Backtest: actual {metric.split(' ')[0]} against the model band", height=430)


def scenarios(results: dict, col="net_gwh", label="Plant net production (GWh)"):
    fig = go.Figure()
    for i, (name, d) in enumerate(results.items()):
        x = d[col]
        q = x.quantile([0.1, 0.25, 0.5, 0.75, 0.9]).values
        fig.add_trace(go.Box(name=name, q1=[q[1]], median=[q[2]], q3=[q[3]], lowerfence=[q[0]], upperfence=[q[4]],
                             mean=[x.mean()], marker_color=GREY if i == 0 else BLUE, boxpoints=False))
    fig.update_yaxes(title=label)
    return _layout(fig, "Scenarios (box P25-P75, whiskers P10-P90, dashed line = mean)", height=440, showlegend=False)


def outage_breakdown(res: dict, units: list[str]):
    cols = [("poh_h", "Planned outage", "#9FB3C2"), ("seh_h", "Outage extension", "#B07D12"),
            ("moh_h", "Maintenance outage", AMBER), ("foh_h", "Forced outage", RED),
            ("efdh_h", "Forced derating (eq.)", "#E07A5F"), ("emdh_h", "Maintenance derating (eq.)", "#E9C46A"),
            ("epdh_h", "Planned derating (eq.)", GREY)]
    fig = go.Figure()
    for c, name, color in cols:
        fig.add_trace(go.Bar(x=units, y=[res[u][c].mean() for u in units], name=name, marker_color=color,
                             hovertemplate=f"{name}: %{{y:,.0f}} h<extra></extra>"))
    fig.update_layout(barmode="stack")
    fig.update_yaxes(title="Mean hours per year")
    return _layout(fig, "Where the hours go (expected values)", height=420)


def continuous_fit(cf: pd.DataFrame, variable: str, title: str):
    d = cf[cf["variable"] == variable]
    years = [c for c in d.columns if str(c).isdigit()]
    fig = go.Figure()
    for i, (_, r) in enumerate(d.iterrows()):
        spec = r["fitted"].split("(")[1].rstrip(")").split(",")
        lo, mode, hi = [float(v) for v in spec]
        fig.add_trace(go.Scatter(x=[lo, hi], y=[r["unit"]] * 2, mode="lines", line=dict(color="rgba(30,95,168,.35)", width=14),
                                 name="Forecast range", showlegend=i == 0, hovertemplate=f"{lo:g} to {hi:g}<extra></extra>"))
        fig.add_trace(go.Scatter(x=[mode], y=[r["unit"]], mode="markers", marker=dict(symbol="line-ns", size=22,
                                 line=dict(width=3, color=BLUE)), name="Most likely (2025)", showlegend=i == 0))
        fig.add_trace(go.Scatter(x=[r[y] for y in years], y=[r["unit"]] * len(years), mode="markers+text",
                                 text=years, textposition="top center", textfont=dict(size=10),
                                 marker=dict(size=9, color=INK), name="Observed years", showlegend=i == 0))
    return _layout(fig, title, height=230)


def reconciliation(rec: pd.DataFrame):
    g = rec.groupby("item")[["failure_log", "production_data"]].sum().reset_index()
    fig = go.Figure([go.Bar(y=g["item"], x=g["failure_log"], orientation="h", name="Failure log", marker_color=BLUE),
                     go.Bar(y=g["item"], x=g["production_data"], orientation="h", name="Production data", marker_color=GREY)])
    fig.update_layout(barmode="group")
    fig.update_xaxes(title="Hours, all units and years")
    return _layout(fig, "Failure log against the monthly KPI data", height=360)
