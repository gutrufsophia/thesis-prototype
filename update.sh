#!/usr/bin/env bash
# Rebuilds the prototype's data from newly downloaded source files and loads it into the database,
# every step in order (README, "Updating the data"). Run it by hand when a source is updated; it is
# not scheduled.
#
# Usage:
#   ./update.sh [--from STEP] [--only STEP] [--dry-run]
#   steps, in order: tabnet etl geocoding seed batch load
#
# The downloaded files are given as environment variables (only those of the steps that run are
# required):
#   CNES_DIR          monthly CNES base, e.g. ~/Downloads/BASE_DE_DADOS_CNES_202608     (etl, batch)
#   LEITOS            CNES beds file, e.g. ~/Downloads/Leitos_csv_2026/Leitos_2026.csv  (etl)
#   SIH_MORBIDADE     TabNet export: SIH admissions by chapter and facility               (etl)
#   SIH_PERMANENCIA   TabNet export: SIH mean length of stay by facility                  (etl)
#   DENGUE, LEPTO     TabNet exports: dengue and leptospirosis by municipality and year   (etl)
#   CENSO_BASICO      Census 2022 basic aggregates by tract, national                     (etl)
#   CENSO_DOMICILIO   Census 2022 household aggregates (domicilio2), national             (etl)
#   RENDA_ZIP         Census 2022 household-head income by tract, national zip            (etl)
#   CNEFE_DIR         folder with the CNEFE 2022 zip of each of the 39 municipalities     (geocoding, batch)
#
# The database connection comes from DATABASE_URL in .env. Reference periods are constants: SIH
# months and TabNet years in database/tabnet/fetch_tabnet.py, SINAN years in
# backend-core/config/rules.json. fetch_sih_hospitals.py skips the files it already has, so a new
# SIH period also needs database/tabnet/raw/sih_hospitals/ emptied first.
set -euo pipefail

root=$(cd "$(dirname "$0")" && pwd)
cd "$root"

steps=(tabnet etl geocoding seed batch load)
from=${steps[0]}
only=""
dry=0
while [ $# -gt 0 ]; do
  case "$1" in
    --from) from=$2; shift 2 ;;
    --only) only=$2; shift 2 ;;
    --dry-run) dry=1; shift ;;
    -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

wanted() {
  if [ -n "$only" ]; then [ "$1" = "$only" ]; return; fi
  local started=0 s
  for s in "${steps[@]}"; do
    [ "$s" = "$from" ] && started=1
    [ "$s" = "$1" ] && { [ $started = 1 ]; return; }
  done
  return 1
}

need() {
  local v missing=0
  for v in "$@"; do
    if [ -z "${!v:-}" ]; then echo "missing environment variable $v" >&2; missing=1; fi
  done
  [ $missing = 0 ] || exit 2
}

run() {
  echo "+ $*" >&2
  [ $dry = 1 ] || "$@"
}

sql() {
  echo "+ psql <<SQL" >&2
  if [ $dry = 1 ]; then sed 's/^/    /' "$1" >&2; else psql -X -q -v ON_ERROR_STOP=1 < "$1"; fi
}

if [ $dry = 0 ] && { wanted seed || wanted batch || wanted load; }; then
  eval "$(python3 -I database/pgenv.py)"
fi

if wanted tabnet; then
  echo "== tabnet: DATASUS and SMS-SP tabulations" >&2
  run python3 -I database/tabnet/fetch_tabnet.py
fi

if wanted etl; then
  echo "== etl: cleaning and filtering to the RMSP" >&2
  need CNES_DIR LEITOS SIH_MORBIDADE SIH_PERMANENCIA DENGUE LEPTO CENSO_BASICO CENSO_DOMICILIO RENDA_ZIP
  run python3 etl/limpeza.py --cnes-dir "$CNES_DIR" --leitos "$LEITOS" \
      --sih-morbidade "$SIH_MORBIDADE" --sih-permanencia "$SIH_PERMANENCIA"
  run python3 etl/limpeza_ibge.py --basico "$CENSO_BASICO" --domicilio "$CENSO_DOMICILIO"
  run python3 etl/limpeza_datasus.py --dengue "$DENGUE" --lepto "$LEPTO"
  run python3 -I etl/limpeza_renda.py "$RENDA_ZIP"
  run python3 -I database/tabnet/build_district_indicators.py
fi

if wanted geocoding; then
  echo "== geocoding: positions from CNEFE addresses, distance from homes to primary care" >&2
  need CNEFE_DIR
  run python3 database/geocoding/geocode_cnefe.py --cnefe-dir "$CNEFE_DIR"
  run python3 database/geocoding/compute_access.py --cnefe-dir "$CNEFE_DIR"
fi

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

if wanted seed; then
  echo "== seed: facilities, census, municipal and district indicators, income" >&2
  run python3 database/seeders/seed.py --replace
  # Income (migration 012) and the district table (011) are not in seed.py
  cat > "$tmp" <<SQL
