#!/bin/sh
# Computes the 1 km surroundings of every mapped facility with the same SQL the facility page uses
# (facility_surroundings) and writes data/surroundings_1000.csv: the reference for peer
# comparisons, need against supply, and the territorial typology.
#
# Deprived residents (union approach of Alkire & Foster 2011): residents of tracts with at least
# one of: precarious sewage for 20% or more of households; 3.1 or more residents per household
# (the region's top decile); garbage collection for 90% or fewer households; mean household-head
# income below 60% of the regional median of tract means (the Eurostat at-risk-of-poverty convention).
#
# Usage: database/reference/build_surroundings.sh [workers]   (connection from .env)
set -eu

root=$(cd "$(dirname "$0")/../.." && pwd)
eval "$(python3 -I "$root/database/pgenv.py")"
# Concurrent batches run slower than the default 2-minute limit; raise it for this session only.
export PGOPTIONS='-c statement_timeout=900000'
out="$root/data/surroundings_1000.csv"
radius=1000
batch=100
workers=${1:-3}

total=$(psql -X -q -A -t -c "select count(*) from infraestrutura_saude where coord is not null")
low_income=$(psql -X -q -A -t -c "select round(0.6 * percentile_cont(0.5) within group (order by renda_media_responsavel))
                                  from dados_censo_grande_sp where renda_media_responsavel is not null")
echo "build_surroundings: $total facilities, low-income line R\$ $low_income" >&2

run_batch() {
    psql -X -q -v ON_ERROR_STOP=1 -c "\copy (
        with f as (
            select \"CO_CNES\" as cnes, tipo_equipamento, rede_sus
            from infraestrutura_saude where coord is not null
            order by \"CO_CNES\" limit $batch offset $1),
        s as (select f.*, facility_surroundings(f.cnes, $radius)::jsonb as j from f),
        t as (
            select s.cnes, p
            from s, jsonb_array_elements(s.j->'tracts'->'features') as feature,
                 lateral (select feature->'properties' as p) props)
        select s.cnes, s.tipo_equipamento, s.rede_sus,
               (s.j->'census'->'radius'->>'population')::numeric as population,
               (s.j->'census'->'radius'->>'households')::numeric as households,
               (s.j->'census'->'radius'->>'sewage_pct')::numeric as sewage_pct,
               (s.j->'census'->'radius'->>'precarious_pct')::numeric as precarious_pct,
               (s.j->'census'->'radius'->>'garbage_pct')::numeric as garbage_pct,
               (s.j->'census'->'radius'->>'residents_per_household')::numeric as residents_per_household,
               (s.j->'census'->'radius'->>'crowded_pct')::numeric as crowded_pct,
               (s.j->'census'->'radius'->>'far_primary_pct')::numeric as far_primary_pct,
               (s.j->'census'->'radius'->>'income')::numeric as income,
               (s.j->'census'->'radius'->>'tracts')::int as tracts,
               (select count(*) from jsonb_array_elements(s.j->'facilities') n
                 where n->>'type' in ('Centro de Saúde/UBS', 'Posto de Saúde')
                   and (n->>'sus_network')::boolean) as public_primary_nearby,
               (select round(sum((p->>'population')::numeric * (p->>'share_inside')::numeric))
                  from t where t.cnes = s.cnes
                   and ((p->>'precarious_pct')::numeric >= 20
                     or (p->>'residents_per_household')::numeric >= 3.1
                     or (p->>'garbage_pct')::numeric <= 90
                     or (p->>'income')::numeric < $low_income)) as deprived_population
        from s order by s.cnes
    ) to stdout with (format csv, header false)" > "$out.part$1"
}

worker() {
    offset=$(($1 * batch))
    while [ "$offset" -lt "$total" ]; do
        run_batch "$offset"
        echo "build_surroundings: batch at $offset done" >&2
        offset=$((offset + workers * batch))
    done
}

rm -f "$out" "$out".part*
i=0
while [ "$i" -lt "$workers" ]; do
    worker "$i" &
    i=$((i + 1))
done
wait

echo "cnes,tipo_equipamento,rede_sus,population,households,sewage_pct,precarious_pct,garbage_pct,residents_per_household,crowded_pct,far_primary_pct,income,tracts,public_primary_nearby,deprived_population" > "$out"
cat "$out".part* | sort -t, -k1,1n >> "$out"
rm -f "$out".part*
echo "build_surroundings: wrote $(($(wc -l < "$out") - 1)) rows to $out" >&2
