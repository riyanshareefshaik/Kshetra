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
- **Sentinel-2 NDVI**: Level-1C harmonized (consistent from 2017; surface reflectance over India
  only starts late 2018), masked with Cloud Score+ (clouds and shadows); a date is kept when
  at least 60% of the field is clear.
- **Sentinel-1 VV/VH** (dB): averaged in linear power over the polygon; only the orbit direction
  with the most passes is kept, since ascending and descending geometry differ.
- **NISAR**: L-band GCOV (HH, HV) found via NASA CMR and read from ASF with HTTP range requests
  (only the pixels over the field are downloaded); S-band GCOV files from Bhoonidhi read locally.
- Gaps in NDVI during cloudy periods are filled by a random forest from radar
  features (co-pol, cross-pol, their ratio; no calendar features, so real anomalies
  are not smoothed away) to NDVI, fitted per field on dates where both exist.
  Kept only if cross-validated R² ≥ 0.5. Filled values are flagged
  (`ndvi_source = 'sar_fill'`) and shown differently in the UI.
- Daily `ndvi_smoothed`: Savitzky-Golay (31 days) over observed + filled NDVI,
  left empty across gaps longer than 60 days.

## LLM (F10)
The model sees only tool results. Tools: `get_field_summary`, `get_season`,
`get_yield_explanation`, `find_field_twins`, `search_diary`, `run_what_if`.
Provider order: Groq → Gemini → local Ollama (Qwen2.5, Apache 2.0).
Every question and answer is embedded (multilingual MiniLM, 384 dims) and stored in `semantic_memory`.

## Privacy (F13, F14)
`users.data_sharing_consent` defaults to `false`. The seed company view
(`v_seed_insights`) uses consenting fields only, drops owner and geometry,
reports at district level, and hides groups smaller than 5 fields.
