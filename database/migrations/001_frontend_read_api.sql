-- 001_frontend_read_api.sql
--
-- Read-only API for the prototype frontend, which talks to Supabase (PostgREST)
-- directly with the public anon key until the C++ backend exists.
--
--   1. Lock the public roles down to SELECT and add read policies.
--   2. Track why a facility has no usable coordinate (coord_status).
--   3. facility_points()        -> every facility the map can draw, in one response.
--   4. facility_surroundings()  -> census and facility aggregates within a radius.
--
-- Idempotent: safe to run more than once. PostGIS lives in the "extensions" schema.

begin;

-- ---------------------------------------------------------------------------
-- 1. Privileges and row-level security
-- ---------------------------------------------------------------------------

alter table public.setores_censitarios_grande_sp enable row level security;
alter table public.dados_censo_grande_sp         enable row level security;
alter table public.infraestrutura_saude          enable row level security;

revoke all on public.setores_censitarios_grande_sp from anon, authenticated;
revoke all on public.dados_censo_grande_sp         from anon, authenticated;
revoke all on public.infraestrutura_saude          from anon, authenticated;
revoke all on public.mapa_vulnerabilidade          from anon, authenticated;

grant select on public.setores_censitarios_grande_sp to anon, authenticated;
grant select on public.dados_censo_grande_sp         to anon, authenticated;
grant select on public.infraestrutura_saude          to anon, authenticated;
grant select on public.mapa_vulnerabilidade          to anon, authenticated;

drop policy if exists "Public read" on public.setores_censitarios_grande_sp;
create policy "Public read" on public.setores_censitarios_grande_sp
    for select to anon, authenticated using (true);

drop policy if exists "Public read" on public.dados_censo_grande_sp;
create policy "Public read" on public.dados_censo_grande_sp
    for select to anon, authenticated using (true);

drop policy if exists "Public read" on public.infraestrutura_saude;
create policy "Public read" on public.infraestrutura_saude
    for select to anon, authenticated using (true);

-- ---------------------------------------------------------------------------
-- 2. Coordinate quality flag (filled by database/seeders/seed.py)
-- ---------------------------------------------------------------------------

alter table public.infraestrutura_saude add column if not exists coord_status text;

alter table public.infraestrutura_saude drop constraint if exists infraestrutura_saude_coord_status_check;
alter table public.infraestrutura_saude add constraint infraestrutura_saude_coord_status_check
    check (coord_status in ('ok', 'missing', 'placeholder', 'out_of_region'));

comment on column public.infraestrutura_saude.coord_status is
    'ok: coord is usable. missing: CNES has no coordinate. placeholder: low-precision point shared by several facilities (municipal centroid). out_of_region: falls outside every RMSP census tract. coord is NULL unless ok.';

