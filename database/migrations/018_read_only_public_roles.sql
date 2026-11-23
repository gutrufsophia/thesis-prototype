-- 018_read_only_public_roles.sql
--
-- The public roles held INSERT, UPDATE and DELETE on three tables created after 004
-- (entorno_referencia, indicadores_distrito, resultado_esperado). Row-level security blocked the
-- writes, but the roles should not hold the privilege. Unlike 004, this covers every table in the
-- public schema, so re-running it after the Data API is switched off and on again also covers
-- tables added later.
--
-- Idempotent.

begin;

do $$
declare t text;
begin
    for t in select tablename from pg_tables where schemaname = 'public' loop
        execute format('revoke all on public.%I from anon, authenticated', t);
        execute format('grant select on public.%I to anon, authenticated', t);
    end loop;
end;
$$;

commit;

notify pgrst, 'reload schema';
