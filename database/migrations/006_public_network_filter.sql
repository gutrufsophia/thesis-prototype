-- 006_public_network_filter.sql
--
-- "Public network" (rede_sus) is defined once, in the database: a facility run by
-- the public administration, or one that declares services under the SUS agreement.
-- Legal nature alone is not enough: several public hospitals are legally non-profit
-- foundations. The map and the radius analysis use this flag for the optional
-- "public network only" filter.
--
-- Idempotent.

begin;

alter table public.infraestrutura_saude add column if not exists rede_sus boolean
    generated always as (esfera_juridica = 'Administração Pública' or coalesce(atende_sus, false)) stored;

comment on column public.infraestrutura_saude.rede_sus is
    'Public network: public administration, or declares SUS services (atende_sus). Derived; do not write.';

create or replace function public.facility_points()
returns json
language sql
stable
set search_path = public, extensions
as $$
    select json_build_object(
        -- [cnes, name, type, lat, lon, coord_source, rede_sus]
        'points', coalesce((
            select json_agg(json_build_array(
                f."CO_CNES",
                coalesce(nullif(btrim(f."NO_FANTASIA"), ''), f."NO_RAZAO_SOCIAL"),
                f.tipo_equipamento,
                round(st_y(f.coord::geometry)::numeric, 6),
                round(st_x(f.coord::geometry)::numeric, 6),
                f.coord_source,
                coalesce(f.rede_sus, false)
            ))
            from infraestrutura_saude f
            where f.coord is not null
        ), '[]'::json),
        -- [cnes, name, type, coord_status, rede_sus]
        'unlocated', coalesce((
            select json_agg(json_build_array(
                f."CO_CNES",
                coalesce(nullif(btrim(f."NO_FANTASIA"), ''), f."NO_RAZAO_SOCIAL"),
                f.tipo_equipamento,
                f.coord_status,
                coalesce(f.rede_sus, false)
            ))
            from infraestrutura_saude f
            where f.coord is null
        ), '[]'::json)
    );
$$;

-- Same as in 001, with sus_network added to each nearby facility
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
            'sus_network', rede_sus,
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

commit;

notify pgrst, 'reload schema';
