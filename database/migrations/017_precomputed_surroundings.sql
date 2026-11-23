-- 017_precomputed_surroundings.sql
--
-- facility_surroundings and municipal_indicators used to read every tract on every call: the
-- crowding threshold over all tracts, the census x access join, and the municipal and regional
-- sums. That work depended on the size of the whole table (about 90% of a 1 km call), not on the
-- circle, and would grow tenfold with national data. It now lives in tables refreshed once per data
-- load, so a call costs the tracts in the circle (GiST) plus key lookups. The JSON the functions
-- return is unchanged; see docs/monograph-log.md, 2026-11-22.
--
-- The derived tables are rebuilt by refresh_surroundings_tables(), which statement-level triggers
-- on the census and access tables call after any load, so they cannot fall out of step.
--
-- Idempotent.

begin;

-- Indexes the loaders created; recorded here so that a fresh database gets them too.
create index if not exists idx_setores_censitarios_grande_sp_geometry
    on public.setores_censitarios_grande_sp using gist (geometry);
create index if not exists idx_infra_saude_coord on public.infraestrutura_saude using gist (coord);
create index if not exists idx_dados_censo_municipio on public.dados_censo_grande_sp (cd_municipio);

-- Every tract outline is valid, so the overlay no longer repairs geometries per call; keep it so.
alter table public.setores_censitarios_grande_sp drop constraint if exists setores_geometry_valid;
alter table public.setores_censitarios_grande_sp
    add constraint setores_geometry_valid check (extensions.st_isvalid(geometry));

-- 1. Derived tables. Created from the same expressions the functions used, so the column types,
--    and therefore the arithmetic, are the same.

-- "crowded" = among the 10% of tracts with most residents per household
create table if not exists public.limiar_adensamento as
    select percentile_cont(0.9) within group (order by media_moradores_domicilio) as threshold
    from public.dados_censo_grande_sp
    where total_domicilios_ocupados > 0
with no data;

create table if not exists public.setor_entorno as
    select c.cd_setor, c.cd_municipio,
           c.populacao_total as pop, c.total_domicilios_ocupados as hh,
           c.esgoto_rede_geral as sewage, c.total_lixo_coletado as garbage, c.esgoto_precario as precarious,
           c.domicilios_esgoto_informado as sewage_den, c.domicilios_lixo_informado as garbage_den,
           c.media_moradores_domicilio as residents_per_hh,
           c.renda_media_responsavel as income, c.responsaveis as heads,
           a.pct_ate_500 as s500, a.pct_ate_1000 as s1000, a.pct_ate_2000 as s2000,
           a.dist_mediana_m as dist,
           (c.total_domicilios_ocupados > 0 and c.media_moradores_domicilio >= l.threshold) as crowded
    from public.dados_censo_grande_sp c
    cross join public.limiar_adensamento l
    left join public.setor_acesso a on a.cd_setor = c.cd_setor
with no data;

-- Sums per municipality and for the whole region (code 0)
create table if not exists public.entorno_agregado as
    select 'municipality'::text as scope, c.cd_municipio as code,
           sum(c.pop) as pop, sum(c.hh) as hh, sum(c.sewage) as sewage, sum(c.garbage) as garbage,
           sum(c.precarious) as precarious, sum(c.sewage_den) as sewage_den, sum(c.garbage_den) as garbage_den,
           sum(c.residents_per_hh * c.hh) as residents_x_hh,
           sum(c.pop) filter (where c.crowded) as pop_crowded,
           sum(c.pop * (100 - c.s1000) / 100) as pop_far,
           sum(c.pop) filter (where c.s1000 is not null) as pop_access,
           count(*) as tracts, count(*) filter (where c.hh = 0) as tracts_no_households,
           sum(c.income * c.heads) as income_x_heads,
           sum(c.heads) filter (where c.income is not null) as heads_with_income
    from public.setor_entorno c
    group by c.cd_municipio
with no data;

create table if not exists public.municipio_referencia as
    select p.code, n.nome, p.populacao
    from (select left(cd_municipio::text, 6) as code, sum(populacao_total) as populacao
          from public.dados_censo_grande_sp group by 1) p
    join (select distinct left("CD_MUN", 6) as code, "NM_MUN" as nome
          from public.setores_censitarios_grande_sp) n on n.code = p.code
with no data;

alter table public.setor_entorno drop constraint if exists setor_entorno_pkey;
alter table public.setor_entorno add constraint setor_entorno_pkey primary key (cd_setor);
alter table public.entorno_agregado drop constraint if exists entorno_agregado_pkey;
alter table public.entorno_agregado add constraint entorno_agregado_pkey primary key (scope, code);
create index if not exists idx_municipio_referencia_code on public.municipio_referencia (code);

