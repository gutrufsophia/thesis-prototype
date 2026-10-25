"""Load the cleaned CNES and census CSVs into Supabase.

Run after the SQL files in database/migrations/:

    python database/seeders/seed.py

Reads DATABASE_URL from the .env file in the repository root. Refuses to touch a
table that already has rows unless --replace is given.
"""

import argparse
import io
import sys
from pathlib import Path

import pandas as pd
import psycopg2

ROOT = Path(__file__).resolve().parents[2]
HEALTH_CSV = ROOT / "data" / "culturaeduca_infraestrutura_saude_rmsp.csv"
CENSUS_CSV = ROOT / "data" / "dados_censo_culturaeduca.csv"
HEALTH_TABLE = "infraestrutura_saude"
CENSUS_TABLE = "dados_censo_grande_sp"
MUNICIPAL_CSV = ROOT / "data" / "indicadores_municipais_rmsp.csv"
MUNICIPAL_TABLE = "indicadores_municipio"
ACCESS_TABLE = "setor_acesso"
ACCESS_CSV = ROOT / "database" / "geocoding" / "setor_acesso.csv"
PRIMARY_CARE_TYPES = ("Centro de Saúde/UBS", "Posto de Saúde")
GEOCODED_CSV = ROOT / "database" / "geocoding" / "geocoded_facilities.csv"
VALIDATION_CSV = ROOT / "database" / "geocoding" / "validation_detail.csv"
EVIDENCE_CSV = ROOT / "database" / "geocoding" / "establishment_evidence.csv"

# Geocoding acceptance rules, derived from the validation outputs in database/geocoding/.
# Matched CNEFE addresses farther apart than this are treated as ambiguous
# (e.g. two streets with the same name) and fall back to CEP-level precision.
AMBIGUOUS_SPREAD_M = 100
# 90th percentile error of the nearest-house-number tier, measured by leave-one-out
STREET_PRECISION_M = 103
# A CEP whose addresses spread farther than this is too coarse to place a facility
MAX_CEP_SPREAD_M = 1000
# A CNES coordinate farther than this from the CNEFE address of the same street, number
# and CEP is replaced by the address position. Wherever the two differ by more than 50 m
# and the census recorded a health establishment with the facility's name at one of them,
# it was at the address in about 95% of cases (430 against 23). Below 50 m the two are
# equivalent. Facilities the census recorded at the CNES point keep the CNES coordinate.
CORRECTION_THRESHOLD_M = 50

# A coordinate with at most this many decimals, shared by at least this many
# facilities, is a municipal-centroid placeholder rather than a real location.
PLACEHOLDER_MAX_DECIMALS = 3
PLACEHOLDER_MIN_SHARED = 3


def read_env(path):
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip("'\"")
    return env


def table_types(cur, table):
    cur.execute(
        "select column_name, data_type from information_schema.columns "
        "where table_schema = 'public' and table_name = %s",
        (table,),
    )
    return dict(cur.fetchall())


def cast_to_table(df, types):
    """Coerce CSV text columns to the types of the destination table."""
    out = pd.DataFrame(index=df.index)
    for column in df.columns:
        if types[column] in ("bigint", "integer"):
            out[column] = pd.to_numeric(df[column], errors="coerce").round().astype("Int64")
        elif types[column] in ("double precision", "numeric"):
            out[column] = pd.to_numeric(df[column], errors="coerce")
        else:
            out[column] = df[column]
    return out


def decimals(series):
    return series.str.split(".").str[1].str.len().fillna(0)


