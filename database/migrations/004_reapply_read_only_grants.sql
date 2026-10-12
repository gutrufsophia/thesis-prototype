-- 004_reapply_read_only_grants.sql
--
-- Enabling the Data API in the Supabase dashboard grants INSERT, UPDATE and DELETE
-- on every public table back to the anon and authenticated roles. Row-level
-- security still blocks the writes, but the roles should not hold the privilege
-- at all. Re-run this file whenever the Data API is switched off and on again.
--
-- Idempotent.

begin;

revoke all on public.setores_censitarios_grande_sp from anon, authenticated;
revoke all on public.dados_censo_grande_sp         from anon, authenticated;
revoke all on public.infraestrutura_saude          from anon, authenticated;
revoke all on public.mapa_vulnerabilidade          from anon, authenticated;

grant select on public.setores_censitarios_grande_sp to anon, authenticated;
grant select on public.dados_censo_grande_sp         to anon, authenticated;
grant select on public.infraestrutura_saude          to anon, authenticated;
grant select on public.mapa_vulnerabilidade          to anon, authenticated;

commit;

notify pgrst, 'reload schema';