create or replace function public.refresh_surroundings_tables()
returns void
language plpgsql
set search_path = public, extensions
as $$
begin
    truncate limiar_adensamento;
    insert into limiar_adensamento
        select percentile_cont(0.9) within group (order by media_moradores_domicilio)
        from dados_censo_grande_sp
        where total_domicilios_ocupados > 0;

    truncate setor_entorno;
    insert into setor_entorno
        select c.cd_setor, c.cd_municipio,
               c.populacao_total, c.total_domicilios_ocupados,
               c.esgoto_rede_geral, c.total_lixo_coletado, c.esgoto_precario,
               c.domicilios_esgoto_informado, c.domicilios_lixo_informado,
               c.media_moradores_domicilio,
               c.renda_media_responsavel, c.responsaveis,
               a.pct_ate_500, a.pct_ate_1000, a.pct_ate_2000,
               a.dist_mediana_m,
               (c.total_domicilios_ocupados > 0 and c.media_moradores_domicilio >= l.threshold)
        from dados_censo_grande_sp c
        cross join limiar_adensamento l
        left join setor_acesso a on a.cd_setor = c.cd_setor;

    truncate entorno_agregado;
    insert into entorno_agregado
        select s.scope, s.code,
               sum(c.pop), sum(c.hh), sum(c.sewage), sum(c.garbage), sum(c.precarious),
               sum(c.sewage_den), sum(c.garbage_den),
               sum(c.residents_per_hh * c.hh),
               sum(c.pop) filter (where c.crowded),
               sum(c.pop * (100 - c.s1000) / 100),
               sum(c.pop) filter (where c.s1000 is not null),
               count(*), count(*) filter (where c.hh = 0),
               sum(c.income * c.heads),
               sum(c.heads) filter (where c.income is not null)
        from setor_entorno c
        cross join lateral (values ('municipality', c.cd_municipio), ('region', 0::bigint)) as s(scope, code)
        group by s.scope, s.code;

    truncate municipio_referencia;
    insert into municipio_referencia
        select p.code, n.nome, p.populacao
        from (select left(cd_municipio::text, 6) as code, sum(populacao_total) as populacao
              from dados_censo_grande_sp group by 1) p
        join (select distinct left("CD_MUN", 6) as code, "NM_MUN" as nome
              from setores_censitarios_grande_sp) n on n.code = p.code;
end;
$$;

revoke all on function public.refresh_surroundings_tables() from public, anon, authenticated;

create or replace function public.refresh_surroundings_tables_trigger()
returns trigger
language plpgsql
set search_path = public, extensions
as $$
begin
    perform refresh_surroundings_tables();
    return null;
end;
$$;

revoke all on function public.refresh_surroundings_tables_trigger() from public, anon, authenticated;

drop trigger if exists refresh_surroundings on public.dados_censo_grande_sp;
create trigger refresh_surroundings
    after insert or update or delete or truncate on public.dados_censo_grande_sp
    for each statement execute function public.refresh_surroundings_tables_trigger();
drop trigger if exists refresh_surroundings on public.setor_acesso;
create trigger refresh_surroundings
    after insert or update or delete or truncate on public.setor_acesso
    for each statement execute function public.refresh_surroundings_tables_trigger();
-- the municipality names come from the tract table
drop trigger if exists refresh_surroundings on public.setores_censitarios_grande_sp;
create trigger refresh_surroundings
    after insert or delete or truncate on public.setores_censitarios_grande_sp
    for each statement execute function public.refresh_surroundings_tables_trigger();

select public.refresh_surroundings_tables();

-- Read-only, like the other tables of the public API
do $$
declare t text;
begin
    foreach t in array array['limiar_adensamento', 'setor_entorno', 'entorno_agregado', 'municipio_referencia'] loop
        execute format('alter table public.%I enable row level security', t);
        execute format('revoke all on public.%I from anon, authenticated', t);
        execute format('grant select on public.%I to anon, authenticated', t);
        execute format('drop policy if exists "Public read" on public.%I', t);
        execute format('create policy "Public read" on public.%I for select using (true)', t);
    end loop;
end;
$$;

