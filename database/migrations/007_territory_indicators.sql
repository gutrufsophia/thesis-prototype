-- 007_territory_indicators.sql
--
-- Surrounding-territory data for the facility page.
--
--   indicadores_municipio   municipality-level outcomes from DATASUS TabNet (SINAN,
--                           SINASC, SIM), produced by limpeza_datasus.py
--   setor_acesso            for each census tract, how far its residential addresses
--                           are from the nearest public primary care unit
--                           (database/geocoding/compute_access.py, loaded by the seeder)
--   municipal_indicators()  the municipal table with names and census population
--   facility_surroundings() extended: municipalities reached by the radius, crowding
--                           and primary-care access for the radius and its context
--
-- Idempotent.

begin;

create table if not exists public.indicadores_municipio (
    cd_municipio6 text primary key,
    dengue_2022 bigint not null,
    lepto_2022 bigint not null,
    dengue_2023 bigint not null,
    lepto_2023 bigint not null,
    dengue_2024 bigint not null,
    lepto_2024 bigint not null,
    dengue_2025 bigint not null,
    lepto_2025 bigint not null,
    dengue_2026 bigint not null,
    lepto_2026 bigint not null,
    tuberculose_2022 bigint not null,
    tuberculose_2023 bigint not null,
    tuberculose_2024 bigint not null,
    tuberculose_2025 bigint not null,
    nasc_total bigint not null,
    nasc_idade_conhecida bigint not null,
    nasc_mae_menor_20 bigint not null,
    nasc_gestacao_conhecida bigint not null,
    nasc_pretermo bigint not null,
    obitos_total bigint not null,
    obitos_cap_i bigint not null,
    obitos_cap_ii bigint not null,
    obitos_cap_iii bigint not null,
    obitos_cap_iv bigint not null,
    obitos_cap_v bigint not null,
    obitos_cap_vi bigint not null,
    obitos_cap_vii bigint not null,
    obitos_cap_viii bigint not null,
    obitos_cap_ix bigint not null,
    obitos_cap_x bigint not null,
    obitos_cap_xi bigint not null,
    obitos_cap_xii bigint not null,
    obitos_cap_xiii bigint not null,
    obitos_cap_xiv bigint not null,
    obitos_cap_xv bigint not null,
    obitos_cap_xvi bigint not null,
    obitos_cap_xvii bigint not null,
    obitos_cap_xviii bigint not null,
    obitos_cap_xx bigint not null
);

comment on table public.indicadores_municipio is
    'Municipal health outcomes, RMSP. dengue_*: probable cases by residence and year of first symptoms. lepto_*: confirmed cases by residence. tuberculose_*: confirmed cases by municipality of NOTIFICATION. nasc_*: live births by mother''s residence, 2022-2026 pooled. obitos_*: deaths at ages 30-69 by residence and ICD-10 chapter, 2022-2026 pooled.';

-- derived data: safe to rebuild whenever its definition changes
drop table if exists public.setor_acesso;
create table public.setor_acesso (
    cd_setor bigint primary key,
    enderecos integer not null,
    pct_ate_500 numeric not null,
    pct_ate_1000 numeric not null,
    pct_ate_2000 numeric not null,
    dist_mediana_m integer not null
);

comment on table public.setor_acesso is
    'Per census tract: number of residential addresses in CNEFE 2022, the share of them within 500 m, 1 km and 2 km (straight line) of the nearest public-network primary care unit (Centro de Saúde/UBS or Posto de Saúde with rede_sus), and the median distance.';

alter table public.indicadores_municipio enable row level security;
-- (setor_acesso is recreated above, so its policy and grants are set again here)
alter table public.setor_acesso          enable row level security;
revoke all on public.indicadores_municipio from anon, authenticated;
revoke all on public.setor_acesso          from anon, authenticated;
grant select on public.indicadores_municipio to anon, authenticated;
grant select on public.setor_acesso          to anon, authenticated;

drop policy if exists "Public read" on public.indicadores_municipio;
create policy "Public read" on public.indicadores_municipio for select to anon, authenticated using (true);
drop policy if exists "Public read" on public.setor_acesso;
create policy "Public read" on public.setor_acesso for select to anon, authenticated using (true);

create or replace function public.municipal_indicators()
returns json
language sql
stable
set search_path = public, extensions
as $$
    with population as (
        select left(cd_municipio::text, 6) as code, sum(populacao_total) as populacao
        from dados_censo_grande_sp group by 1
    ),
    names as (
        select distinct left("CD_MUN", 6) as code, "NM_MUN" as nome
        from setores_censitarios_grande_sp
    )
    select coalesce(json_agg(to_jsonb(i) || jsonb_build_object('nome', n.nome, 'populacao', p.populacao)), '[]'::json)
    from indicadores_municipio i
    join population p on p.code = i.cd_municipio6
    join names n on n.code = i.cd_municipio6;
$$;

