-- ============================================================================
-- PostgreSQL initialization script for aiecommerce-agents (development only)
-- Runs automatically on first container start via docker-entrypoint-initdb.d.
-- ============================================================================

-- ── Application user (full read-write access) ─────────────────────────────
-- Used by the FastAPI application and sentinel process.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_user') THEN
        CREATE ROLE app_user WITH LOGIN PASSWORD 'app_password';
    END IF;
END
$$;

GRANT ALL PRIVILEGES ON DATABASE orchestrator TO app_user;

-- Grant schema-level privileges so app_user can create tables via SQLAlchemy
GRANT ALL ON SCHEMA public TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO app_user;

-- ── Read-only user (inspection / debugging) ───────────────────────────────
-- Useful for connecting with a DB client to inspect data without risk.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'readonly_user') THEN
        CREATE ROLE readonly_user WITH LOGIN PASSWORD 'readonly_password';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE orchestrator TO readonly_user;
GRANT USAGE ON SCHEMA public TO readonly_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;
