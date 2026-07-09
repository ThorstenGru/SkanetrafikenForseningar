-- train_announcements.modified_time (012) was left nullable, but every
-- ON CONFLICT DO UPDATE clause in db.py's upsert_train_announcements_batch
-- gates on `EXCLUDED.modified_time >= train_announcements.modified_time` --
-- a comparison that's false-like whenever either side is NULL. Currently
-- masked only because scan_trafikverket.py's own to_row() always backfills
-- `now` when Trafikverket's ModifiedTime is absent -- a script-level
-- guarantee, not a schema-level one. A future caller (a backfill script,
-- a manual INSERT) that doesn't replicate that fallback could insert a
-- NULL modified_time row that then can never be updated again by any
-- later poll. Found by code review 2026-07-08; verified zero existing
-- NULL rows before adding this constraint.
ALTER TABLE train_announcements
    ALTER COLUMN modified_time SET NOT NULL;
