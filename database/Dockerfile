# Local dev database: PostgreSQL 16 + pgvector + PostGIS 3 (all open source).
# Based on the official pgvector image (current Debian, PostgreSQL apt repo preconfigured).
# Supabase already ships both extensions, so production needs no custom image.
FROM pgvector/pgvector:pg16
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-16-postgis-3 \
 && rm -rf /var/lib/apt/lists/*
COPY schema.sql /docker-entrypoint-initdb.d/10_schema.sql
