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
| 3. Earth Engine + NISAR + weather + soil pipeline | ⏳ |
| 4. ML models | ⏳ |
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
pytest

# Frontend (Node 20.19+)
cd frontend && npm install && npm run dev
```

**Using Supabase instead of local Postgres:** create a free project, open
*SQL Editor*, paste `database/schema.sql` and run it (PostGIS and pgvector are
enabled by the script). Put the *Session pooler* connection string in `DATABASE_URL`.

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
