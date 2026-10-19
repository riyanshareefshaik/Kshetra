-- =====================================================================
-- Kshetra database schema: the database is the memory, not the LLM.
--
--   Layer 1  users, fields                 who owns what, where, soil
--   Layer 2  field_timeseries              one row per field per date
--   Layer 3  seasons, events, diary_entries what happened each season
--   Layer 4  semantic_memory, qa_log       embeddings of notes and Q&A
--
--   Support  api_cache                     every external response, so the
--                                          demo never needs a live API
--            district_yields, mandi_prices, crop_varieties  reference data
--
-- Runs on PostgreSQL 16 + PostGIS 3 + pgvector, locally or on Supabase.
-- Idempotent: safe to run more than once.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

-- ---------------------------------------------------------------------
-- Layer 1: users and fields
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name                  text,
    phone                 text UNIQUE,
    preferred_language    text NOT NULL DEFAULT 'te' CHECK (preferred_language IN ('te', 'hi', 'en')),
    -- F13: sharing is OFF until the farmer turns it on.
    data_sharing_consent  boolean NOT NULL DEFAULT false,
    consent_updated_at    timestamptz,
    -- Login (Supabase Auth user id and email); NULL in local single-user mode.
    auth_id               text UNIQUE,
    email                 text,
    created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fields (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id         uuid REFERENCES users(id) ON DELETE SET NULL,
    name             text,
    boundary         geometry(Polygon, 4326) NOT NULL,
    -- Filled by trigger from boundary.
    location         geometry(Point, 4326),
    area_ha          numeric(10, 3),
    boundary_source  text NOT NULL DEFAULT 'drawn'
                     CHECK (boundary_source IN ('drawn', 'auto_sam', 'auto_ndvi', 'pin_buffer')),
    village          text,
    district         text,
    state            text,
    irrigation_type  text CHECK (irrigation_type IN ('rainfed', 'canal', 'borewell', 'tank', 'drip', 'sprinkler', 'unknown')),
    -- Soil (SoilGrids 0-30 cm means unless noted)
    soil_texture     text,
    clay_pct         real,
    sand_pct         real,
    silt_pct         real,
    soc_g_per_kg     real,
    ph_h2o           real,
    nitrogen_g_per_kg real,
    cec_cmol_per_kg  real,
    bulk_density     real,
    soil_source      text,
    ingest_status    text NOT NULL DEFAULT 'pending'
                     CHECK (ingest_status IN ('pending', 'running', 'done', 'failed')),
    ingest_error     text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION fields_derive_geometry() RETURNS trigger AS $$
BEGIN
    NEW.location   := ST_PointOnSurface(NEW.boundary);
    NEW.area_ha    := round((ST_Area(NEW.boundary::geography) / 10000.0)::numeric, 3);
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_fields_derive_geometry ON fields;
CREATE TRIGGER trg_fields_derive_geometry
    BEFORE INSERT OR UPDATE OF boundary ON fields
    FOR EACH ROW EXECUTE FUNCTION fields_derive_geometry();

CREATE INDEX IF NOT EXISTS idx_fields_boundary ON fields USING gist (boundary);
CREATE INDEX IF NOT EXISTS idx_fields_location ON fields USING gist (location);
CREATE INDEX IF NOT EXISTS idx_fields_owner    ON fields (owner_id);
CREATE INDEX IF NOT EXISTS idx_fields_district ON fields (state, district);

-- ---------------------------------------------------------------------
-- Layer 2: time series (field averages, not rasters, to fit the free tier)
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS field_timeseries (
    field_id         uuid NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    date             date NOT NULL,
    -- Optical: Sentinel-2
    ndvi             real CHECK (ndvi BETWEEN -1 AND 1),
    ndvi_smoothed    real CHECK (ndvi_smoothed BETWEEN -1 AND 1),
    -- 's2' = observed, 'sar_fill' = predicted from radar on cloudy dates, 'interp' = interpolated
    ndvi_source      text CHECK (ndvi_source IN ('s2', 'sar_fill', 'interp')),
    cloud_pct        real CHECK (cloud_pct BETWEEN 0 AND 100),
    -- Radar: Sentinel-1 C-band backscatter (dB)
    sar_vv           real,
    sar_vh           real,
    -- Radar: NISAR GCOV backscatter (dB). L-band from ASF, S-band from Bhoonidhi.
    nisar_l_hh       real,
    nisar_l_hv       real,
    nisar_s_hh       real,
    nisar_s_hv       real,
    -- Weather (Open-Meteo archive, NASA POWER as fallback)
    rainfall_mm      real CHECK (rainfall_mm >= 0),
    temp_max_c       real,
    temp_min_c       real,
    temp_mean_c      real,
    et0_mm           real,
    soil_moisture    real,           -- m3/m3, 0-7 cm
    sources          text[] NOT NULL DEFAULT '{}',
    PRIMARY KEY (field_id, date)
);

-- Composite PK covers field+date range scans; BRIN keeps date-only scans cheap.
CREATE INDEX IF NOT EXISTS idx_timeseries_date ON field_timeseries USING brin (date);

-- ---------------------------------------------------------------------
-- Layer 3: seasons, events, diary
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS seasons (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    field_id             uuid NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    year                 smallint NOT NULL CHECK (year BETWEEN 2015 AND 2100),
    season               text NOT NULL CHECK (season IN ('kharif', 'rabi', 'zaid')),
    sowing_date          date,
    peak_date            date,
    harvest_date         date,
    peak_ndvi            real,
    date_detection       text CHECK (date_detection IN ('ndvi', 'sar', 'nisar', 'fused', 'diary')),
    -- F3: crop with confidence; < 0.60 is shown as uncertain.
    crop                 text,
    crop_confidence      real CHECK (crop_confidence BETWEEN 0 AND 1),
    crop_status          text GENERATED ALWAYS AS (
                             CASE WHEN crop IS NULL THEN 'unknown'
                                  WHEN crop_confidence >= 0.60 THEN 'confident'
                                  ELSE 'uncertain' END) STORED,
    crop_alternatives    jsonb NOT NULL DEFAULT '[]',   -- [{"crop": "maize", "p": 0.21}, ...]
    crop_confirmed_by_farmer boolean NOT NULL DEFAULT false,
    variety              text,
    -- F5: yields are ranges (t/ha), never a single number.
    yield_low_t_ha       real CHECK (yield_low_t_ha >= 0),
    yield_mid_t_ha       real CHECK (yield_mid_t_ha >= 0),
    yield_high_t_ha      real CHECK (yield_high_t_ha >= 0),
    yield_is_forecast    boolean NOT NULL DEFAULT false,
    yield_model_version  text,
    yield_method         text CHECK (yield_method IN ('model', 'baseline')),
    -- F6: [{"feature": "rain_jul_mm", "value": 412, "shap": -0.31, "reason": "Rainfall in July was low"}]
    shap_reasons         jsonb NOT NULL DEFAULT '[]',
    -- Season features used by the crop, yield and twin models (ml/features.py)
    features             jsonb NOT NULL DEFAULT '{}',
    in_progress          boolean NOT NULL DEFAULT false,
    date_confidence      real CHECK (date_confidence BETWEEN 0 AND 1),
    -- F7 twins: scaled season features for k-NN (ml/features.py twin_vector).
    feature_vector       vector,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (field_id, year, season),
    CHECK (yield_low_t_ha IS NULL OR yield_high_t_ha IS NULL OR yield_low_t_ha <= yield_high_t_ha),
    CHECK (yield_mid_t_ha IS NULL OR yield_low_t_ha IS NULL OR yield_mid_t_ha >= yield_low_t_ha),
    CHECK (yield_mid_t_ha IS NULL OR yield_high_t_ha IS NULL OR yield_mid_t_ha <= yield_high_t_ha),
    CHECK (sowing_date IS NULL OR harvest_date IS NULL OR sowing_date < harvest_date)
);

CREATE INDEX IF NOT EXISTS idx_seasons_field ON seasons (field_id, year DESC);
CREATE INDEX IF NOT EXISTS idx_seasons_crop  ON seasons (crop, year);

CREATE TABLE IF NOT EXISTS events (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    field_id    uuid NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    season_id   uuid REFERENCES seasons(id) ON DELETE CASCADE,
    event_type  text NOT NULL CHECK (event_type IN (
                    'dry_spell', 'waterlogging', 'flood', 'heat_stress', 'sudden_damage',
                    'sowing', 'harvest', 'irrigation', 'fertilizer', 'pesticide', 'pest_disease', 'other')),
    start_date  date NOT NULL,
    end_date    date,
    severity    real CHECK (severity BETWEEN 0 AND 1),
    -- 'detected' by our models, or reported by the farmer
    origin      text NOT NULL DEFAULT 'detected' CHECK (origin IN ('detected', 'diary', 'farmer')),
    -- Numbers behind the event, e.g. {"rain_mm_21d": 3.2, "ndvi_drop": 0.18, "sar_vh_db": -22.4}
    evidence    jsonb NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now(),
    CHECK (end_date IS NULL OR end_date >= start_date)
);

CREATE INDEX IF NOT EXISTS idx_events_field  ON events (field_id, start_date);
CREATE INDEX IF NOT EXISTS idx_events_season ON events (season_id);

CREATE TABLE IF NOT EXISTS diary_entries (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    field_id       uuid NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    season_id      uuid REFERENCES seasons(id) ON DELETE SET NULL,
    entry_date     date NOT NULL DEFAULT current_date,
    raw_text       text NOT NULL,            -- transcript or typed note, original language
    text_en        text,                     -- English translation for the models
    language       text NOT NULL DEFAULT 'te' CHECK (language IN ('te', 'hi', 'en')),
    audio_path     text,
    activity_type  text CHECK (activity_type IN (
                       'sowing', 'irrigation', 'fertilizer', 'pesticide', 'weeding',
                       'harvest', 'sale', 'observation', 'other')),
    -- Parsed record, e.g. {"product": "urea", "quantity": 50, "unit": "kg", "cost_rs": 300}
    structured     jsonb NOT NULL DEFAULT '{}',
    -- Seed packet OCR, e.g. {"crop": "paddy", "variety": "BPT 5204", "lot": "...", "expiry": "..."}
    seed_packet    jsonb,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_diary_field ON diary_entries (field_id, entry_date DESC);

-- ---------------------------------------------------------------------
-- Layer 4: semantic memory (pgvector)
-- Embeddings: sentence-transformers paraphrase-multilingual-MiniLM-L12-v2 (384 dims).
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS qa_log (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    field_id    uuid REFERENCES fields(id) ON DELETE CASCADE,
    user_id     uuid REFERENCES users(id) ON DELETE SET NULL,
    language    text NOT NULL DEFAULT 'te' CHECK (language IN ('te', 'hi', 'en')),
    question    text NOT NULL,
    answer      text NOT NULL,
    -- [{"tool": "get_season", "args": {...}, "result": {...}}]
    tool_calls  jsonb NOT NULL DEFAULT '[]',
    -- Numbers shown to the farmer as sources
    sources     jsonb NOT NULL DEFAULT '[]',
    answered    boolean NOT NULL DEFAULT true,   -- false when the answer was "I don't know"
    llm_provider text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_qa_field ON qa_log (field_id, created_at DESC);

CREATE TABLE IF NOT EXISTS semantic_memory (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    field_id    uuid REFERENCES fields(id) ON DELETE CASCADE,
    owner_id    uuid REFERENCES users(id) ON DELETE CASCADE,
    kind        text NOT NULL CHECK (kind IN ('diary', 'qa', 'season_summary', 'report')),
    source_id   uuid,                     -- diary_entries.id / qa_log.id / seasons.id
    content     text NOT NULL,
    language    text CHECK (language IN ('te', 'hi', 'en')),
    embedding   vector(384) NOT NULL,
    metadata    jsonb NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memory_embedding ON semantic_memory
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_memory_field ON semantic_memory (field_id, kind);

-- ---------------------------------------------------------------------
-- Cache of every external API response (Rule #1: demo never depends on a live call)
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS api_cache (
    source       text NOT NULL,     -- 'gee_s2', 'gee_s1', 'nisar_l', 'nisar_s', 'open_meteo', 'nasa_power', 'soilgrids', 'agmarknet', ...
    request_key  text NOT NULL,     -- stable hash of the request parameters
    request      jsonb NOT NULL DEFAULT '{}',
    response     jsonb NOT NULL,
    fetched_at   timestamptz NOT NULL DEFAULT now(),
    expires_at   timestamptz,       -- NULL = never expires (historical data)
    PRIMARY KEY (source, request_key)
);

-- ---------------------------------------------------------------------
-- Reference data
-- ---------------------------------------------------------------------

-- ICRISAT district-level database + data.gov.in crop statistics
CREATE TABLE IF NOT EXISTS district_yields (
    state         text NOT NULL,
    district      text NOT NULL,
    year          smallint NOT NULL,
    season        text NOT NULL DEFAULT 'total' CHECK (season IN ('kharif', 'rabi', 'zaid', 'total')),
    crop          text NOT NULL,
    area_ha       real,
    production_t  real,
    yield_t_ha    real,
    source        text NOT NULL,     -- 'icrisat_dld', 'data_gov_in'
    PRIMARY KEY (state, district, year, season, crop, source)
);

CREATE INDEX IF NOT EXISTS idx_district_yields_crop ON district_yields (crop, year);

-- Agmarknet daily mandi prices via data.gov.in (Rs per quintal)
CREATE TABLE IF NOT EXISTS mandi_prices (
    arrival_date  date NOT NULL,
    state         text NOT NULL,
    district      text NOT NULL,
    market        text NOT NULL,
    commodity     text NOT NULL,
    variety       text NOT NULL DEFAULT '',
    min_price     real,
    max_price     real,
    modal_price   real,
    PRIMARY KEY (arrival_date, state, district, market, commodity, variety)
);

CREATE INDEX IF NOT EXISTS idx_mandi_commodity ON mandi_prices (commodity, district, arrival_date DESC);

-- Crops and varieties for the what-if simulator and planner (F8, F9)
CREATE TABLE IF NOT EXISTS crop_varieties (
    crop                  text NOT NULL,
    variety               text NOT NULL,
    season                text NOT NULL CHECK (season IN ('kharif', 'rabi', 'zaid')),
    duration_days         smallint,
    sowing_window_start   text,      -- 'MM-DD'
    sowing_window_end     text,      -- 'MM-DD'
    water_need            text CHECK (water_need IN ('low', 'medium', 'high')),
    recommended_n_kg_ha   real,
    recommended_p2o5_kg_ha real,
    recommended_k2o_kg_ha  real,
    seed_cost_rs_per_ha   real,
    other_cost_rs_per_ha  real,
    states                text[] NOT NULL DEFAULT '{}',
    source                text,
    PRIMARY KEY (crop, variety, season)
);

-- ---------------------------------------------------------------------
-- Soil tests (Soil Health Card, lab or manual entry) for the fertilizer calculator.
-- Values as reported: available N, P, K in kg/ha (P and K elemental, as on the card).
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS soil_tests (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    field_id    uuid NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    test_date   date NOT NULL DEFAULT current_date,
    n_kg_ha     real CHECK (n_kg_ha >= 0),
    p_kg_ha     real CHECK (p_kg_ha >= 0),
    k_kg_ha     real CHECK (k_kg_ha >= 0),
    ph          real CHECK (ph BETWEEN 0 AND 14),
    oc_pct      real CHECK (oc_pct >= 0),
    ec_ds_m     real CHECK (ec_ds_m >= 0),
    zn_ppm      real CHECK (zn_ppm >= 0),
    source      text NOT NULL DEFAULT 'manual' CHECK (source IN ('soil_health_card', 'lab', 'manual')),
    raw_text    text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_soil_tests_field ON soil_tests (field_id, test_date DESC);

-- ---------------------------------------------------------------------
-- Farmer groups (FPOs, village groups). Members choose to share their fields with the group.
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS farmer_groups (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL,
    district    text,
    state       text,
    join_code   text NOT NULL UNIQUE,
    created_by  uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS group_members (
    group_id          uuid NOT NULL REFERENCES farmer_groups(id) ON DELETE CASCADE,
    user_id           uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role              text NOT NULL DEFAULT 'member' CHECK (role IN ('admin', 'member')),
    share_with_group  boolean NOT NULL DEFAULT true,
    joined_at         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (group_id, user_id)
);

-- ---------------------------------------------------------------------
-- F14: seed company insights. Consenting farmers only, no owner, no geometry,
-- district level, groups under 5 fields hidden (k-anonymity).
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW v_seed_insights AS
SELECT
    f.state,
    f.district,
    s.year,
    s.season,
    s.crop,
    s.variety,
    count(DISTINCT f.id)                                         AS n_fields,
    round(avg(s.yield_mid_t_ha)::numeric, 2)                     AS avg_yield_mid_t_ha,
    round(percentile_cont(0.25) WITHIN GROUP (ORDER BY s.yield_mid_t_ha)::numeric, 2) AS yield_p25_t_ha,
    round(percentile_cont(0.75) WITHIN GROUP (ORDER BY s.yield_mid_t_ha)::numeric, 2) AS yield_p75_t_ha,
    round(avg(s.harvest_date - s.sowing_date))                   AS avg_season_days
FROM seasons s
JOIN fields f ON f.id = s.field_id
JOIN users  u ON u.id = f.owner_id
WHERE u.data_sharing_consent
  AND s.crop_status = 'confident'
GROUP BY f.state, f.district, s.year, s.season, s.crop, s.variety
HAVING count(DISTINCT f.id) >= 5;

-- ---------------------------------------------------------------------
-- Upgrades: columns added after the first release, for databases created earlier.
-- Remove synthetic demo data created by earlier versions, then the flag itself.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'fields' AND column_name = 'is_synthetic') THEN
        DELETE FROM fields WHERE is_synthetic;
        ALTER TABLE fields DROP COLUMN is_synthetic;
    END IF;
END $$;
DELETE FROM district_yields WHERE source = 'synthetic';
DELETE FROM users WHERE phone LIKE 'synthetic-%';
ALTER TABLE crop_varieties ADD COLUMN IF NOT EXISTS recommended_n_kg_ha real;
ALTER TABLE seasons ADD COLUMN IF NOT EXISTS yield_method text CHECK (yield_method IN ('model', 'baseline'));
ALTER TABLE seasons ADD COLUMN IF NOT EXISTS features jsonb NOT NULL DEFAULT '{}';
ALTER TABLE seasons ADD COLUMN IF NOT EXISTS in_progress boolean NOT NULL DEFAULT false;
ALTER TABLE seasons ADD COLUMN IF NOT EXISTS date_confidence real CHECK (date_confidence BETWEEN 0 AND 1);
ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_id text UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email text;
ALTER TABLE crop_varieties ADD COLUMN IF NOT EXISTS recommended_p2o5_kg_ha real;
ALTER TABLE crop_varieties ADD COLUMN IF NOT EXISTS recommended_k2o_kg_ha real;
