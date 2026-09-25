"""Bahasa Indonesia for the Streamlit app.

The model code (calibrate.py, reporting.py) keeps English labels because the command-line tools and the Excel
report use them. The app translates them only when displaying: t() for single labels, df() for tables.
"""
from __future__ import annotations

import re

import pandas as pd

BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

# Labels produced by the model code -> Bahasa
TEXT = {
    # scopes, inspection types
    "Plant": "Pembangkit", "Base": "Dasar", "Calibrated forecast": "Prakiraan hasil kalibrasi",
    "simple": "sederhana", "serious": "serius", "none": "tidak ada",
    # event categories (calibrate.CAT_LABEL)
    "Forced outage": "Outage gangguan", "Maintenance outage": "Outage pemeliharaan",
    "Scheduled outage extension": "Perpanjangan outage terjadwal", "Outage slip": "Pergeseran outage",
    "Forced derating": "Derating gangguan", "Maintenance derating": "Derating pemeliharaan",
    "Planned derating": "Derating terencana",
    # failure-mode groups (calibrate.GROUP_LABEL)
    "Boiler tube leak": "Kebocoran pipa boiler", "Generator, exciter & electrical": "Generator, eksiter & kelistrikan",
    "Fans, dampers & air/gas system": "Fan, damper & sistem udara/gas",
    "Coal feeding / fuel supply to bunker": "Pengumpanan batubara / pasokan bahan bakar ke bunker",
    "CFB bed, ash, loop seal & refractory": "Bed CFB, abu, loop seal & refraktori",
    "Circulating water system": "Sistem air pendingin (circulating water)",
    "Feedwater, piping & auxiliaries": "Air umpan, perpipaan & alat bantu",
    "Unit performance limitation": "Keterbatasan kinerja unit",
    "Inspection-related (overrun / extension / derate)": "Terkait inspeksi (molor / perpanjangan / derating)",
    "External (lightning, grid)": "Eksternal (petir, jaringan)", "Other causes": "Penyebab lain", "All causes": "Semua penyebab",
    # summary metrics (reporting.METRICS)
    "Gross production (GWh)": "Produksi bruto (GWh)", "Net production / sales (GWh)": "Produksi neto / penjualan (GWh)",
    "Net energy lost to unplanned events (GWh)": "Energi neto hilang akibat kejadian tak terencana (GWh)",
    "Planned outage (h)": "Outage terencana (jam)", "Forced outage (h)": "Outage gangguan (jam)",
    "Maintenance outage (h)": "Outage pemeliharaan (jam)", "Outage extension (h)": "Perpanjangan outage (jam)",
    "EFDH (h)": "EFDH (jam)", "EMDH (h)": "EMDH (jam)", "EPDH (h)": "EPDH (jam)",
    "Net plant heat rate (kcal/kWh)": "Net plant heat rate (kcal/kWh)", "Coal consumption (kt)": "Konsumsi batubara (kt)",
    "Biomass consumption (kt)": "Konsumsi biomassa (kt)", "CO2 from coal (kt)": "CO2 dari batubara (kt)",
    "Fuel cost (Rp bn) - placeholder prices": "Biaya bahan bakar (Rp miliar) - harga sementara",
    "Value of lost energy (Rp bn) - at BPP": "Nilai energi hilang (Rp miliar) - pada BPP",
    # production bridge (reporting.loss_bridge)
    "Plan (deterministic)": "Rencana (deterministik)", "Planned outage longer than mode": "Outage terencana lebih lama dari modus",
    "Forced outages": "Outage gangguan", "Maintenance outages": "Outage pemeliharaan", "Outage extensions": "Perpanjangan outage",
    "Outage slips": "Pergeseran outage", "Forced deratings": "Derating gangguan", "Maintenance deratings": "Derating pemeliharaan",
    "Planned deratings": "Derating terencana", "Output factor & other uncertainty": "Faktor output & ketidakpastian lain",
    "Expected (mean)": "Ekspektasi (rata-rata)",
    # reconciliation items (calibrate.reconciliation)
    "Forced outage hours": "Jam outage gangguan", "Maintenance outage hours": "Jam outage pemeliharaan",
    "Forced derating eq. hours": "Jam ekuivalen derating gangguan",
    "Maintenance derating eq. hours": "Jam ekuivalen derating pemeliharaan",
    "Planned derating eq. hours": "Jam ekuivalen derating terencana",
    # scenarios (calibrate.build)
    "Tube leaks -50%": "Kebocoran pipa -50%", "Coal feeding -50%": "Pengumpanan batubara -50%",
    "Generator/exciter -50%": "Generator/eksiter -50%", "Heat rate recovery": "Pemulihan heat rate",
    "Co-firing 10%": "Co-firing 10%",
    "Tube-leak prevention (thickness survey, erosion shields) halves tube-leak frequency":
        "Pencegahan kebocoran pipa (survei ketebalan, pelindung erosi) menurunkan frekuensi kebocoran pipa separuhnya",
    "Coal handling / feeder reliability programme halves coal-feeding deratings":
        "Program keandalan coal handling / feeder menurunkan derating pengumpanan batubara separuhnya",
    "AVR/exciter reliability fix halves generator-side trips":
        "Perbaikan keandalan AVR/eksiter menurunkan trip sisi generator separuhnya",
    "Net plant heat rate brought back to each unit's best observed year":
        "Net plant heat rate dikembalikan ke tahun terbaik tiap unit",
    "Biomass share held at 8-12% of heat input on both units":
        "Porsi biomassa dijaga 8-12% dari masukan panas di kedua unit",
    # plant performance variables (calibration evidence)
    "nphr_kcal_kwh": "Net plant heat rate (kcal/kWh)", "net_output_factor": "Net output factor",
    "aux_share": "Porsi pemakaian sendiri", "cofiring_share": "Porsi co-firing",
    # sensitivity driver inputs
    "Heat rate": "Heat rate", "Net output factor": "Net output factor", "Auxiliary power share": "Porsi pemakaian sendiri",
    "Co-firing share": "Porsi co-firing", "Coal calorific value": "Nilai kalor batubara",
    "Planned outage hours": "Jam outage terencana",
}

