-- Row-level security: each account sees only what its role and agency allow.
--
-- Before this, RLS was off and the anon key (which ships inside the website)
-- could read and change every row - including every user's password hash.
--
-- How it works: the API signs each user in and issues a token signed with
-- this project's JWT secret (api/services/auth.py). The website sends that
-- token to Supabase, which verifies it and exposes its claims through
-- auth.jwt(): "sub" (user id), "app_role" and "agency_id". The policies below
-- read those. The API itself uses the service-role key, which bypasses RLS,
-- for sign-in, sign-up, alerts and everything else it does on users' behalf.
--
-- BEFORE RUNNING THIS, in api/.env:
--   SUPABASE_SERVICE_ROLE_KEY = the real service_role key (Project Settings > API)
--   SUPABASE_JWT_SECRET       = the legacy JWT secret (Project Settings > JWT Keys)
-- then restart the API and sign in again. Otherwise the API (still on the anon
-- key) and every open browser lose database access.
--
-- Run in the Supabase SQL editor. Safe to run twice. To undo in an emergency:
--   ALTER TABLE <table> DISABLE ROW LEVEL SECURITY;  (for each table below)

-- ── Who is asking (from the verified token) ──────────────────────────────────

CREATE OR REPLACE FUNCTION public.app_user_id() RETURNS integer
LANGUAGE sql STABLE AS $$
  SELECT CASE WHEN (auth.jwt() ->> 'sub') ~ '^[0-9]+$' THEN (auth.jwt() ->> 'sub')::integer END
$$;

CREATE OR REPLACE FUNCTION public.app_role() RETURNS text
LANGUAGE sql STABLE AS $$
  SELECT auth.jwt() ->> 'app_role'
$$;

CREATE OR REPLACE FUNCTION public.app_agency_id() RETURNS integer
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(auth.jwt() ->> 'agency_id', '')::integer
$$;

-- ── Signed-out visitors get nothing; the API handles sign-in and sign-up ──────

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon;

-- ── Every table: RLS on, no access unless a policy below grants it ───────────
-- detection, media, response, alert and audit_history get no policies: only the
-- API (service role) reads and writes them.

ALTER TABLE "user"          ENABLE ROW LEVEL SECURITY;
ALTER TABLE agency          ENABLE ROW LEVEL SECURITY;
ALTER TABLE drone           ENABLE ROW LEVEL SECURITY;
ALTER TABLE incident        ENABLE ROW LEVEL SECURITY;
ALTER TABLE detection       ENABLE ROW LEVEL SECURITY;
ALTER TABLE media           ENABLE ROW LEVEL SECURITY;
ALTER TABLE response        ENABLE ROW LEVEL SECURITY;
ALTER TABLE alert           ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_history   ENABLE ROW LEVEL SECURITY;

-- ── user ─────────────────────────────────────────────────────────────────────
-- Readable: yourself, your agency's members, and (System Admin) everyone.
-- Never readable from the browser: passwordHash, pushToken.
-- Changeable: your own profile; an Agency Admin activates/deactivates their
-- staff; the System Admin activates an approved agency's admin. Role, agency
-- and password are never changed from the browser.

REVOKE SELECT, INSERT, UPDATE, DELETE ON "user" FROM authenticated;

DO $$
DECLARE
  readable text;
  writable text;
BEGIN
  SELECT string_agg(quote_ident(column_name), ', ') INTO readable
  FROM information_schema.columns
  WHERE table_schema = 'public' AND table_name = 'user'
    AND column_name NOT IN ('passwordHash', 'pushToken');
  EXECUTE format('GRANT SELECT (%s) ON "user" TO authenticated', readable);

  SELECT string_agg(quote_ident(column_name), ', ') INTO writable
  FROM information_schema.columns
  WHERE table_schema = 'public' AND table_name = 'user'
    AND column_name IN ('firstName', 'middleName', 'lastName', 'email', 'phone', 'active');
  EXECUTE format('GRANT UPDATE (%s) ON "user" TO authenticated', writable);