-- Supersedes the definitions in 001 and 006.
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
    -- "crowded" = among the 10% of RMSP tracts with most residents per household
    crowd as (
        select percentile_cont(0.9) within group (order by media_moradores_domicilio) as threshold
        from dados_censo_grande_sp
        where total_domicilios_ocupados > 0
    ),
    census as (
        select c.cd_setor, c.cd_municipio,
               c.populacao_total as pop, c.total_domicilios_ocupados as hh,
               c.esgoto_rede_geral as sewage, c.total_lixo_coletado as garbage,
               c.media_moradores_domicilio as residents_per_hh,
               a.pct_ate_500 as s500, a.pct_ate_1000 as s1000, a.pct_ate_2000 as s2000,
               a.dist_mediana_m as dist,
               (c.total_domicilios_ocupados > 0 and c.media_moradores_domicilio >= crowd.threshold) as crowded
        from dados_censo_grande_sp c
        cross join crowd
        left join setor_acesso a on a.cd_setor = c.cd_setor
    ),
    tract as (
        select
            s."CD_SETOR" as cd_setor, s."CD_MUN" as cd_mun, s."NM_MUN" as nm_mun,
            v.mv as geom, w.frac,
            c.pop, c.hh, c.sewage, c.garbage, c.residents_per_hh, c.dist, c.crowded,
            c.s500, c.s1000, c.s2000
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
        left join census c on c.cd_setor = s."CD_SETOR"::bigint
        where w.frac > 0
    ),
    scope as (
        select 'radius' as name,
               sum(pop * frac) as pop, sum(hh * frac) as hh,
               sum(sewage * frac) as sewage, sum(garbage * frac) as garbage,
               sum(residents_per_hh * hh * frac) as residents_x_hh,
               sum(pop * frac) filter (where crowded) as pop_crowded,
               sum(pop * frac * (100 - s1000) / 100) as pop_far,
               sum(pop * frac) filter (where s1000 is not null) as pop_access,
               count(*) as tracts,
               count(*) filter (where coalesce(hh, 0) = 0) as tracts_no_households
        from tract
        union all
        select 'municipality',
               sum(c.pop), sum(c.hh), sum(c.sewage), sum(c.garbage),
               sum(c.residents_per_hh * c.hh),
               sum(c.pop) filter (where c.crowded),
               sum(c.pop * (100 - c.s1000) / 100), sum(c.pop) filter (where c.s1000 is not null),
               count(*), count(*) filter (where c.hh = 0)
        from census c, home
        where c.cd_municipio = home."CD_MUN"::bigint
        union all
        select 'region',
               sum(c.pop), sum(c.hh), sum(c.sewage), sum(c.garbage),
               sum(c.residents_per_hh * c.hh),
               sum(c.pop) filter (where c.crowded),
               sum(c.pop * (100 - c.s1000) / 100), sum(c.pop) filter (where c.s1000 is not null),
               count(*), count(*) filter (where c.hh = 0)
        from census c
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
            'tract', "CD_SETOR", 'municipality', "NM_MUN", 'municipality_code', left("CD_MUN", 6),
            'district', "NM_DIST", 'situation', "SITUACAO") from home),
        'census', (select json_object_agg(name, json_build_object(
            'population', round(pop::numeric),
            'households', round(hh::numeric),
            'sewage_pct', round((100 * sewage / nullif(hh, 0))::numeric, 1),
            'garbage_pct', round((100 * garbage / nullif(hh, 0))::numeric, 1),
            'residents_per_household', round((residents_x_hh / nullif(hh, 0))::numeric, 2),
            'crowded_pct', round((100 * coalesce(pop_crowded, 0) / nullif(pop, 0))::numeric, 1),
            'far_primary_pct', round((100 * coalesce(pop_far, 0) / nullif(pop_access, 0))::numeric, 1),
            'tracts', tracts,
            'tracts_no_households', tracts_no_households)) from scope),
        'crowding_threshold', (select round(threshold::numeric, 2) from crowd),
        -- estimated residents of the radius by distance to the nearest public primary care unit
        'access_bands', (select json_build_object(
            'upto_500', round(coalesce(sum(pop * frac * s500 / 100), 0)::numeric),
            'upto_1000', round(coalesce(sum(pop * frac * (s1000 - s500) / 100), 0)::numeric),
            'upto_2000', round(coalesce(sum(pop * frac * (s2000 - s1000) / 100), 0)::numeric),
            'over_2000', round(coalesce(sum(pop * frac * (100 - s2000) / 100), 0)::numeric)) from tract),
        -- municipalities the radius reaches, with the estimated residents in each
        'municipalities', coalesce((select json_agg(json_build_object(
            'code', code, 'name', name, 'population', round(pop::numeric)) order by pop desc)
            from (select left(cd_mun, 6) as code, nm_mun as name, sum(pop * frac) as pop
                  from tract group by 1, 2) m
            where pop > 0), '[]'::json),
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
                    'residents_per_household', residents_per_hh,
                    'dist_primary_m', dist))) from tract), '[]'::json))
    ) end;
$$;

grant execute on function public.municipal_indicators() to anon, authenticated;

commit;

notify pgrst, 'reload schema';
