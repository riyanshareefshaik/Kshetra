# Kshetra

**An AI that learns from every field's past to guide its future.** Team GenZ, AgriTech hackathon.

Kshetra rebuilds a farm field's seasonal history (2017 onward) from free satellite data
(Sentinel-2 optical, Sentinel-1 radar and NASA-ISRO **NISAR** radar), explains why yields went
up or down, and guides the next season — in Telugu, Hindi and English. Everything it uses is
free and open source. See [docs/PRD.md](docs/PRD.md) and [docs/architecture.md](docs/architecture.md).

| | Feature | Where |
|---|---|---|
| F1 | Draw a field, or drop a pin and get a boundary from Sentinel-2 segmentation | Map |
| F2 | Season timeline: sowing / peak / harvest from NDVI, radar fills monsoon cloud gaps | Timeline |
| F3 | Crop per season with confidence; < 60% shown as "uncertain"; farmer can confirm | Timeline |
| F4 | Stress: dry spells, waterlogging/flood, sudden damage, heat at flowering | Timeline |
| F5 | Yield as a range (t/ha), forecasts for crops still in the field | Timeline, Why |
| F6 | "Likely reasons" from SHAP (never "causes") | Why & Twins |
| F7 | 5 most similar fields and what they did differently | Why & Twins |
| F8 | What-if sliders → yield, risk, profit in well under a second | What-If |
| F9 | Top 3 crop + variety options for next season | Planner |
| F10 | Voice/text Q&A, answers only from tool calls on your data, with sources, or "I don't know" | Ask Your Field |
| F11 | Voice farm diary → structured records; seed packet OCR | Diary |
| F12 | One-click PDF for loans and PMFBY claims | Report |
| F13 | Data sharing off by default; anonymised when on | Report |
| F14 | Seed company dashboard, aggregates of 5+ fields only | Insights (linked from Report) |
| F15 | Works offline and installs like an app (PWA): saved pages, data and map tiles | everywhere |
| F16 | 7-day weather alerts: heavy rain, heat, cold, wind, best spraying day, harvest window | Today |
| F17 | Irrigation advisor: FAO-56 water balance with soil, crop stage, forecast and diary irrigations | Today |
| F18 | Pest and disease risk from weather for paddy, cotton, chilli, maize, pulses, sugarcane | Today |
| F19 | Fertilizer calculator: urea/DAP/MOP bags and cost from Soil Health Card ratings (card photo OCR) | Fertilizer |
| F20 | When and where to sell: price trend, usual best month, nearby mandis by price and distance | Market |
| F21 | PMFBY claim helper: flags damage, 72-hour deadline, helpline 14447, evidence PDF | Report & Claims |
| F22 | Government scheme finder matched to the farmer (central + Andhra Pradesh) | Schemes |
| F23 | Farmer group / FPO dashboard with join codes and opt-out sharing | Group |
| F24 | Login with an email magic link (Supabase Auth); each farmer sees only their own fields | sign-in |
| F25 | Every screen in Telugu, Hindi and English, with voice navigation (say "ఎరువులు", "मंडी", "today") | header 🎤 |

## Quick start

```bash
git clone https://github.com/riyanshareefshaik/Kshetra.git && cd Kshetra
cp .env.example .env                               # add at least GEE_PROJECT (see "Getting the free keys")
earthengine authenticate                           # once (pip install earthengine-api)
docker compose up --build -d                       # Postgres+PostGIS+pgvector, API, web
# open http://localhost:5173  (API docs: http://localhost:8000/docs)
```

The app starts empty. On the **Map** page, draw your field (or drop a pin); Kshetra builds its
history from satellite and weather data in the background (a few minutes), then every page fills in.

### Without Docker

```bash
# Database: PostgreSQL 16 with PostGIS 3 and pgvector
psql "$DATABASE_URL" -f database/schema.sql

# Backend (Python 3.11)
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt          # add requirements-ai.txt for local embeddings + Whisper
uvicorn app.main:app --reload                # http://localhost:8000/docs
TEST_DATABASE_URL=postgresql://... pytest    # tests reset that database: use a throwaway one

# Frontend (Node 20.19+)
cd frontend && npm install && npm run dev    # http://localhost:5173
```

System packages for PDF and OCR (already in the Docker images):
`apt install libpango-1.0-0 libpangoft2-1.0-0 tesseract-ocr tesseract-ocr-tel tesseract-ocr-hin`.

## Login (optional)

Without login (`AUTH_MODE=none`, the default) Kshetra is single-user: good for one farmer, a
kiosk or a demo. To give every farmer their own account:

1. In Supabase: *Authentication → Sign In / Providers → Email* (on by default). Under
   *Authentication → URL Configuration* set the Site URL to your app (e.g. `https://<app>.vercel.app`).