def locate(df):
    """Derive the PostGIS point and a quality flag from the raw CNES coordinates."""
    # CNES mixes decimal points and decimal commas
    lat_text = df["NU_LATITUDE"].str.strip().str.replace(",", ".")
    lon_text = df["NU_LONGITUDE"].str.strip().str.replace(",", ".")
    lat = pd.to_numeric(lat_text, errors="coerce")
    lon = pd.to_numeric(lon_text, errors="coerce")

    status = pd.Series("ok", index=df.index)
    status[lat.isna() | lon.isna()] = "missing"

    shared = df.assign(lat=lat, lon=lon).groupby(["lat", "lon"])["CO_CNES"].transform("size")
    low_precision = (decimals(lat_text) <= PLACEHOLDER_MAX_DECIMALS) & (
        decimals(lon_text) <= PLACEHOLDER_MAX_DECIMALS
    )
    status[(status == "ok") & low_precision & (shared >= PLACEHOLDER_MIN_SHARED)] = "placeholder"

    ok = status == "ok"
    coord = pd.Series(pd.NA, index=df.index, dtype="object")
    coord[ok] = "SRID=4326;POINT(" + lon[ok].astype(str) + " " + lat[ok].astype(str) + ")"
    return coord, status


def classify_geocoded(geocoded):
    """Turn matching tiers into a coordinate source and a precision in metres."""
    tight = geocoded["spread_m"] <= AMBIGUOUS_SPREAD_M
    exact = geocoded["tier"].isin(["exact_cep", "exact_street"]) & tight
    street = (geocoded["tier"] == "street_cep") & tight
    out = geocoded.copy()
    out["coord_source"] = "cnefe_cep"
    out.loc[street, "coord_source"] = "cnefe_street"
    out.loc[exact, "coord_source"] = "cnefe_address"
    # for CEP-level points the farthest address of the CEP bounds the error
    # (never claimed tighter than the street tier)
    out["coord_precision_m"] = out["spread_m"].clip(lower=STREET_PRECISION_M).round().astype("Int64")
    out.loc[street, "coord_precision_m"] = STREET_PRECISION_M
    out.loc[exact, "coord_precision_m"] = pd.NA
    return out[(out["coord_source"] != "cnefe_cep") | (out["spread_m"] <= MAX_CEP_SPREAD_M)]


def apply_geocoding(cur):
    """Give CNEFE-derived coordinates to facilities CNES could not place."""
    if not GEOCODED_CSV.exists():
        print("no geocoded_facilities.csv; facilities without CNES coordinates stay unmapped")
        return
    geocoded = classify_geocoded(pd.read_csv(GEOCODED_CSV))
    for row in geocoded.itertuples():
        precision = None if pd.isna(row.coord_precision_m) else int(row.coord_precision_m)
        cur.execute(
            f"""
            update public.{HEALTH_TABLE} f
            set coord = st_setsrid(st_makepoint(%s, %s), 4326)::geography,
                coord_source = %s, coord_precision_m = %s
            where f."CO_CNES" = %s and f.coord is null
              and exists (
                  select 1 from public.setores_censitarios_grande_sp s
                  where st_intersects(s.geometry, st_setsrid(st_makepoint(%s, %s), 4326)))
            """,
            (row.lon, row.lat, row.coord_source, precision, int(row.cnes), row.lon, row.lat),
        )


def apply_corrections(cur):
    """Replace CNES coordinates that contradict an exact, door-surveyed CNEFE address."""
    if not VALIDATION_CSV.exists():
        print("no validation_detail.csv; CNES coordinates are left as they are")
        return
    detail = pd.read_csv(VALIDATION_CSV)
    if EVIDENCE_CSV.exists():
        evidence = pd.read_csv(EVIDENCE_CSV)[["cnes", "verdict"]]
        detail = detail.merge(evidence, on="cnes", how="left")
    else:
        detail["verdict"] = None
    wrong = detail[
        (detail["tier"] == "exact_cep")
        & (detail["geo_level"] == 1)
        & (detail["spread_m"] <= AMBIGUOUS_SPREAD_M)
        & (detail["error_m"] > CORRECTION_THRESHOLD_M)
        & (detail["verdict"] != "cnes")
    ]
    for row in wrong.itertuples():
        cur.execute(
            f"""
            update public.{HEALTH_TABLE} f
            set coord = st_setsrid(st_makepoint(%s, %s), 4326)::geography,
                coord_source = 'cnefe_corrected', coord_shift_m = %s
            where f."CO_CNES" = %s and f.coord_source = 'cnes'
              and exists (
                  select 1 from public.setores_censitarios_grande_sp s
                  where st_intersects(s.geometry, st_setsrid(st_makepoint(%s, %s), 4326)))
            """,
            (row.lon, row.lat, round(row.error_m), int(row.cnes), row.lon, row.lat),
        )


