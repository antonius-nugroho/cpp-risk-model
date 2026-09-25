# PLTU Tarahan Units 3 & 4 – Calibrated Risk Model (v3, web app)

Monte Carlo risk model calibrated from the plant's own failure log and monthly
production data (2023–2025). It forecasts one year ahead (default 2026) for each
unit and for the plant, and quantifies risks, opportunities and uncertainty in
EAF, EFOR, production, heat rate, coal and CO₂.

## Web app (Streamlit)

```bash
pip install -r requirements.txt      # adds streamlit and plotly
streamlit run streamlit_app.py       # or F5 -> "Web app (Streamlit)"
```

The browser opens at http://localhost:8501 with five steps. The app is in Bahasa Indonesia (page names below in
brackets); the command-line tools and the Excel report stay in English. Light and dark themes are available in the app
menu (⋮ -> Settings -> Light / Dark); by default the app follows the system setting.

| Page | What it does |
|---|---|
| 1. Data | Upload Failure Data and Data Pengusahaan (or load the bundled Tarahan data); file checks; status mapping editor |
| 2. Build model (Bangun model) | Calibrate, adjust planned outage, targets, prices, event frequencies and scenarios; run the simulation |
| 3. Model validation (Validasi model) | Backtest against past years, failure log vs KPI reconciliation, calibration evidence |
| 4. Dashboard (Dasbor) | Annunciator KPI panel and interactive charts for the plant or each unit: outcomes, risks, drivers, scenarios |
| 5. Model resume (Ringkasan model) | Plain-language summary of outlook, risks, opportunities and validation; Excel report download |

The failure file can be the raw `Failure_Data.xlsx` (default mapping) or `Failure_Data_highlighted.xlsx`
(its *Status Mapping* sheet is used). Either way the mapping can be changed on the Data page.

## Command-line workflow in VS Code

1. Open the folder, create a venv from `requirements.txt`
   (`Ctrl+Shift+P` → *Python: Create Environment* → *Venv*).
2. **F5 → "1. Calibrate from data"** – reads `data/` and writes
   `config/model_config.yaml` and `config/calibration_evidence.xlsx`.
3. Review/edit `config/model_config.yaml` (targets, prices, planned outage, scenarios).
4. **F5 → "2. Run risk model"** – writes `outputs/Risk_Model_Results.xlsx` and charts.

Terminal equivalent: `python calibrate.py` then `python run.py [-n 5000]`.
Re-run calibration only when the data files change; editing the YAML and re-running
`run.py` is enough for what-if analysis.

## Data used

The plant data files, `config/model_config.yaml` and `config/calibration_evidence.xlsx` are not in the repository.
Put the Excel files in `data/` and run `python calibrate.py` to build the config.

To use your own plant's data, download the templates from the app's Data page (or run
`python -m app_lib.templates`, which writes them to `templates/`). Each template has the required
columns in its first sheet and a *Columns* sheet explaining every column with an example value; the
failure-log template also has an editable *Status Mapping* sheet.

| File | Used for |
|---|---|
| `data/Failure_Data_highlighted.xlsx` | Event log + *Status Mapping* sheet (only statuses with Include = Yes are modelled) |
| `data/Data_Pengusahaan.xlsx` | POH, EAF, EFDH/EMDH/EPDH, production, fuel, GCV, heat rate, plans |
| `data/Pricing.xlsx` (optional) | Monthly coal price (Rp/ton), biomass price (Rp/ton) and BPP (Rp/kWh) per unit, matched to Data Pengusahaan by unit and month. The latest year sets each unit's `coal_price_rp_t` (weighted by coal burned), `biomass_price_rp_t` (by biomass burned) and `bpp_rp_kwh`, Biaya Pokok Penyediaan (by net sales), which sets the opportunity loss = lost net energy × BPP. Without it the prices are placeholders |

## How the calibration works

- **Event merging** – log rows split at month boundaries (same unit, status and
  cause code, gap ≤ 10 min) are merged: 195 rows → 164 events.
- **Event classes** – status category (FO, MO, SE, FD, MD, PD) × failure-mode group
  from the cause-code system (tube leak, coal feeding, CFB bed/ash/refractory, fans,
  generator/exciter, cooling water, …). Classes with < 2 events go to `<cat>_other`.
- **Frequency** – Poisson per unit-year, pooled over both units (6 unit-years).
  Rate uncertainty: λ ~ Gamma(k + 0.5, 1/6), sampled each iteration.
  Outage extensions (SE): probability per inspection type (simple / serious).
- **Duration / severity** – outage hours, or equivalent derated hours
  (loss MWh ÷ 100 MW, which reproduces the reported EFDH/EMDH/EPDH within ~7 %).
  Empirical resampling for classes with ≥ 8 events; mean-matched lognormal otherwise.
- **Planned outage** – triangular from historical years of the same inspection type,
  extensions removed. Inspection type for the forecast year follows each unit's cycle.
- **Plant parameters** (per unit) – PERT with mode = latest year (2025), the best
  observed year as the upside and half the latest-vs-best gap as the downside:
  net plant heat rate, net output factor, auxiliary share, biomass co-firing share.
  Coal GCV is shared by both units. Correlations come from the monthly data.

## Outputs (`outputs/Risk_Model_Results.xlsx`)

Summary (plan vs P10/P50/P90), Targets (probability of meeting each), Risk Register
(frequency, severity, expected loss, tail effect, L×C score and rating), Production
Bridge, Sensitivity, Scenarios, Backtest, calibration evidence and the merged event list.

## Placeholders to replace

In `config/model_config.yaml`: `targets.eaf_min`, `targets.efor_max` (set to your KPI
contract) and production/coal targets (default = 2025 plan). The prices are placeholders only when no
`data/Pricing.xlsx` is given.

## Known simplifications

- Pooled event rates: both units get the same frequencies (same design). Set
  `event_rate_multiplier` per unit to reflect differences.
- FO hours classed as OMC in the KPI are still counted as lost availability; the
  backtest compares against EAF including these hours.
- Starts and biodiesel use are not modelled (≈0.2 % of heat input).
