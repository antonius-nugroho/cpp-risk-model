# Changelog

## v3.6 – BPP as Biaya Pokok Penyediaan; Opportunity loss
- BPP means Biaya Pokok Penyediaan throughout; config key `energy_value_rp_kwh` is now `bpp_rp_kwh`
  (older configs still load)
- Lost net energy × BPP is reported as the **Opportunity loss** (`opportunity_loss_rp_bn`) instead of a
  "value of lost energy"; the dashboard's lost-energy panel shows it in rupiah
- Data preview: a "Harga" tab shows the loaded pricing file

## v3.5 – Pricing file replaces BPP file
- `data/Pricing.xlsx` (month, coal_price_rp_per_ton, biomass_price_rp_per_ton, bpp_rp_kwh, unit_name) replaces
  `data/BPP.xlsx`; `calibrate.py --pricing` replaces `--bpp`
- Coal and biomass prices are no longer placeholders when the file is given: each unit gets its latest-year price,
  weighted by coal / biomass burned (BPP stays weighted by net sales); `model.py` uses the unit prices for fuel cost
- Evidence sheets `prices_annual` and `prices_monthly` replace `energy_value_bpp_*`
- Streamlit: "Harga" upload and Template_Pricing.xlsx on the Data page; per-unit coal, biomass and BPP inputs on the
  Prices tab

## v3.4 – Light and dark themes
- `.streamlit/config.toml` defines `[theme.light]` and `[theme.dark]` (same control-room palette, dark variant);
  users switch in the app menu (⋮ -> Settings); the default follows the system setting
- Custom CSS and Plotly charts no longer hard-code light-mode text and background colours, so they follow the theme
- Sidebar note (in Bahasa) on where to switch the theme

## v3.3 – Streamlit app in Bahasa Indonesia
- All app text (pages, sidebar, checks, charts, table headers) is in Bahasa Indonesia
- `app_lib/i18n.py` translates the labels produced by the model code (metrics, event descriptions, scenarios,
  bridge steps, status meanings) at display time, so `calibrate.py`, `run.py` and the Excel report keep English labels
- Month names in the file checks use Indonesian abbreviations

## v3.2 – Upload templates
- Download buttons on the Data page for Failure data, Data Pengusahaan and BPP templates (`app_lib/templates.py`,
  also `python -m app_lib.templates`): empty data sheet, Columns sheet with descriptions and examples, and a
  Status Mapping sheet for the failure log
- Required-column checks now list every column the calibration reads (previously some missing columns only failed
  during calibration); BPP uploads are checked too
- "Load bundled Tarahan data" is shown only when the data files are present

## v3.1 – Value of lost energy from BPP
- `data/BPP.xlsx` (monthly BPP per unit) is matched to Data Pengusahaan by unit and calendar month
- `calibrate.py --bpp` sets `energy_value_rp_kwh` per unit (and plant) to the latest year's net-sales-weighted BPP
- Evidence sheets `energy_value_bpp_annual` and `energy_value_bpp_monthly`
- `model.py` uses the unit value, falling back to `economics.energy_value_rp_kwh`
- Streamlit: optional BPP upload on the Data page (bundled with the sample data), per-unit values on the Prices tab

## v3 – Streamlit web application
### New
- `streamlit_app.py`, `app_pages/` (Data, Build model, Model validation, Dashboard, Model resume)
- `app_lib/` – cached computation (`state.py`), interactive Plotly charts (`charts.py`), styling (`ui.py`), status codes
- `.streamlit/config.toml` theme; `tests/test_app.py` end-to-end smoke test
- Launch configuration "Web app (Streamlit)"
### Changed
- `calibrate.py` accepts uploaded files (bytes), works with or without a Status Mapping sheet, detects DMN and the
  derating reference MW from the data, handles any unit names, and adds a failure-log vs KPI reconciliation table
- `requirements.txt` adds streamlit and plotly
- The command-line tools (`calibrate.py`, `run.py`) still work as before

## v2 – calibrated on plant data (replaces the illustrative v1 model)

### New
- `calibrate.py` – builds the model inputs from the plant data in `data/`
- `data/` – Failure_Data_highlighted.xlsx, Data_Pengusahaan.xlsx, Deskripsi_Kolom_Data_Pengusahaan.xlsx
- `config/model_config.yaml` – calibrated inputs (replaces `inputs.yaml`)
- `config/calibration_evidence.xlsx` – the data behind every calibrated number
- Risk register with likelihood x consequence rating, backtest against 2023-2025,
  per-unit and plant results, production bridge, Excel report with embedded charts

### Changed
- `model.py` – unit/plant engine: EAF, EFOR, production, heat rate, coal, biomass, CO2
- `reporting.py`, `run.py` – new tables, charts and `outputs/Risk_Model_Results.xlsx`
- `distributions.py` – added gamma (uncertain event rates) and empirical distributions
- `.vscode/launch.json` – "1. Calibrate from data" and "2. Run risk model"

### Removed
- `inputs.yaml` – no longer used; delete it from your folder
- Old outputs (`outputs/results.xlsx`, old PNG charts) – delete the `outputs/` folder
