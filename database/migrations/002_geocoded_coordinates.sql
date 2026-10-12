-- 002_geocoded_coordinates.sql
--
-- Facilities without a usable CNES coordinate are geocoded from their street
-- address with IBGE's CNEFE 2022 (database/geocoding/geocode_cnefe.py). This
-- migration records where each coordinate came from and how precise it is, and
-- exposes that to the map. coord_status keeps describing the CNES coordinate.
--
-- Idempotent.

begin;

alter table public.infraestrutura_saude add column if not exists coord_source text;
alter table public.infraestrutura_saude add column if not exists coord_precision_m integer;

alter table public.infraestrutura_saude drop constraint if exists infraestrutura_saude_coord_source_check;
alter table public.infraestrutura_saude add constraint infraestrutura_saude_coord_source_check
    check (coord_source in ('cnes', 'cnefe_address', 'cnefe_street', 'cnefe_cep'));

comment on column public.infraestrutura_saude.coord_source is
    'Origin of coord. cnes: registry coordinate. cnefe_address: CNEFE address with the same street and number. cnefe_street: nearest house number on the same street and CEP. cnefe_cep: centroid of the CEP. NULL when coord is NULL.';
comment on column public.infraestrutura_saude.coord_precision_m is
    'Radius in metres expected to contain the true position. cnefe_street: 90th percentile measured by leave-one-out. cnefe_cep: farthest CNEFE address of the CEP from its centroid (upper bound). NULL for cnes and cnefe_address.';

update public.infraestrutura_saude set coord_source = 'cnes'
where coord is not null and coord_source is null;

create or replace function public.facility_points()
returns json
language sql
stable
set search_path = public, extensions
as $$
    select json_build_object(
        -- [cnes, name, type, lat, lon, coord_source]
        'points', coalesce((
            select json_agg(json_build_array(
                f."CO_CNES",
                coalesce(nullif(btrim(f."NO_FANTASIA"), ''), f."NO_RAZAO_SOCIAL"),
                f.tipo_equipamento,
                round(st_y(f.coord::geometry)::numeric, 6),
                round(st_x(f.coord::geometry)::numeric, 6),
                f.coord_source
            ))
            from infraestrutura_saude f
            where f.coord is not null
        ), '[]'::json),
        -- [cnes, name, type, coord_status]
        'unlocated', coalesce((
            select json_agg(json_build_array(
                f."CO_CNES",
                coalesce(nullif(btrim(f."NO_FANTASIA"), ''), f."NO_RAZAO_SOCIAL"),
                f.tipo_equipamento,
                f.coord_status
            ))
            from infraestrutura_saude f
            where f.coord is null
        ), '[]'::json)
    );
$$;

commit;

notify pgrst, 'reload schema';
