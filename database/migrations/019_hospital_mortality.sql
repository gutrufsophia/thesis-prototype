-- 019_hospital_mortality.sql
--
-- In-hospital deaths of SUS admissions and the deaths each hospital's case mix predicts
-- (database/reference/compute_hospital_mortality.py: indirect standardisation by diagnosis group,
-- age group and admission type over the RMSP hospitals; funnel limits with an additive
-- random-effects term). Loaded from data/hospital_mortality.csv:
--
--   create temp table m (cnes bigint, admissions int, deaths int, mortality_pct numeric,
--                        expected_deaths numeric, ratio numeric, expected_pct numeric,
--                        lower_95 numeric, upper_95 numeric, lower_998 numeric, upper_998 numeric,
--                        band text, top_chapter text, top_chapter_pct numeric);
--   \copy m from 'data/hospital_mortality.csv' with (format csv, header true)
--   update infraestrutura_saude i set obitos_sus = m.deaths, obitos_esperados = m.expected_deaths,
--          mortalidade_faixa = m.band from m where m.cnes = i."CO_CNES";
--
-- Idempotent.

begin;

alter table public.infraestrutura_saude
    add column if not exists obitos_sus integer,
    add column if not exists obitos_esperados numeric,
    add column if not exists mortalidade_faixa text;

comment on column public.infraestrutura_saude.obitos_sus is
    'Deaths in SUS admissions, SIH by place of admission, processed Jan/2025 to Jul/2026; hospitals only';
comment on column public.infraestrutura_saude.obitos_esperados is
    'Deaths the case mix predicts at the RMSP hospitals'' rates by diagnosis group x age group x admission type';
comment on column public.infraestrutura_saude.mortalidade_faixa is
    'within, above or below the 99.8% funnel limits of observed / expected among the RMSP hospitals';

alter table public.infraestrutura_saude drop constraint if exists mortalidade_faixa_valida;
alter table public.infraestrutura_saude
    add constraint mortalidade_faixa_valida check (mortalidade_faixa in ('within', 'above', 'below'));

commit;

notify pgrst, 'reload schema';
