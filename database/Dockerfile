# Local dev database: PostgreSQL 16 + PostGIS 3.4 + pgvector (all open source).
# Supabase already ships both extensions, so production needs no custom image.
FROM postgis/postgis:16-3.4
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-16-pgvector \
 && rm -rf /var/lib/apt/lists/*
COPY schema.sql /docker-entrypoint-initdb.d/10_schema.sql