PATTERNS = [
    (re.compile(r"^Serious inspection at (.+)$"), r"Inspeksi serius di \1"),
    (re.compile(r"^(.+) performs a serious inspection in the forecast year$"), r"\1 menjalani inspeksi serius pada tahun prakiraan"),
    (re.compile(r"^BPP (\d{4}), net-sales weighted$"), r"BPP \1, dibobot penjualan neto"),
    (re.compile(r"^(.+) events$"), r"Kejadian \1"),
]

# Column headers -> Bahasa (display only; the underlying keys stay English)
COLS = {
    # generic
    "Scope": "Cakupan", "Metric": "Metrik", "Mean": "Rata-rata", "Std dev": "Simpangan baku", "Unit": "Unit", "Year": "Tahun",
    "Description": "Deskripsi", "Category": "Kategori", "Rank": "Peringkat",
    # summary / bridge / backtest
    "Plan (deterministic)": "Rencana (deterministik)", "Step": "Tahap", "Net production (GWh)": "Produksi neto (GWh)",
    "Inspection": "Inspeksi", "Actual": "Aktual", "Reported KPI": "KPI dilaporkan",
    "Percentile of actual": "Persentil aktual", "Inside P10-P90": "Di dalam P10-P90",
    # risk register
    "Event class": "Kelas kejadian", "Events per year (plant)": "Kejadian per tahun (pembangkit)",
    "P(at least one per year)": "P(minimal satu per tahun)", "Mean eq. hours per event": "Rata-rata jam ekuivalen per kejadian",
    "Mean net MWh lost per event": "Rata-rata MWh neto hilang per kejadian",
    "Expected eq. hours per year (plant)": "Ekspektasi jam ekuivalen per tahun (pembangkit)",
    "Expected EAF impact (pp, plant)": "Ekspektasi dampak EAF (poin %, pembangkit)",
    "Expected net energy loss (GWh/yr)": "Ekspektasi energi neto hilang (GWh/thn)",
    "P90 annual loss from this class (GWh)": "Kehilangan tahunan P90 dari kelas ini (GWh)",
    "Effect on P10 plant production (GWh)": "Efek pada produksi P10 pembangkit (GWh)",
    "Share of expected event loss": "Porsi dari ekspektasi kehilangan", "Likelihood score (1-5)": "Skor kemungkinan (1-5)",
    "Consequence score (1-5)": "Skor dampak (1-5)", "Risk score": "Skor risiko", "Rating": "Tingkat",
    # scenarios
    "Scenario": "Skenario", "Mean EAF (%)": "Rata-rata EAF (%)", "Mean net GWh": "Rata-rata GWh neto",
    "P10 net GWh": "P10 GWh neto", "P90 net GWh": "P90 GWh neto",
    "Delta mean net GWh vs base": "Selisih rata-rata GWh neto vs dasar",
    "Delta P10 net GWh vs base": "Selisih P10 GWh neto vs dasar", "P(gross >= plan)": "P(bruto >= rencana)",
    "Mean NPHR (kcal/kWh)": "Rata-rata NPHR (kcal/kWh)", "Mean coal (kt)": "Rata-rata batubara (kt)",
    "Mean CO2 (kt)": "Rata-rata CO2 (kt)", "Delta coal (kt) vs base": "Selisih batubara (kt) vs dasar",
    # calibration evidence
    "unit": "Unit", "year": "Tahun", "item": "Item", "failure_log": "Log gangguan", "production_data": "Data produksi",
    "production_field": "Kolom data produksi", "difference": "Selisih", "difference %": "Selisih %",
    "event_class": "Kelas kejadian", "category": "Kategori", "impact": "Dampak", "description": "Deskripsi",
    "events": "Kejadian", "exposure_unit_years": "Eksposur (unit-tahun)", "rate_per_unit_year": "Laju per unit-tahun",
    "occurrence_model": "Model kejadian", "mean_hours_or_eq_hours": "Rata-rata jam (atau jam ekuivalen)",
    "median": "Median", "max": "Maks", "total_loss_mwh": "Total kehilangan (MWh)", "duration_model": "Model durasi",
    "fitted_mean": "Rata-rata hasil fit", "fitted_sd": "Simpangan baku hasil fit", "cap": "Batas atas",
    "inspection_type": "Jenis inspeksi", "POH_reported": "POH dilaporkan", "extension_hours": "Jam perpanjangan",
    "planned_hours_model": "Jam terencana (model)", "status": "Status", "start": "Mulai", "stop": "Selesai",
    "hours": "Jam", "loss_mwh": "Kehilangan (MWh)", "loss_mw": "Kehilangan (MW)", "cause_code": "Kode penyebab",
    "source_rows": "Baris sumber", "group": "Kelompok", "impact_type": "Jenis dampak", "eq_hours": "Jam ekuivalen",
    "variable": "Variabel", "variable_a": "Variabel A", "variable_b": "Variabel B", "rho": "rho", "fitted": "Distribusi",
}