-- ---------------------------------------------------------------------------
-- 3. facility_points(): everything the map needs, as one JSON document
--    (a single value, so PostgREST's row limit does not truncate it)
-- ---------------------------------------------------------------------------

create or replace function public.facility_points()
returns json
language sql
stable
set search_path = public, extensions
as $$
    select json_build_object(
        -- [cnes, name, type, lat, lon]
        'points', coalesce((
            select json_agg(json_build_array(
                f."CO_CNES",
                coalesce(nullif(btrim(f."NO_FANTASIA"), ''), f."NO_RAZAO_SOCIAL"),
                f.tipo_equipamento,
                round(st_y(f.coord::geometry)::numeric, 6),
                round(st_x(f.coord::geometry)::numeric, 6)
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

-- ---------------------------------------------------------------------------
-- 4. facility_surroundings(): what lies within p_radius_m of a facility
--
--    Census counts are attributed by areal weighting: a tract contributes in
--    proportion to the share of its area inside the circle, which assumes
--    residents are spread evenly within the tract. The same indicators are
--    returned for the facility's municipality and for the whole region so the
--    frontend can show the radius against its context.
-- ---------------------------------------------------------------------------

create or replace function public.facility_surroundings(p_cnes bigint, p_radius_m integer default 1000)
returns json
language sql
stable
set search_path = public, extensions
as $$
    with f as (
        select i."CO_CNES" as cnes, i.coord, i.coord::geometry as pt
        from infraestrutura_saude i
        where i."CO_CNES" = p_cnes and i.coord is not null
    ),
    r as (
        select least(greatest(coalesce(p_radius_m, 1000), 100), 5000) as m
    ),
    circle as (
        select st_buffer(f.coord, r.m)::geometry as g from f, r
    ),
    home as (
        select s."CD_SETOR", s."CD_MUN", s."NM_MUN", s."NM_DIST", s."SITUACAO"
        from setores_censitarios_grande_sp s, f
        where st_intersects(s.geometry, f.pt)
        limit 1
    ),
    tract as (
        select
            s."CD_SETOR" as cd_setor,
            v.mv as geom,
            w.frac,
            c.populacao_total as pop,
            c.total_domicilios_ocupados as hh,
            c.esgoto_rede_geral as sewage,
            c.total_lixo_coletado as garbage,
            c.media_moradores_domicilio as residents_per_hh
        from circle
        join setores_censitarios_grande_sp s
            on s.geometry && circle.g and st_intersects(s.geometry, circle.g)
        -- the simplified mesh has self-intersecting polygons; repair before overlay
        cross join lateral (select st_makevalid(s.geometry) as mv) v
        cross join lateral (
            select least(1, coalesce(
                st_area(st_intersection(v.mv, circle.g)) / nullif(st_area(v.mv), 0), 0
            )) as frac
        ) w
        left join dados_censo_grande_sp c on c.cd_setor = s."CD_SETOR"::bigint
        where w.frac > 0
    ),
    scope as (
        select 'radius' as name,
               sum(pop * frac) as pop, sum(hh * frac) as hh,
               sum(sewage * frac) as sewage, sum(garbage * frac) as garbage,
               sum(residents_per_hh * hh * frac) as residents_x_hh,
               count(*) as tracts,
               count(*) filter (where coalesce(hh, 0) = 0) as tracts_no_households
        from tract
        union all
        select 'municipality',
               sum(c.populacao_total), sum(c.total_domicilios_ocupados),
               sum(c.esgoto_rede_geral), sum(c.total_lixo_coletado),
               sum(c.media_moradores_domicilio * c.total_domicilios_ocupados),
               count(*), count(*) filter (where c.total_domicilios_ocupados = 0)
        from dados_censo_grande_sp c, home
        where c.cd_municipio = home."CD_MUN"::bigint
        union all
        select 'region',
               sum(c.populacao_total), sum(c.total_domicilios_ocupados),
               sum(c.esgoto_rede_geral), sum(c.total_lixo_coletado),
               sum(c.media_moradores_domicilio * c.total_domicilios_ocupados),
               count(*), count(*) filter (where c.total_domicilios_ocupados = 0)
        from dados_censo_grande_sp c
    ),
    nearby as (
        select n.*, st_distance(n.coord, f.coord) as dist
        from infraestrutura_saude n, f, r
        where n.coord is not null
          and n."CO_CNES" <> f.cnes
          and st_dwithin(n.coord, f.coord, r.m)
    )
    select case when not exists (select 1 from f) then
        json_build_object('located', false)
    else json_build_object(
        'located', true,
        'facility', (select json_build_object(
            'lat', round(st_y(pt)::numeric, 6), 'lon', round(st_x(pt)::numeric, 6)) from f),
        'radius_m', (select m from r),
        'area_km2', (select round((pi() * m * m / 1e6)::numeric, 3) from r),
        'location', (select json_build_object(
            'tract', "CD_SETOR", 'municipality', "NM_MUN",
            'district', "NM_DIST", 'situation', "SITUACAO") from home),
        'census', (select json_object_agg(name, json_build_object(
            'population', round(pop::numeric),
            'households', round(hh::numeric),
            'sewage_pct', round((100 * sewage / nullif(hh, 0))::numeric, 1),
            'garbage_pct', round((100 * garbage / nullif(hh, 0))::numeric, 1),
            'residents_per_household', round((residents_x_hh / nullif(hh, 0))::numeric, 2),
            'tracts', tracts,
            'tracts_no_households', tracts_no_households)) from scope),
        'facilities', coalesce((select json_agg(json_build_object(
            'cnes', "CO_CNES",
            'name', coalesce(nullif(btrim("NO_FANTASIA"), ''), "NO_RAZAO_SOCIAL"),
            'type', tipo_equipamento,
            'distance_m', round(dist::numeric),
            'lat', round(st_y(coord::geometry)::numeric, 6),
            'lon', round(st_x(coord::geometry)::numeric, 6),
            'beds', "LEITOS_EXISTENTES",
            'physicians', total_medicos,
            'nurses', total_enfermeiros) order by dist) from nearby), '[]'::json),
        'tracts', json_build_object(
            'type', 'FeatureCollection',
            'features', coalesce((select json_agg(json_build_object(
                'type', 'Feature',
                'geometry', st_asgeojson(geom, 5)::json,
                'properties', json_build_object(
                    'cd_setor', cd_setor,
                    'share_inside', round(frac::numeric, 3),
                    'population', pop,
                    'households', hh,
                    'sewage_pct', round((100.0 * sewage / nullif(hh, 0))::numeric, 1),
                    'garbage_pct', round((100.0 * garbage / nullif(hh, 0))::numeric, 1),
                    'residents_per_household', residents_per_hh))) from tract), '[]'::json))
    ) end;
$$;

grant execute on function public.facility_points() to anon, authenticated;
grant execute on function public.facility_surroundings(bigint, integer) to anon, authenticated;

commit;

notify pgrst, 'reload schema';
