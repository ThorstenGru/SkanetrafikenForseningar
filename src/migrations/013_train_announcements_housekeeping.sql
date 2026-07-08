-- train_announcements (012) went live 2026-07-08 without a retention path --
-- housekeeping.py only knew about the tables that existed when it was
-- written, so this table would otherwise grow unbounded forever. Adds the
-- same 45-day cutoff every other detail table already gets.
ALTER TABLE housekeeping_runs
    ADD COLUMN IF NOT EXISTS train_announcements_deleted INTEGER;