# Status code meanings (app_lib.status_codes) -> Bahasa
STATUS_MEANING = {
    "Reserve Shutdown": "Reserve shutdown (siaga)", "Non Curtailing": "Tidak mengurangi daya", "Planned Outage": "Outage terencana",
    "Maintenance Outage": "Outage pemeliharaan", "Planned Outage Extension": "Perpanjangan outage terencana",
    "Maintenance Outage Extension": "Perpanjangan outage pemeliharaan", "Forced Outage": "Outage gangguan",
    "Forced Outage.Outage Slip": "Outage gangguan - pergeseran outage", "Forced Outage.System": "Outage gangguan - sistem/jaringan",
    "Forced Outage.Environment": "Outage gangguan - lingkungan", "Forced Outage.Fuel": "Outage gangguan - kekurangan bahan bakar",
    "Forced Outage.Force Majeure": "Outage gangguan - keadaan kahar", "Forced Outage.Others": "Outage gangguan - eksternal lain",
    "Startup Failure": "Gagal start", "Planned Derated": "Derating terencana", "Maintenance Derated": "Derating pemeliharaan",
    "Planned Derated Extension": "Perpanjangan derating terencana", "Maintenance Derated Extension": "Perpanjangan derating pemeliharaan",
    "Forced Derated": "Derating gangguan", "Forced Derated.Derating Slip": "Derating gangguan - pergeseran derating",
    "Forced Derated.System": "Derating gangguan - sistem/jaringan", "Forced Derated.Environment": "Derating gangguan - lingkungan",
    "Forced Derated.Fuel": "Derating gangguan - kekurangan bahan bakar",
    "Forced Derated.Major Problem": "Derating gangguan - masalah besar", "Forced Derated.Others": "Derating gangguan - eksternal lain",
    "Forced Derated Reserve Shutdown": "Derating gangguan saat reserve shutdown", "Seasonal Derated": "Derating musiman",
    "Start Up Derating": "Derating saat start up", "Shutdown Derating": "Derating saat shutdown",
    "Not in status list": "Tidak ada di daftar status",
}


def t(s):
    """Translate one label; 'A - B' labels are translated part by part. Unknown text is returned unchanged."""
    if not isinstance(s, str):
        return s
    if s in TEXT:
        return TEXT[s]
    if s in STATUS_MEANING:
        return STATUS_MEANING[s]
    for pat, rep in PATTERNS:
        if pat.match(s):
            return pat.sub(rep, s)
    if " - " in s:
        return " - ".join(TEXT.get(p, p) for p in s.split(" - "))
    return s


def df(d: pd.DataFrame, values=(), index=False) -> pd.DataFrame:
    """Copy of a table with Bahasa column headers; `values` columns (and the index, if asked) are translated too."""
    d = d.copy()
    for c in values:
        if c in d.columns:
            d[c] = d[c].map(t)
    if index:
        d.index = d.index.map(t)
        d.index.name = COLS.get(d.index.name, d.index.name)
    return d.rename(columns=lambda c: COLS.get(c, t(c)) if isinstance(c, str) else c)


def col(name: str) -> str:
    return COLS.get(name, name)


def month(ts, day=False) -> str:
    """'Jan 2023' / '31 Jan 2023' with Indonesian month abbreviations."""
    ts = pd.Timestamp(ts)
    return f"{ts.day} {BULAN[ts.month - 1]} {ts.year}" if day else f"{BULAN[ts.month - 1]} {ts.year}"

