-- Drone serial numbers follow one format, and removing a drone keeps its detections.
--
-- 1. Serial format. The web app (src/components/drones/registration/validation.ts)
--    stores serials trimmed and upper-case: 4-32 letters, digits or hyphens, not
--    starting or ending with a hyphen. This CHECK holds every other path that
--    writes a drone to the same rule.
--
-- 2. Detection evidence. detection."droneId" cascaded on delete, so removing a
--    drone from the fleet erased every detection it had recorded, along with the
--    evidence behind any incident. A removed drone's detections now stay, with
--    "droneId" set to NULL.
--
-- Run in the Supabase SQL editor after 08_detections_missions.sql. Safe to run twice.

ALTER TABLE drone DROP CONSTRAINT IF EXISTS drone_serial_number_format;
ALTER TABLE drone ADD CONSTRAINT drone_serial_number_format
  CHECK ("serialNumber" ~ '^[A-Z0-9][A-Z0-9-]{2,30}[A-Z0-9]$');

ALTER TABLE detection ALTER COLUMN "droneId" DROP NOT NULL;
ALTER TABLE detection DROP CONSTRAINT IF EXISTS "detection_droneId_fkey";
ALTER TABLE detection ADD CONSTRAINT "detection_droneId_fkey"
  FOREIGN KEY ("droneId") REFERENCES drone(id) ON UPDATE CASCADE ON DELETE SET NULL;
