-- 020_hospital_mortality_profile.sql
--
-- What makes each hospital's expected death rate differ from the regional rate
-- (database/reference/compute_hospital_mortality.py): the Shapley split of expected - regional
-- rate among diagnosis, age and admission type, and the shares that describe each factor.
-- Loaded from data/hospital_mortality.csv together with the columns of migration 019:
--
--   create temp table m (cnes bigint, admissions int, deaths int, mortality_pct numeric,
--                        expected_deaths numeric, ratio numeric, expected_pct numeric,
--                        lower_95 numeric, upper_95 numeric, lower_998 numeric, upper_998 numeric,
--                        band text, top_chapter text, top_chapter_pct numeric,
--                        region_mortality_pct numeric, profile_factor text, shapley_diagnosis_pp numeric,
--                        shapley_age_pp numeric, shapley_urgency_pp numeric, old_pct numeric,
--                        old_region_pct numeric, urgent_pct numeric, urgent_region_pct numeric,
--                        chapter text, chapter_pct numeric, chapter_region_pct numeric,
--                        chapter_rate_region_pct numeric);
--   \copy m from 'data/hospital_mortality.csv' with (format csv, header true)
--   update infraestrutura_saude i set obitos_sus = m.deaths, obitos_esperados = m.expected_deaths,
--          mortalidade_faixa = m.band,
--          mortalidade_perfil = jsonb_build_object(
--              'taxa_regiao', m.region_mortality_pct,
--              'shapley_pp', jsonb_build_object('diagnostico', m.shapley_diagnosis_pp,
--                                               'idade', m.shapley_age_pp, 'carater', m.shapley_urgency_pp),
--              'idosos_pct', m.old_pct, 'idosos_regiao_pct', m.old_region_pct,
--              'urgencia_pct', m.urgent_pct, 'urgencia_regiao_pct', m.urgent_region_pct,
--              'capitulo', m.chapter, 'capitulo_pct', m.chapter_pct,
--              'capitulo_regiao_pct', m.chapter_region_pct, 'capitulo_taxa_regiao', m.chapter_rate_region_pct)
--   from m where m.cnes = i."CO_CNES";
--
-- Idempotent.

begin;

alter table public.infraestrutura_saude add column if not exists mortalidade_perfil jsonb;

comment on column public.infraestrutura_saude.mortalidade_perfil is
    'Composition behind obitos_esperados against the RMSP hospitals: Shapley split (percentage points) of '
    'expected - regional rate among diagnosis, age and admission type; shares aged 70+, urgent, and of the '
    'ICD-10 chapter that moves the expected rate most, each with the regional share; hospitals only';

commit;

notify pgrst, 'reload schema';
