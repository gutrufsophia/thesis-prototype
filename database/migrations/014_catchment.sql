-- Expected population of each public primary care unit, from the Huff-model allocation of
-- residents within variable floating catchments (database/reference/compute_catchment.py).
-- Loaded into entorno_referencia, which surroundings_reference() already returns whole:
--
--   create temp table c (cnes bigint, served_population numeric, served_deprived_pct numeric,
--                        mean_catchment_m numeric, edge_m numeric, near_edge boolean);
--   \copy c from 'data/catchment_units.csv' with (format csv, header true)
--   update entorno_referencia e set served_population = c.served_population,
--          served_deprived_pct = c.served_deprived_pct, mean_catchment_m = c.mean_catchment_m,
--          edge_m = c.edge_m, near_edge = c.near_edge
--   from c where c.cnes = e.cnes;

begin;

alter table public.entorno_referencia
    add column if not exists served_population numeric,
    add column if not exists served_deprived_pct numeric,
    add column if not exists mean_catchment_m numeric,
    add column if not exists edge_m numeric,
    add column if not exists near_edge boolean;

comment on column public.entorno_referencia.served_population is
    'Residents expected to use this unit: Huff allocation among public primary care units within variable catchments';
comment on column public.entorno_referencia.served_deprived_pct is
    'Share of served_population living in tracts with at least one deprivation (union rule)';
comment on column public.entorno_referencia.near_edge is
    'Distance to the RMSP outer boundary below the mean catchment radius of the residents allocated to the unit';

commit;

notify pgrst, 'reload schema';