-- 2. The functions, reading the derived tables. Output unchanged.

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
            s."CD_SETOR" as cd_setor, s."CD_MUN" as cd_mun, s."NM_MUN" as nm_mun,
            s.geometry as geom, w.frac,
            c.pop, c.hh, c.sewage, c.garbage, c.precarious, c.sewage_den, c.garbage_den, c.residents_per_hh, c.dist, c.crowded,
            c.s500, c.s1000, c.s2000, c.income, c.heads
        from circle
        join setores_censitarios_grande_sp s
            on s.geometry && circle.g and st_intersects(s.geometry, circle.g)
        cross join lateral (
            select least(1, coalesce(
                st_area(st_intersection(s.geometry, circle.g)) / nullif(st_area(s.geometry), 0), 0
            )) as frac
        ) w
        left join setor_entorno c on c.cd_setor = s."CD_SETOR"::bigint
        where w.frac > 0
    ),
    scope as (
        select 'radius' as name,
               sum(pop * frac) as pop, sum(hh * frac) as hh,
               sum(sewage * frac) as sewage, sum(garbage * frac) as garbage, sum(precarious * frac) as precarious,
               sum(sewage_den * frac) as sewage_den, sum(garbage_den * frac) as garbage_den,
               sum(residents_per_hh * hh * frac) as residents_x_hh,
               sum(pop * frac) filter (where crowded) as pop_crowded,
               sum(pop * frac * (100 - s1000) / 100) as pop_far,
               sum(pop * frac) filter (where s1000 is not null) as pop_access,
               count(*) as tracts,
               count(*) filter (where coalesce(hh, 0) = 0) as tracts_no_households,
               sum(income * heads * frac) as income_x_heads,
               sum(heads * frac) filter (where income is not null) as heads_with_income
        from tract
        union all
        select 'municipality',
               a.pop, a.hh, a.sewage, a.garbage, a.precarious, a.sewage_den, a.garbage_den,
               a.residents_x_hh, a.pop_crowded, a.pop_far, a.pop_access,
               coalesce(a.tracts, 0), coalesce(a.tracts_no_households, 0),
               a.income_x_heads, a.heads_with_income
        from (select 1) one
        left join home on true
        left join entorno_agregado a on a.scope = 'municipality' and a.code = home."CD_MUN"::bigint
        union all
        select 'region',
               a.pop, a.hh, a.sewage, a.garbage, a.precarious, a.sewage_den, a.garbage_den,
               a.residents_x_hh, a.pop_crowded, a.pop_far, a.pop_access,
               a.tracts, a.tracts_no_households, a.income_x_heads, a.heads_with_income
        from entorno_agregado a
        where a.scope = 'region' and a.code = 0
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
            'sewage_pct', round((100 * sewage / nullif(sewage_den, 0))::numeric, 1),
            'precarious_pct', round((100 * precarious / nullif(sewage_den, 0))::numeric, 1),
            'garbage_pct', round((100 * garbage / nullif(garbage_den, 0))::numeric, 1),
            'residents_per_household', round((residents_x_hh / nullif(hh, 0))::numeric, 2),
            'crowded_pct', round((100 * coalesce(pop_crowded, 0) / nullif(pop, 0))::numeric, 1),
            'far_primary_pct', round((100 * coalesce(pop_far, 0) / nullif(pop_access, 0))::numeric, 1),
            -- mean income of household heads with income, weighted by the number of heads
            'income', round((income_x_heads / nullif(heads_with_income, 0))::numeric),
            'tracts', tracts,
            'tracts_no_households', tracts_no_households)) from scope),
        'crowding_threshold', (select round(threshold::numeric, 2) from limiar_adensamento),
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
                    'sewage_pct', round((100.0 * sewage / nullif(sewage_den, 0))::numeric, 1),
                    'precarious_pct', round((100.0 * precarious / nullif(sewage_den, 0))::numeric, 1),
                    'garbage_pct', round((100.0 * garbage / nullif(garbage_den, 0))::numeric, 1),
                    'residents_per_household', residents_per_hh,
                    'income', round(income::numeric),
                    'dist_primary_m', dist))) from tract), '[]'::json))
    ) end;
$$;

create or replace function public.municipal_indicators()
returns json
language sql
stable
set search_path = public, extensions
as $$
    select coalesce(json_agg(to_jsonb(i) || jsonb_build_object('nome', m.nome, 'populacao', m.populacao)), '[]'::json)
    from indicadores_municipio i
    join municipio_referencia m on m.code = i.cd_municipio6;
$$;

-- 3. Facilities in a map view, for national data, where sending every point at once would not do.
--    Same row layout as facility_points(); the prototype's map still uses facility_points().
create or replace function public.facility_points_in_view(p_west double precision, p_south double precision,
                                                          p_east double precision, p_north double precision)
returns json
language sql
stable
set search_path = public, extensions
as $$
    select json_build_object(
        -- [cnes, name, type, lat, lon, coord_source, rede_sus, beds]
        'points', coalesce((
            select json_agg(json_build_array(
                f."CO_CNES",
                coalesce(nullif(btrim(f."NO_FANTASIA"), ''), f."NO_RAZAO_SOCIAL"),
                f.tipo_equipamento,
                round(st_y(f.coord::geometry)::numeric, 6),
                round(st_x(f.coord::geometry)::numeric, 6),
                f.coord_source,
                coalesce(f.rede_sus, false),
                coalesce(f."LEITOS_EXISTENTES", 0)
            ))
            from infraestrutura_saude f
            where f.coord && st_makeenvelope(p_west, p_south, p_east, p_north, 4326)::geography
        ), '[]'::json)
    );
$$;

grant execute on function public.facility_surroundings(bigint, integer) to anon, authenticated;
grant execute on function public.municipal_indicators() to anon, authenticated;
grant execute on function public.facility_points_in_view(double precision, double precision, double precision, double precision)
    to anon, authenticated;

commit;

notify pgrst, 'reload schema';