2. API: `AUTH_MODE=supabase` and `SUPABASE_URL`. Projects with a legacy shared JWT secret also set
   `SUPABASE_JWT_SECRET`; newer projects are verified with their public keys automatically.
3. App: `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` (the anon key is public by design).

Supabase Auth's free tier covers 50,000 monthly users, but its built-in email sender only allows a
few emails per hour; for real use connect any free SMTP provider in *Authentication → Emails*.

## Real fields: building history

```bash
earthengine authenticate                      # once, with your free non-commercial project
cd backend
python -m scripts.load_reference apy ../data/district_apy.csv      # district yields (see below)
python -m scripts.refresh_fields                                   # update every field (also done from the app)
python -m scripts.fetch_prices                                     # today's mandi prices (run daily)
python -m scripts.train_models && python -m scripts.analyze_all    # once 30+ confident seasons exist
```

Or add fields in the app: every new field is ingested and analysed in the background
(FastAPI BackgroundTasks). Each external response is cached in `api_cache`, so a field that was
built once never needs the network again — the demo runs offline.

| Source | What | Years | Key |
|---|---|---|---|
| Sentinel-2 (Earth Engine, L1C + Cloud Score+) | NDVI, cloud % | 2017→ | `GEE_PROJECT` |
| Sentinel-1 (Earth Engine, GRD IW) | VV, VH backscatter | 2017→ | `GEE_PROJECT` |
| NISAR L-band GCOV (NASA ASF) | HH, HV backscatter; only the field's pixels are downloaded | mid-2025→ | `EARTHDATA_TOKEN` |
| NISAR S-band GCOV (ISRO Bhoonidhi) | HH, HV backscatter; put downloaded `.h5` files in `data/nisar_s/` | Jul 2026→ | Bhoonidhi account |
| Open-Meteo archive, NASA POWER fallback | rain, temperature, ET0, soil moisture | 2017→ | none |
| SoilGrids | texture, clay/sand/silt, SOC, pH, N, CEC | static | none |
| Ministry APY / ICRISAT district data | district yields (model labels, baseline, crop prior) | ICRISAT to ~2017, APY recent | none (download) |
| Agmarknet via data.gov.in | mandi prices; MSP 2026-27 fallback | daily | `DATA_GOV_API_KEY` |

