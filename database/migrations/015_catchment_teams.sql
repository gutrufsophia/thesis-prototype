-- Supply in primary care teams and reach for the catchment model (database/reference/compute_catchment.py):
-- team-equivalents (eSF = 1; eAP = 0.5 or 0.75 by modality), people per team, and the mean straight-line
-- distance from the residents allocated to each unit, with the share beyond 2 km. Loaded like 014:
--
--   create temp table c (cnes bigint, served_population numeric, served_deprived_pct numeric,
--                        mean_catchment_m numeric, edge_m numeric, near_edge boolean, teams_esf int,
--                        teams_eap_20h int, teams_eap_30h int, team_equivalents numeric,
--                        served_per_team numeric, served_mean_distance_m numeric, served_far_pct numeric);
--   \copy c from 'data/catchment_units.csv' with (format csv, header true)
--   update entorno_referencia e set served_population = c.served_population, ... from c where c.cnes = e.cnes;

begin;

alter table public.entorno_referencia
    add column if not exists teams_esf integer,
    add column if not exists teams_eap_20h integer,
    add column if not exists teams_eap_30h integer,
    add column if not exists team_equivalents numeric,
    add column if not exists served_per_team numeric,
    add column if not exists served_mean_distance_m numeric,
    add column if not exists served_far_pct numeric;

comment on column public.entorno_referencia.team_equivalents is
    'Active eSF teams plus eAP teams weighted 0.5 (20 h) or 0.75 (30 h), CNES 2026-08';
comment on column public.entorno_referencia.served_per_team is
    'served_population / team_equivalents; compared with the PNAB 2017 range of 2,000 to 3,500 people per team';
comment on column public.entorno_referencia.served_mean_distance_m is
    'Mean straight-line distance from the residents allocated to the unit to the unit';

commit;

notify pgrst, 'reload schema';
