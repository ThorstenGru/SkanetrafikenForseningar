-- Follow-up to 004_wipe_delay_history.sql: the user clarified they meant
-- ALL tables, fully — including claim_tracking, which 004 deliberately
-- excluded. It was already empty of real data at this point (2026-07-06),
-- so this is a formality for a genuinely clean slate rather than an actual
-- data-loss event.
TRUNCATE TABLE claim_tracking RESTART IDENTITY;
