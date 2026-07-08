-- Adds Trafikverket's own TrainAnnouncement feed as a second, independent
-- rail-delay source alongside Trafiklab's GTFS-RT TripUpdates. Requested by
-- the user 2026-07-08 after discovering the GTFS-RT feed only reports live
-- predictions for ~5% of scheduled trips (see docs/ARCHITECTURE.md's
-- coverage-check section) -- two departures the rider saw flagged in
-- Skånetrafiken's own app (a 04:50 delay, a 05:20 cancellation) had zero
-- rows anywhere in `delays`/`trip_cancellations`, confirmed by direct query
-- against this project's own Supabase project.
--
-- Trafikverket is the track infrastructure owner and runs its own
-- track-side train-describer system independent of which onboard AVL
-- equipment a given operator's vehicle happens to carry -- this is the
-- source Trafikverket's own "Tågläget"/öppna-data reporting is built on,
-- and it covers essentially all train movement nationally (Pågatåg,
-- Öresundståg, Krösatåg all run on Trafikverket-owned track). It does NOT
-- cover buses (SkåneExpressen etc.) -- rail only. See
-- docs/TRAFIKVERKET_INTEGRATION.md for the full research writeup, open
-- questions, and why this is a second, parallel table rather than a
-- straight merge into `delays`.
--
-- Kept as its own table, not merged into `delays`: different primary key
-- shape (Trafikverket has no `trip_id` -- AdvertisedTrainNumber + the
-- traffic date + LocationSignature is the closest equivalent), different
-- station identifier system (LocationSignature, not GTFS stop_id -- see
-- `location_signature_map` below), and reconciliation logic (which source
-- wins when both have data for the same physical trip) belongs in the
-- read/build layer (build_dashboard.py / build_compensation.py /
-- build_claims.py), not baked into ingestion.
CREATE TABLE IF NOT EXISTS train_announcements (
    advertised_train_number   TEXT NOT NULL,
    -- Trafikverket's own "traffic date" for this announcement (their
    -- AdvertisedTimeAtLocation's local calendar date) -- kept distinct from
    -- trip_start_date's GTFS convention until the crosswalk in §2 of the
    -- integration doc is actually verified against real data.
    traffic_date               DATE NOT NULL,
    location_signature         TEXT NOT NULL,
    -- "Ankomst" (arrival) or "Avgang" (departure) -- TrainAnnouncement
    -- carries one row per activity, not one row per stop like GTFS does.
    activity_type              TEXT NOT NULL,
    advertised_time_at_location TIMESTAMPTZ NOT NULL,
    estimated_time_at_location TIMESTAMPTZ,
    time_at_location            TIMESTAMPTZ,
    -- True once Trafikverket marks the whole train as canceled for this
    -- traffic date (their `Canceled` boolean is per train, not per stop).
    canceled                   BOOLEAN NOT NULL DEFAULT FALSE,
    track_at_location           TEXT,
    -- Trafikverket's own free-text/coded deviation reasons (their
    -- `Deviation` array) -- kept as raw text pending real examples; may
    -- need to become a child table if a single announcement can carry more
    -- than one deviation.
    deviation_text              TEXT,
    operator                   TEXT,
    -- Trafikverket's own row version number (`ModifiedTime`-backed) -- lets
    -- an upsert tell "this changed" from "this is stale" without relying on
    -- our own last_seen_at alone, mirroring how their own changeid polling
    -- already dedupes at the API layer.
    modified_time               TIMESTAMPTZ,
    first_seen_at                TIMESTAMPTZ NOT NULL,
    last_seen_at                 TIMESTAMPTZ NOT NULL,
    poll_count                   INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (advertised_train_number, traffic_date, location_signature, activity_type)
);
CREATE INDEX IF NOT EXISTS idx_train_announcements_date ON train_announcements (traffic_date);
CREATE INDEX IF NOT EXISTS idx_train_announcements_train ON train_announcements (advertised_train_number, traffic_date);

-- One-time, hand-researched crosswalk from Trafikverket's 3-4 letter
-- LocationSignature codes to this project's own GTFS stop_id -- the two
-- systems don't share an identifier. Populated by a one-off script (see
-- docs/TRAFIKVERKET_INTEGRATION.md open question #1: GTFS Sweden's own
-- stops.txt `stop_code` column may already carry these signatures, which
-- would make this table a straight import instead of a manual mapping --
-- check before hand-building it station by station).
CREATE TABLE IF NOT EXISTS location_signature_map (
    location_signature  TEXT PRIMARY KEY,
    stop_id              TEXT NOT NULL,
    stop_name            TEXT NOT NULL,
    verified_at           TIMESTAMPTZ NOT NULL
);

-- Trafikverket's polling is changeid-based (INCLUDECHANGEINFO="true"), not
-- time-window based -- each response carries a changeid that the next
-- request's <QUERY ... changeid="..."> replays to get only what changed
-- since. Exactly one row, updated in place every poll -- mirrors the
-- pattern KoDa backfill already uses for its own resume-point bookkeeping
-- (see backfill_koda.py) rather than inventing a second convention.
CREATE TABLE IF NOT EXISTS trafikverket_poll_state (
    id          BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
    changeid    TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL
);