begin;
create temp table r (cd_setor text, responsaveis numeric, renda_media_responsavel numeric,
                     renda_mediana_responsavel numeric);
\copy r from 'data/renda_responsavel_rmsp.csv' with (format csv, header true)
update dados_censo_grande_sp d set responsaveis = r.responsaveis,
       renda_media_responsavel = r.renda_media_responsavel,
       renda_mediana_responsavel = r.renda_mediana_responsavel
from r where d.cd_setor = r.cd_setor::bigint;
truncate indicadores_distrito;
\copy indicadores_distrito ($(head -1 data/indicadores_distrito_sp.csv)) from 'data/indicadores_distrito_sp.csv' with (format csv, header true)
commit;
SQL
  sql "$tmp"
fi

if wanted batch; then
  echo "== batch: surroundings, typology, relations, catchments, hospital mortality" >&2
  need CNEFE_DIR CNES_DIR
  run python3 database/tabnet/fetch_sih_hospitals.py
  run database/reference/build_surroundings.sh 3
  run python3 -I analysis/typology.py
  run python3 -I analysis/outcome_relations.py
  run python3 database/reference/compute_catchment.py --cnefe-dir "$CNEFE_DIR" --cnes-dir "$CNES_DIR"
  run python3 database/reference/compute_hospital_mortality.py
fi

if wanted load; then
  echo "== load: reference tables, catchments, expected outcomes, hospital mortality" >&2
  # The commands of migrations 013, 015, 019 and 020, in one transaction
  cat > "$tmp" <<SQL
begin;
truncate entorno_referencia;
\copy entorno_referencia ($(head -1 data/surroundings_1000.csv)) from 'data/surroundings_1000.csv' with (format csv, header true)
create temp table t (cnes bigint, territory_type integer);
\copy t from 'data/surroundings_types.csv' with (format csv, header true)
update entorno_referencia e set territory_type = t.territory_type from t where t.cnes = e.cnes;
create temp table c (cnes bigint, served_population numeric, served_deprived_pct numeric,
                     mean_catchment_m numeric, edge_m numeric, near_edge boolean, teams_esf int,
                     teams_eap_20h int, teams_eap_30h int, team_equivalents numeric,
                     served_per_team numeric, served_mean_distance_m numeric, served_far_pct numeric);
\copy c from 'data/catchment_units.csv' with (format csv, header true)
update entorno_referencia e set served_population = c.served_population,
       served_deprived_pct = c.served_deprived_pct, mean_catchment_m = c.mean_catchment_m,
       edge_m = c.edge_m, near_edge = c.near_edge, teams_esf = c.teams_esf,
       teams_eap_20h = c.teams_eap_20h, teams_eap_30h = c.teams_eap_30h,
       team_equivalents = c.team_equivalents, served_per_team = c.served_per_team,
       served_mean_distance_m = c.served_mean_distance_m, served_far_pct = c.served_far_pct
from c where c.cnes = e.cnes;
truncate resultado_esperado;
\copy resultado_esperado from 'data/outcome_expected.csv' with (format csv, header true)
create temp table m (cnes bigint, admissions int, deaths int, mortality_pct numeric,
                     expected_deaths numeric, ratio numeric, expected_pct numeric,
                     lower_95 numeric, upper_95 numeric, lower_998 numeric, upper_998 numeric,
                     band text, top_chapter text, top_chapter_pct numeric,
                     region_mortality_pct numeric, profile_factor text, shapley_diagnosis_pp numeric,
                     shapley_age_pp numeric, shapley_urgency_pp numeric, old_pct numeric,
                     old_region_pct numeric, urgent_pct numeric, urgent_region_pct numeric,
                     chapter text, chapter_pct numeric, chapter_region_pct numeric,
                     chapter_rate_region_pct numeric);
\copy m from 'data/hospital_mortality.csv' with (format csv, header true)
update infraestrutura_saude i set obitos_sus = m.deaths, obitos_esperados = m.expected_deaths,
       mortalidade_faixa = m.band,
       mortalidade_perfil = jsonb_build_object(
           'taxa_regiao', m.region_mortality_pct,
           'shapley_pp', jsonb_build_object('diagnostico', m.shapley_diagnosis_pp,
                                            'idade', m.shapley_age_pp, 'carater', m.shapley_urgency_pp),
           'idosos_pct', m.old_pct, 'idosos_regiao_pct', m.old_region_pct,
           'urgencia_pct', m.urgent_pct, 'urgencia_regiao_pct', m.urgent_region_pct,
           'capitulo', m.chapter, 'capitulo_pct', m.chapter_pct,
           'capitulo_regiao_pct', m.chapter_region_pct, 'capitulo_taxa_regiao', m.chapter_rate_region_pct)
from m where m.cnes = i."CO_CNES";
commit;
SQL
  sql "$tmp"
  echo "done. The page and the storytelling service read the new data at once; restart the service" \
       "to reload its in-memory reference." >&2
fi
