# Kshetra — Architecture

```
 React + Vite (Vercel)          FastAPI (Hugging Face Spaces / Render)          Postgres (Supabase)
 ┌──────────────────┐  HTTPS   ┌──────────────────────────────────┐  SQL   ┌───────────────────────┐
 │ Map  Timeline    │ ───────▶ │ api/  one router per feature     │ ─────▶ │ L1 fields (PostGIS)   │
 │ Why  What-If     │          │ ml/   seasons, crop, yield, SHAP,│        │ L2 field_timeseries   │
 │ Planner Ask      │          │       twins                      │        │ L3 seasons, events,   │
 │ Diary Report     │          │ services/ EE, NISAR, weather,    │        │    diary_entries      │
 └──────────────────┘          │   soil, prices, LLM tools, voice,│        │ L4 semantic_memory    │
                               │   OCR, PDF                       │        │    (pgvector)         │
                               └───────────────┬──────────────────┘        │ caches + reference    │
                                               │ BackgroundTasks           └───────────────────────┘
                     ┌─────────────────────────┴───────────────────────────┐
                     │ Earth Engine (S2, S1) · ASF/Earthdata (NISAR L)      │
                     │ Bhoonidhi (NISAR S) · Open-Meteo · NASA POWER         │
                     │ SoilGrids · data.gov.in (Agmarknet, yields) · ICRISAT │
                     │ Groq / Gemini free tier · Ollama (Qwen2.5) offline    │
                     └──────────────────────────────────────────────────────┘
```

## Request flow: "add a field"
1. Frontend sends the polygon (or a pin; backend proposes a boundary).
2. `fields` row inserted; a BackgroundTask starts ingestion.
3. Ingestion pulls each source once, stores raw responses in `api_cache`,
   and writes one row per field per date into `field_timeseries`.
4. ML stage detects seasons, crops, stress events and yield ranges, and writes `seasons` and `events`.
5. All pages read only from Postgres, so the demo works without live APIs.

## Satellite fusion
- **Sentinel-2 NDVI**: cloud-masked (SCL + s2cloudless), field-mean every pass.
- **Sentinel-1 VV/VH** (dB): field-mean every pass, speckle reduced by averaging over the polygon.
- **NISAR**: L-band GCOV (HH, HV) from ASF via Earthdata; S-band GCOV from Bhoonidhi. Field-mean backscatter.
- Gaps in NDVI during cloudy periods are filled by a regression from radar
  features to NDVI, fitted per region on dates where both exist. Filled
  values are flagged (`ndvi_source = 'sar_fill'`) and shown differently in the UI.

## LLM (F10)
The model sees only tool results. Tools: `get_field_summary`, `get_season`,
`get_yield_explanation`, `find_field_twins`, `search_diary`, `run_what_if`.
Provider order: Groq → Gemini → local Ollama (Qwen2.5, Apache 2.0).
Every question and answer is embedded (multilingual MiniLM, 384 dims) and stored in `semantic_memory`.

## Privacy (F13, F14)
`users.data_sharing_consent` defaults to `false`. The seed company view
(`v_seed_insights`) uses consenting fields only, drops owner and geometry,
reports at district level, and hides groups smaller than 5 fields.