District yield files: download district-wise crop area/production/yield for your state as CSV
from [data.desagri.gov.in](https://data.desagri.gov.in) or the data.gov.in "District-wise,
season-wise crop production statistics" dataset, and/or the ICRISAT District Level Database.

## Getting the free keys
None of these need a credit card. Put them in `.env` (never commit it).

| Variable | Where | Notes |
|---|---|---|
| `GEE_PROJECT` | [code.earthengine.google.com/register](https://code.earthengine.google.com/register) → *Unpaid usage* → non-commercial → create a Cloud project | Keep the **Community tier** (150 EECU-hours/month, no billing account). The Contributor tier needs billing — don't pick it. Then `earthengine authenticate`. |
| `EE_SERVICE_ACCOUNT_KEY` | Cloud console → IAM → Service accounts → create → Keys → JSON; register it for Earth Engine in the same project | Servers only (Hugging Face / Render). Paste the JSON as a secret. |
| `GROQ_API_KEY` | [console.groq.com/keys](https://console.groq.com/keys) | Default model `openai/gpt-oss-120b` (Apache-2.0 weights). Limits per org at console.groq.com/settings/limits. |
| `GEMINI_API_KEY` | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | Free tier covers Flash models; limits change, check AI Studio. Free-tier prompts may be used by Google, so only field numbers are sent — never names or phones. |
| `SUPABASE_URL`, `SUPABASE_KEY`, `DATABASE_URL` | [supabase.com](https://supabase.com) → New project. Run `database/schema.sql` in *SQL Editor*; copy the *Session pooler* string into `DATABASE_URL` | 500 MB free; **pauses after 7 idle days** — restore it from the dashboard before a demo. |
| `DATA_GOV_API_KEY` | [data.gov.in](https://data.gov.in) → sign up → *My Account → API key* | Agmarknet prices. |
| `BHASHINI_KEY`, `BHASHINI_USER_ID` | [bhashini.gov.in](https://bhashini.gov.in) → ULCA sign-up → profile → generate API key | Approval can take days. Without it: browser speech, then local Whisper. |
| `EARTHDATA_TOKEN` | [urs.earthdata.nasa.gov](https://urs.earthdata.nasa.gov) → *Generate Token* | NISAR L-band. |
| `BHOONIDHI_USERNAME/PASSWORD` | [bhoonidhi.nrsc.gov.in](https://bhoonidhi.nrsc.gov.in) → register | NISAR S-band downloads. |

No key needed: Open-Meteo, NASA POWER, SoilGrids, Ollama (`ollama pull qwen2.5:7b` for offline Q&A).

## Deploy (free tiers)

1. **Database — Supabase:** create a project, run `database/schema.sql` in the SQL Editor.
2. **API — Hugging Face Spaces (Docker, free CPU 16 GB):** create a Space with SDK *Docker*; push
   this repo's `Dockerfile`, `backend/`, `database/` and `deploy/huggingface-README.md` (renamed
   to `README.md`). Add the `.env.example` variables as Space secrets, including
   `CORS_ORIGINS=https://<your-app>.vercel.app`. Free Spaces sleep after ~48 h without visits.
   *Alternative:* Render free (`render.yaml`, 512 MB, set `WITH_AI=0`, sleeps after 15 min idle).
3. **Web — Vercel (Hobby, non-commercial):** import the repo, root directory `frontend`, set
   `VITE_API_URL=https://<your-space>.hf.space`. `frontend/vercel.json` handles page routes.
4. **CI — GitHub Actions** (`.github/workflows/ci.yml`): lint, 87 backend tests on PostGIS +
   pgvector, frontend build. Free for public repos; private repos get 2,000 free minutes/month.

Before a demo: open the Space (wakes it), restore Supabase if paused, and make sure your
fields were ingested while online.

## Free-tier limits to know
- **Earth Engine Community tier:** 150 EECU-hours/month per project. Kshetra makes ~20 small
  requests per field (10 years × 2 sensors) plus one for an auto-boundary. Over the limit, requests
  still run, slowly. Re-verify non-commercial status yearly.
- **Supabase:** 500 MB (≈ 0.5 MB per field-decade of daily rows); pauses after 7 idle days.
- **Groq / Gemini:** per-minute and per-day request limits; the app falls back Groq → Gemini →
  Ollama, and says "I don't know" if none answers.
- **Hugging Face Spaces:** sleeps when idle; first request after waking takes ~1 minute.
- **Vercel Hobby and Open-Meteo:** non-commercial use only.
- **Bhashini:** needs approval; **gTTS** uses an unofficial endpoint (used only if the browser has
  no Telugu/Hindi voice).
- **OpenStreetMap Nominatim** (mandi distances): 1 request per second; every lookup is cached forever.
- **Open-Meteo forecast** (Today page): cached 3 hours per field; free for non-commercial use.

## Repository layout
```
frontend/    React + Vite + Tailwind + Leaflet/Geoman + Recharts (14 pages), PWA service worker
backend/app/ api/ (one router per feature, auth) · services/ (Earth Engine, NISAR, weather, forecast,
             soil, prices, market, claims, schemes, LLM + tools, memory, voice, OCR, PDF, boundary, cache, ingest)
             ml/ (gap fill, seasons, features, crop, stress, yield, SHAP, twins, simulator,
             advisory, irrigation, fertilizer)
backend/scripts/  refresh_fields, load_reference, fetch_prices, train_models, analyze_all
database/    schema.sql (4 memory layers), seeds/, Dockerfile (local PostGIS + pgvector)
notebooks/   Colab/Kaggle notebook: plot a field, train the yield model
docs/        PRD.md, architecture.md
```

## Honest limits
- **No free field-level yield data exists for India.** The yield model learns from district averages,
  so every yield is a range. Until a model is trained, yields come from district history adjusted by
  the field's greenness.
- **Crop rules** use approximate published crop calendars for coastal Andhra Pradesh; black gram and
  green gram look identical from space and are reported as "pulses". Farmer confirmations override.
- **Pest risk** is from weather only, and **irrigation** uses standard FAO-56 crop and soil values:
  both are guidance, not a diagnosis or a soil-moisture measurement.
- **Fertilizer** doses are standard package-of-practices values adjusted by Soil Health Card ratings;
  MOP price is approximate. **Schemes** change: every card links to the official site.
- **What-if and planner** apply rule-based nitrogen and irrigation effects, and seed/other costs in
  `database/seeds/crop_varieties.csv` are rough estimates — edit them with real CACP figures.
  Assumptions are listed next to every result.
- Not yet run against live Earth Engine / NISAR / Bhashini from this repo's CI (they need your keys);
  those clients are tested against recorded-format responses.

## License
MIT. Every dependency is open source: FastAPI, psycopg, NumPy, pandas, SciPy, scikit-learn (BSD),
XGBoost, earthengine-api, Tesseract, sentence-transformers (Apache-2.0), SHAP, faster-whisper, gTTS,
pyproj (MIT), WeasyPrint, Shapely, h5py, Jinja2 (BSD), React, Vite, Tailwind, Leaflet, Recharts (MIT),
Leaflet-Geoman free (MIT), PostGIS (GPL-2.0), pgvector (PostgreSQL License). Data: Copernicus
Sentinel (free and open), NISAR (open data), SoilGrids (CC-BY 4.0), Open-Meteo (CC-BY 4.0),
Government of India open data (GODL).