END $$;

DROP POLICY IF EXISTS user_read ON "user";
CREATE POLICY user_read ON "user" FOR SELECT TO authenticated USING (
  id = app_user_id()
  OR "agencyId" = app_agency_id()
  OR app_role() = 'SYSTEM_ADMIN'
);

DROP POLICY IF EXISTS user_update ON "user";
CREATE POLICY user_update ON "user" FOR UPDATE TO authenticated
USING (
  id = app_user_id()
  OR (app_role() = 'AGENCY_ADMIN' AND "agencyId" = app_agency_id() AND role IN ('COMMAND_STAFF', 'FIELD_RESPONDER'))
  OR app_role() = 'SYSTEM_ADMIN'
)
WITH CHECK (
  id = app_user_id()
  OR (app_role() = 'AGENCY_ADMIN' AND "agencyId" = app_agency_id() AND role IN ('COMMAND_STAFF', 'FIELD_RESPONDER'))
  OR app_role() = 'SYSTEM_ADMIN'
);

-- ── agency ───────────────────────────────────────────────────────────────────
-- Members read their own agency; the System Admin reads and reviews all.

GRANT SELECT, UPDATE ON agency TO authenticated;
REVOKE INSERT, DELETE ON agency FROM authenticated;

DROP POLICY IF EXISTS agency_read ON agency;
CREATE POLICY agency_read ON agency FOR SELECT TO authenticated USING (
  id = app_agency_id() OR app_role() = 'SYSTEM_ADMIN'
);

DROP POLICY IF EXISTS agency_review ON agency;
CREATE POLICY agency_review ON agency FOR UPDATE TO authenticated
USING (app_role() = 'SYSTEM_ADMIN')
WITH CHECK (app_role() = 'SYSTEM_ADMIN');

-- ── drone ────────────────────────────────────────────────────────────────────
-- An agency's Command Staff and Agency Admin manage its own fleet.

GRANT SELECT, INSERT, UPDATE, DELETE ON drone TO authenticated;

DROP POLICY IF EXISTS drone_read ON drone;
CREATE POLICY drone_read ON drone FOR SELECT TO authenticated USING ("agencyId" = app_agency_id());

DROP POLICY IF EXISTS drone_manage ON drone;
CREATE POLICY drone_manage ON drone FOR ALL TO authenticated
USING ("agencyId" = app_agency_id() AND app_role() IN ('COMMAND_STAFF', 'AGENCY_ADMIN'))
WITH CHECK ("agencyId" = app_agency_id() AND app_role() IN ('COMMAND_STAFF', 'AGENCY_ADMIN'));

-- ── incident ─────────────────────────────────────────────────────────────────
-- Everyone in the agency reads its incidents (responders open the one they
-- are dispatched to). Command Staff open them, in their own name.

GRANT SELECT, INSERT, UPDATE ON incident TO authenticated;
REVOKE DELETE ON incident FROM authenticated;

DROP POLICY IF EXISTS incident_read ON incident;
CREATE POLICY incident_read ON incident FOR SELECT TO authenticated USING ("agencyId" = app_agency_id());

DROP POLICY IF EXISTS incident_create ON incident;
CREATE POLICY incident_create ON incident FOR INSERT TO authenticated WITH CHECK (
  "agencyId" = app_agency_id() AND "reportedBy" = app_user_id() AND app_role() = 'COMMAND_STAFF'
);

DROP POLICY IF EXISTS incident_update ON incident;
CREATE POLICY incident_update ON incident FOR UPDATE TO authenticated
USING ("agencyId" = app_agency_id() AND app_role() IN ('COMMAND_STAFF', 'AGENCY_ADMIN'))
WITH CHECK ("agencyId" = app_agency_id());

-- ── API-only tables: no browser access at all ────────────────────────────────

REVOKE ALL ON detection, media, response, alert, audit_history FROM authenticated;
