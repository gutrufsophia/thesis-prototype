-- Reference data for the storytelling service, loaded with \copy (see the README):
--   entorno_referencia: the 1 km surroundings of every mapped facility (database/reference/build_surroundings.sh)
--                       with its territorial type (analysis/typology.py)
--   resultado_esperado: observed against model-expected counts by district or municipality
--                       (analysis/outcome_relations.py); flag is set only for models used for flags

begin;

drop table if exists public.entorno_referencia;
create table public.entorno_referencia (
    cnes bigint primary key,
    tipo_equipamento text,
    rede_sus boolean,
    population numeric,
    households numeric,
    sewage_pct numeric,
    precarious_pct numeric,
    garbage_pct numeric,
    residents_per_household numeric,
    crowded_pct numeric,
    far_primary_pct numeric,
    income numeric,
    tracts integer,
    public_primary_nearby integer,
    deprived_population numeric,
    territory_type integer
);

drop table if exists public.resultado_esperado;
create table public.resultado_esperado (
    scale text not null,
    code text not null,
    name text not null,
    outcome text not null,
    observed numeric not null,
    expected numeric not null,
    lower numeric not null,
    upper numeric not null,
    flag text,
    primary key (scale, code, outcome)
);

alter table public.entorno_referencia enable row level security;
alter table public.resultado_esperado enable row level security;
grant select on public.entorno_referencia, public.resultado_esperado to anon, authenticated;
create policy "Public read" on public.entorno_referencia for select to anon, authenticated using (true);
create policy "Public read" on public.resultado_esperado for select to anon, authenticated using (true);

create or replace function public.surroundings_reference()
returns json language sql stable set search_path = public as $$
    select coalesce(json_agg(e order by e.cnes), '[]'::json) from entorno_referencia e;
$$;

create or replace function public.expected_outcomes()
returns json language sql stable set search_path = public as $$
    select coalesce(json_agg(r), '[]'::json) from resultado_esperado r;
$$;

grant execute on function public.surroundings_reference(), public.expected_outcomes() to anon, authenticated;

commit;

notify pgrst, 'reload schema';
