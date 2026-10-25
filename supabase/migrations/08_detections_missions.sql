-- Detections awaiting review, and missions, survive a refresh and an API restart.
--
-- Until now a detection lived only in the browser that received it (a refresh
-- lost the review queue) and mission state only in the API's memory (a
-- restart lost every dispatch's progress). Both are now saved here by the API
-- (routers/review.py, services/mission_store.py), each row tagged with its
-- agency, and loaded back when a screen opens.
--
-- Each row keeps the record as the web app uses it (`data`, camelCase, see
-- src/types/detection.ts and src/types/mission.ts), plus the columns needed to
-- filter it. Only the API (service role) touches these tables; RLS is on with
-- no browser policies.
--
-- Run in the Supabase SQL editor after 07_security_rls.sql. Safe to run twice.

CREATE TABLE IF NOT EXISTS review_detection (
  id                 TEXT PRIMARY KEY,
  "agencyId"         INTEGER NOT NULL REFERENCES agency(id) ON DELETE CASCADE,
  "validationStatus" TEXT NOT NULL CHECK ("validationStatus" IN ('PENDING', 'VERIFIED', 'REJECTED')),
  "detectedAt"       TIMESTAMPTZ NOT NULL,
  data               JSONB NOT NULL,
  -- The media asset the detection was seen in (the agency's live feed, or an
  -- uploaded clip), so a reloaded detection still has a source to show.
  "mediaAsset"       JSONB,
  "updatedAt"        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS review_detection_agency_idx ON review_detection ("agencyId", "detectedAt" DESC);

CREATE TABLE IF NOT EXISTS mission (
  id          TEXT PRIMARY KEY,
  "agencyId"  INTEGER NOT NULL REFERENCES agency(id) ON DELETE CASCADE,
  status      TEXT NOT NULL,
  data        JSONB NOT NULL,
  "updatedAt" TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS mission_agency_idx ON mission ("agencyId");

ALTER TABLE review_detection ENABLE ROW LEVEL SECURITY;
ALTER TABLE mission          ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON review_detection, mission FROM anon, authenticated;