def load_access(cur):
    """Load the per-tract access summary produced by database/geocoding/compute_access.py."""
    cur.execute(f"truncate public.{ACCESS_TABLE}")
    if not ACCESS_CSV.exists():
        print("no setor_acesso.csv; primary care access will be empty")
        return
    access = pd.read_csv(ACCESS_CSV, dtype=str)
    copy_frame(cur, ACCESS_TABLE, cast_to_table(access, table_types(cur, ACCESS_TABLE)))


def copy_frame(cur, table, df):
    buffer = io.StringIO()
    df.to_csv(buffer, index=False, header=False)
    buffer.seek(0)
    columns = ", ".join(f'"{c}"' for c in df.columns)
    cur.copy_expert(f"copy public.{table} ({columns}) from stdin with (format csv)", buffer)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--replace", action="store_true", help="empty the tables before loading")
    args = parser.parse_args()

    database_url = read_env(ROOT / ".env").get("DATABASE_URL")
    if not database_url:
        sys.exit("DATABASE_URL is not set in .env")

    conn = psycopg2.connect(database_url, options="-c search_path=public,extensions")
    with conn, conn.cursor() as cur:
        for table in (HEALTH_TABLE, CENSUS_TABLE, MUNICIPAL_TABLE):
            cur.execute(f"select count(*) from public.{table}")
            rows = cur.fetchone()[0]
            if rows and not args.replace:
                sys.exit(f"{table} already has {rows} rows; rerun with --replace to overwrite")
            if rows:
                cur.execute(f"truncate public.{table}")

        health_raw = pd.read_csv(HEALTH_CSV, dtype=str)
        health = cast_to_table(health_raw, table_types(cur, HEALTH_TABLE))
        health["coord"], health["coord_status"] = locate(health_raw)
        copy_frame(cur, HEALTH_TABLE, health)

        census_raw = pd.read_csv(CENSUS_CSV, dtype=str)
        copy_frame(cur, CENSUS_TABLE, cast_to_table(census_raw, table_types(cur, CENSUS_TABLE)))

        municipal_raw = pd.read_csv(MUNICIPAL_CSV, dtype=str)
        copy_frame(cur, MUNICIPAL_TABLE, cast_to_table(municipal_raw, table_types(cur, MUNICIPAL_TABLE)))

        # A point that falls in no RMSP census tract cannot be related to the territory
        cur.execute(
            f"""
            update public.{HEALTH_TABLE} f
            set coord = null, coord_status = 'out_of_region'
            where f.coord is not null
              and not exists (
                  select 1 from public.setores_censitarios_grande_sp s
                  where st_intersects(s.geometry, f.coord::geometry))
            """
        )
        cur.execute(f"update public.{HEALTH_TABLE} set coord_source = 'cnes' where coord is not null")
        apply_geocoding(cur)
        apply_corrections(cur)
        load_access(cur)
        cur.execute(f"analyze public.{HEALTH_TABLE}")
        cur.execute(f"analyze public.{CENSUS_TABLE}")
        cur.execute(f"analyze public.{ACCESS_TABLE}")

        cur.execute(f"select count(*) from public.{CENSUS_TABLE}")
        print(f"{CENSUS_TABLE}: {cur.fetchone()[0]} rows")
        cur.execute(
            f"select coord_status, count(*) from public.{HEALTH_TABLE} group by 1 order by 2 desc"
        )
        print(f"{HEALTH_TABLE} by coord_status:")
        for status, count in cur.fetchall():
            print(f"  {status}: {count}")
        cur.execute(
            f"select coalesce(coord_source, 'unmapped'), count(*) from public.{HEALTH_TABLE} group by 1 order by 2 desc"
        )
        print(f"{HEALTH_TABLE} by coord_source:")
        for source, count in cur.fetchall():
            print(f"  {source}: {count}")
    conn.close()


if __name__ == "__main__":
    main()
