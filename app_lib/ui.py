"""Visual language: a quiet control-room interface.

Palette      steel ink #1D2B36, turbine-hall grey #F3F5F6, panel #E4E9EC,
             grid blue #1E5FA8; signal colours green #2F8F5B, amber #D99A1E, red #C4412D
Type         Barlow (signage-derived, industrial) for text, Barlow Semi Condensed for figures
Signature    the annunciator panel: KPI windows lit by the probability of meeting target
"""
from __future__ import annotations

import html

import streamlit as st

INK, PAPER, PANEL, BLUE = "#1D2B36", "#F3F5F6", "#E4E9EC", "#1E5FA8"
GREEN, AMBER, RED, GREY = "#2F8F5B", "#D99A1E", "#C4412D", "#8A969E"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700&family=Barlow+Semi+Condensed:wght@500;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, .stText, p, li, label, input, textarea, button, select {{
  font-family: 'Barlow', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
}}
h1, h2, h3 {{ font-family: 'Barlow', 'Segoe UI', sans-serif; color: {INK}; letter-spacing: -0.01em; }}
h1 {{ font-weight: 700; font-size: 2.1rem; }}
h2 {{ font-weight: 600; font-size: 1.45rem; }}
h3 {{ font-weight: 600; font-size: 1.15rem; }}
.block-container {{ padding-top: 2.2rem; max-width: 1320px; }}
.lede {{ font-size: 1.08rem; color: #41525E; max-width: 72ch; line-height: 1.5; margin-bottom: 1.2rem; }}
.fig {{ font-family: 'Barlow Semi Condensed', 'Barlow', sans-serif; font-variant-numeric: tabular-nums; }}

/* annunciator panel */
.annunciator {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 6px; background: {INK}; padding: 6px; border-radius: 6px; margin: 0.4rem 0 1.4rem 0; }}
.window {{ background: #2A3A46; border-radius: 3px; padding: 12px 14px 11px 14px; color: #C9D3DA;
  border-top: 3px solid #3B4B57; min-height: 108px; }}
.window.green {{ border-top-color: {GREEN}; background: linear-gradient(180deg, rgba(47,143,91,.28), #2A3A46 70%); }}
.window.amber {{ border-top-color: {AMBER}; background: linear-gradient(180deg, rgba(217,154,30,.30), #2A3A46 70%); }}
.window.red   {{ border-top-color: {RED};   background: linear-gradient(180deg, rgba(196,65,45,.34), #2A3A46 70%); }}
.window .name {{ font-size: 0.86rem; color: #AFBCC5; }}
.window .value {{ font-family: 'Barlow Semi Condensed', sans-serif; font-weight: 600; font-size: 1.9rem;
  color: #FFFFFF; line-height: 1.15; font-variant-numeric: tabular-nums; }}
.window .range {{ font-size: 0.82rem; color: #AFBCC5; font-variant-numeric: tabular-nums; }}
.window .signal {{ font-size: 0.84rem; margin-top: 4px; color: #FFFFFF; }}

/* checklist rows */
.check {{ display: grid; grid-template-columns: 14px 1fr auto; gap: 10px; align-items: baseline;
  padding: 6px 0; border-bottom: 1px solid {PANEL}; font-size: 0.95rem; }}
.check .dot {{ width: 9px; height: 9px; border-radius: 50%; background: {GREEN}; display: inline-block; }}
.check .dot.warn {{ background: {AMBER}; }} .check .dot.info {{ background: {GREY}; }} .check .dot.bad {{ background: {RED}; }}
.check .val {{ color: #41525E; text-align: right; font-variant-numeric: tabular-nums; }}

.resume p {{ max-width: 76ch; line-height: 1.55; font-size: 1.02rem; }}
section[data-testid="stSidebar"] .stepline {{ font-size: 0.92rem; padding: 3px 0; color: #41525E; }}
@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; animation: none !important; }} }}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def lede(text: str):
    st.markdown(f'<p class="lede">{html.escape(text)}</p>', unsafe_allow_html=True)


def signal_class(p: float | None) -> str:
    if p is None:
        return ""
    return "green" if p >= 0.7 else "amber" if p >= 0.4 else "red"


def annunciator(windows: list[dict]):
    """windows: {name, value, range, prob (0-1 or None), signal}"""
    cells = []
    for w in windows:
        cls = w.get("cls") or signal_class(w.get("prob"))
        cells.append(
            f'<div class="window {cls}"><div class="name">{html.escape(w["name"])}</div>'
            f'<div class="value">{html.escape(w["value"])}</div>'
            f'<div class="range">{html.escape(w.get("range", ""))}</div>'
            f'<div class="signal">{html.escape(w.get("signal", ""))}</div></div>')
    st.markdown(f'<div class="annunciator" role="list">{"".join(cells)}</div>', unsafe_allow_html=True)


def checklist(rows):
    """rows: (label, value, level) with level in ok / warn / info / bad"""
    out = "".join(
        f'<div class="check"><span class="dot {lvl}" aria-label="{lvl}"></span>'
        f'<span>{html.escape(label)}</span><span class="val">{html.escape(str(val))}</span></div>'
        for label, val, lvl in rows)
    st.markdown(out, unsafe_allow_html=True)


def need(stage: str):
    """Stop the page with a pointer to the step that is missing."""
    from app_lib import state
    s = state.status()
    msgs = {
        "data": ("Upload the failure data and the production data first.", "app_pages/1_data.py", "Go to Data"),
        "calibration": ("Build the model first: calibrate it from the uploaded data.", "app_pages/2_build.py", "Go to Build model"),
        "results": ("Run the simulation first.", "app_pages/2_build.py", "Go to Build model"),
    }
    for step in ["data", "calibration", "results"]:
        if not s[step]:
            msg, page, label = msgs[step]
            st.info(msg)
            st.page_link(page, label=label, icon=":material/arrow_forward:")
            st.stop()
        if step == stage:
            return


def sidebar_status():
    from app_lib import state
    s = state.status()
    with st.sidebar:
        st.markdown("#### Model status")
        lines = [("Data loaded", s["data"]), ("Model calibrated", s["calibration"]), ("Simulation run", s["results"])]
        for label, ok in lines:
            mark = "●" if ok else "○"
            color = GREEN if ok else GREY
            st.markdown(f'<div class="stepline"><span style="color:{color}">{mark}</span> {label}</div>',
                        unsafe_allow_html=True)
        r = state.get("results")
        if r:
            st.caption(f"{r['n']:,} iterations, seed {r['seed']}")
        if s["data"] and st.button("Start over", width="stretch"):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()


INPUT_LABELS = {
    "nphr_kcal_kwh": "Heat rate", "net_output_factor": "Net output factor", "aux_share": "Auxiliary power share",
    "cofiring_share": "Co-firing share", "coal_gcv_kcal_kg": "Coal calorific value", "planned_outage_hours": "Planned outage hours",
}


def driver_label(name: str, descriptions: dict | None = None) -> str:
    """'events: FO_tube_leak' -> 'Forced outage - Boiler tube leak (events)';
    'net_output_factor[Unit 3]' -> 'Net output factor, Unit 3'."""
    if name.startswith("events: "):
        cls = name[len("events: "):]
        return f"{(descriptions or {}).get(cls, cls)} (events)"
    base, _, unit = name.partition("[")
    label = INPUT_LABELS.get(base, base.replace("_", " "))
    return f"{label}, {unit.rstrip(']')}" if unit else label


def fmt(x, digits=1):
    return f"{x:,.{digits}f}"
