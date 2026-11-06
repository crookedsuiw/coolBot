-- One-time Postgres setup for KalqyBot. Run as a superuser, e.g.:
--   psql -h localhost -U postgres -f migrations/db_setup.sql
-- You'll be prompted for the postgres password, then for a new password for the kalqy user.

CREATE ROLE kalqy LOGIN;
CREATE DATABASE kalqy OWNER kalqy;
GRANT ALL PRIVILEGES ON DATABASE kalqy TO kalqy;

\c kalqy
-- pgvector is not a trusted extension, so a superuser has to create it
CREATE EXTENSION IF NOT EXISTS vector;
ALTER SCHEMA public OWNER TO kalqy;
GRANT ALL ON SCHEMA public TO kalqy;

\password kalqy
