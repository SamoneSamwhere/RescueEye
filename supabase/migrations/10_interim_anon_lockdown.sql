-- Interim lockdown for the anon key, until 07_security_rls.sql can run.
--
-- 07 needs SUPABASE_JWT_SECRET in api/.env so the browser gets a signed
-- database token; without it the web app talks to Supabase with the public
-- anon key, and 07 would lock it out. Meanwhile RLS is off and anon had full
-- access to every table, password hashes included.
--
-- This takes from anon only what the web app never uses (checked against
-- every supabase.from() call in src/). The API is unaffected: it uses the
-- service-role key. 07 still applies cleanly on top: it starts by revoking
-- everything from anon.

-- user: readable without the secrets; only the fields the profile, staff and
-- agency-review screens edit are writable; no inserts or deletes.
REVOKE ALL ON "user" FROM anon;
DO $$
DECLARE
  readable text;
BEGIN
  SELECT string_agg(quote_ident(column_name), ', ') INTO readable
  FROM information_schema.columns
  WHERE table_schema = 'public' AND table_name = 'user'
    AND column_name NOT IN ('passwordHash', 'pushToken');
  EXECUTE format('GRANT SELECT (%s) ON "user" TO anon', readable);
END $$;
GRANT UPDATE ("firstName", "middleName", "lastName", email, phone, active) ON "user" TO anon;

-- agency: read and review only; registration goes through the API.
REVOKE INSERT, DELETE ON agency FROM anon;

-- incident: created and listed from the browser, never edited or deleted.
REVOKE UPDATE, DELETE ON incident FROM anon;

-- Tables the browser never touches: written and read by the API only.
REVOKE ALL ON audit_history, alert, detection, media, response FROM anon;

-- Never needed through the REST API.
REVOKE TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM anon;
