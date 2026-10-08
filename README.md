# Kshetra

**An AI that learns from every field's past to guide its future.** Team GenZ, AgriTech hackathon.

Kshetra rebuilds a farm field's seasonal history (2017 onward) from free
satellite data (Sentinel-2 optical, Sentinel-1 radar and NISAR radar),
explains why yields went up or down, and guides the next season. Everything
it uses is free and open source. See [docs/PRD.md](docs/PRD.md) and
[docs/architecture.md](docs/architecture.md).

## Build status
| Stage | Status |
|---|---|
| 1. Repo scaffold | ✅ |
| 2. Database schema (4 memory layers) | ✅ |
| 3. Earth Engine + NISAR + weather + soil pipeline | ✅ |
| 4. ML models | ✅ |
| 5. Backend APIs | ⏳ |
| 6. LLM tool calling | ⏳ |
| 7. Frontend pages | 🟡 map + navigation only |
| 8. Voice and OCR | ⏳ |
| 9. PDF report | ⏳ |

## Repository layout
```
frontend/    React + Vite + Tailwind + Leaflet/Geoman + Recharts
backend/app/ FastAPI: api/ (routers), services/ (data sources, LLM, voice, PDF), ml/, db/
database/    schema.sql (all 4 memory layers) + local Postgres Dockerfile
notebooks/   data exploration and model training (Colab / Kaggle)
data/        raw data (gitignored)
docs/        PRD.md, architecture.md
```

## Run locally

**Option A: Docker** (database + API + web):
```bash
cp .env.example .env          # fill in the free keys you have
docker compose up --build
# API docs http://localhost:8000/docs · web http://localhost:5173
```

**Option B: without Docker**
```bash
# Database: PostgreSQL 16 with PostGIS 3 and pgvector, then
psql "$DATABASE_URL" -f database/schema.sql

# Backend (Python 3.11)
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload       # http://localhost:8000
pytest                              # DB tests need TEST_DATABASE_URL (they reset that database)

# Frontend (Node 20.19+)
cd frontend && npm install && npm run dev
```

**Using Supabase instead of local Postgres:** create a free project, open
*SQL Editor*, paste `database/schema.sql` and run it (PostGIS and pgvector are
enabled by the script). Put the *Session pooler* connection string in `DATABASE_URL`.

## Building field history (data pipeline)

```bash
earthengine authenticate              # once; uses your free non-commercial GEE project
cd backend
python -m scripts.seed_demo           # demo fields, 2017 -> yesterday
python -m scripts.seed_demo --start 2023-01-01 --limit 2   # quicker first try
```

For each field this pulls, caches in `api_cache`, and writes one row per day to `field_timeseries`:

| Source | What | Years | Key |
|---|---|---|---|
| Sentinel-2 (Earth Engine, L1C + Cloud Score+ mask) | NDVI, cloud % | 2017→ | `GEE_PROJECT` |
| Sentinel-1 (Earth Engine, GRD IW) | VV, VH backscatter (dB) | 2017→ | `GEE_PROJECT` |
| NISAR L-band GCOV (NASA ASF) | HH, HV backscatter (dB); reads only the field's pixels | mid-2025→ | `EARTHDATA_TOKEN` |
| NISAR S-band GCOV (ISRO Bhoonidhi) | HH, HV backscatter (dB) | Jul 2026→ | manual download, see below |
| Open-Meteo archive (NASA POWER fallback) | rain, temperature, ET0, soil moisture | 2017→ | none |
| SoilGrids | clay/sand/silt, SOC, pH, N, CEC, bulk density, texture | static | none |

On cloudy monsoon dates, NDVI is predicted from radar (best available: NISAR L, NISAR S, then
Sentinel-1) using a model fitted on that field's own clear-sky dates. It is used only if its
cross-validated R² ≥ 0.5, and filled values are flagged `ndvi_source = 'sar_fill'`.

