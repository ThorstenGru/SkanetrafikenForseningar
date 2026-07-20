-- Same fix as 016_enable_rls_public_tables.sql, applied to the table that
-- migration was written before -- caught immediately while verifying 018's
-- own rollout, not left for the next Supabase security-advisor email.
-- data_quality_runs is server-only (data_quality_check.py connects via
-- DATABASE_URL, the table owner, which bypasses RLS by default): no
-- policies needed, a hard default-deny for anon/authenticated via
-- PostgREST is correct here, same reasoning as every other table in 016.
ALTER TABLE public.data_quality_runs ENABLE ROW LEVEL SECURITY;
