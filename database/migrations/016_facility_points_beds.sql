-- facility_points with each facility's existing beds appended, so the map can draw hospitals as
-- proportional symbols: a 300-bed hospital was the same 5-pixel dot as a laboratory. The first
-- seven fields are unchanged, so the previous frontend keeps working.

create or replace function public.facility_points()
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

grant execute on function public.facility_points() to anon, authenticated;

notify pgrst, 'reload schema';
