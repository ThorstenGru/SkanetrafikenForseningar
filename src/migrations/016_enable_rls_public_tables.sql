-- Enables Row-Level Security on every public table that had it disabled,
-- flagged by Supabase's automated security advisor (email, 2026-07-14) as
-- "Table publicly accessible" (rls_disabled_in_public). Confirmed directly
-- before applying: the `anon` role -- the same key claims_template.html
-- ships client-side, readable by anyone via page source -- holds full
-- SELECT/INSERT/UPDATE/DELETE/TRUNCATE grants on all of these tables, and
-- with RLS off those grants are completely unrestricted. This is a real,
-- immediately exploitable gap: anyone with the anon key could wipe the
-- entire delays/alerts/train_announcements history via Supabase's
-- auto-generated REST API.
--
-- No policies are added -- deliberately -- which makes this a hard default-
-- deny for the anon/authenticated PostgREST roles. That's safe here because:
--   1. All delay/schedule data is baked server-side into the static HTML at
--      build time (build_dashboard.py/build_compensation.py/build_claims.py),
--      so the client never needs to read these tables directly via the
--      anon key.
--   2. scan.py/housekeeping.py/etc. connect via DATABASE_URL as the table
--      owner, which bypasses RLS by default (RLS only restricts non-owner
--      roles unless FORCE ROW LEVEL SECURITY is set, which this does not
--      do) -- the GitHub Actions pipeline is unaffected.
--   3. claim_tracking already has its own RLS policies (unaffected by this
--      migration) and is the only table the client actually reads/writes
--      via the anon key.
ALTER TABLE public.alert_entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.delays ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.housekeeping_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.line_daily_visibility ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.line_visibility_anomalies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.location_signature_map ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.scan_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.seen_trips ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trafikverket_poll_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.train_announcements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trip_cancellations ENABLE ROW LEVEL SECURITY;