**NISAR S-band files:** log in to [Bhoonidhi](https://bhoonidhi.nrsc.gov.in), open *Browse & Order*,
search your area for NISAR S-SAR GCOV products, download the `.h5` files into `data/nisar_s/`,
and re-run the seed script.

A source that fails (key missing, API down) is recorded in `fields.ingest_error`; the others still load.
The demo fields in `database/seeds/demo_fields.geojson` are 90 m squares around pins, not surveyed
boundaries: redraw them on the map before trusting field-level numbers.

**Earth Engine cost:** one request per field per year per sensor, returning only field averages:
roughly 10 years × 2 sensors = 20 small requests per field, a tiny fraction of the 150 EECU-hour monthly quota.

## Field analysis (ML models)

After ingestion, `seed_demo` also runs `analyze_field`, which writes Layer 3:

| Model | Method | Output |
|---|---|---|
| Season detection (F2) | Humps in smoothed NDVI; sowing from radar puddling signal (paddy) or green-up − 15 days | `seasons`: sowing, peak, harvest dates; `in_progress` |
| Crop detection (F3) | Phenology rules × district crop-area prior (+ trained model once farmers confirm 20+ seasons) | crop, confidence, alternatives; < 0.60 = "uncertain" |
| Stress detection (F4) | Dry spells (only where rain is normally expected), heavy rain + radar standing water, sudden NDVI drops, heat at flowering | `events` with evidence numbers |
| Yield (F5) | XGBoost quantile models (P10/P50/P90) when trained; otherwise district yield history × greenness vs the field's usual | range in t/ha, never one number |
| Likely reasons (F6) | SHAP on the P50 model; baseline: greenness + stress events | `seasons.shap_reasons`, worded "likely" |
| Field twins (F7) | k-NN with pgvector on scaled soil, timing, greenness and weather | 5 nearest field-seasons + what they did differently |

Training data and models:
```bash
cd backend
# 1. District crop statistics (free downloads, see scripts/load_reference.py)
python -m scripts.load_reference apy ../data/district_apy.csv      # Ministry APY / data.gov.in (2017+)
python -m scripts.load_reference icrisat ../data/icrisat_dld.csv   # ICRISAT DLD (history to ~2017)
# 2. Train (needs 30+ confident field-seasons with district yields), then refresh all fields
python -m scripts.train_models
python -m scripts.analyze_all
```
Or use `notebooks/01_field_history_and_models.ipynb` on free Colab/Kaggle. Trained models are saved
in `backend/models/` (gitignored).

**Honest limits.** No free field-level yield data exists for India, so yields are trained on district
averages and shown as ranges. Black gram and green gram look identical from space and are reported as
"pulses". Crop rules use approximate published crop calendars for coastal Andhra Pradesh; other
regions need their own ranges in `ml/crop_classifier.py`.

## Getting the free keys
None of these need a credit card.

| Variable | Where | Notes |
|---|---|---|
| `GEE_PROJECT` | [code.earthengine.google.com/register](https://code.earthengine.google.com/register) → *Unpaid usage* → *Academia/research or non-profit/hackathon* → create a Cloud project | Keep the project on the **Community tier** (150 EECU-hours/month). The Contributor tier needs a billing account, so don't pick it. Then run `earthengine authenticate`. |
| `GEMINI_API_KEY` | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | Free tier covers Flash / Flash-Lite models; check live limits in AI Studio. Free-tier prompts may be used to improve Google products, so we only send aggregated field numbers. |
| `GROQ_API_KEY` | [console.groq.com/keys](https://console.groq.com/keys) | Free tier, per-model limits at console.groq.com/settings/limits. |
| `SUPABASE_URL`, `SUPABASE_KEY` | [supabase.com](https://supabase.com) → New project → *Project Settings → API* | Free: 500 MB DB. **Pauses after 7 days idle**; restore it from the dashboard before a demo. |
| `DATA_GOV_API_KEY` | [data.gov.in](https://data.gov.in) → sign up → *My Account → API key* | Agmarknet mandi prices and crop statistics. |
| `BHASHINI_KEY` | [bhashini.gov.in](https://bhashini.gov.in) → ULCA sign up → generate API key | Approval can take a few days; apply early. Local Whisper is the fallback. |
| `EARTHDATA_TOKEN` | [urs.earthdata.nasa.gov](https://urs.earthdata.nasa.gov) → register → *Generate Token* | NISAR L-band products (ASF DAAC). |
| `BHOONIDHI_USERNAME`, `BHOONIDHI_PASSWORD` | [bhoonidhi.nrsc.gov.in](https://bhoonidhi.nrsc.gov.in) → register | NISAR S-band products (ISRO open data). |

No key needed: Open-Meteo, NASA POWER, SoilGrids, Ollama (local).

## Free-tier limits to know
- **Earth Engine Community tier**: 150 EECU-hours/month per project; beyond it, requests still run but slowly. Re-verify non-commercial status yearly.
- **Supabase free**: 500 MB database, pauses after 7 idle days. Timeseries are stored as field averages (not rasters) to stay small.
- **Hosting**: Hugging Face Spaces free CPU (16 GB RAM) is recommended for the API because Whisper and the embedding model don't fit in Render's 512 MB free instance. Render free sleeps after 15 min idle.
- **Vercel Hobby**: non-commercial use only.
- **LLMs**: Groq and Gemini free tiers rate-limit per minute and per day; Ollama with Qwen2.5 is the offline fallback.

## License
MIT. All dependencies are open source (MIT / Apache-2.0 / BSD / GPL / LGPL).
