"""Geocode health facilities from their street address using IBGE's CNEFE 2022.

For every facility the script tries four matching tiers, from most to least precise,
and records which one produced the coordinate:

  exact_cep     municipality + CEP + street + house number
  exact_street  municipality + street + house number (CEP differs or is wrong)
  street_cep    municipality + CEP + street, nearest house number (or street centroid
                when the facility has no number)
  cep           centroid of every CNEFE address sharing the CEP

The same procedure is run on the facilities whose CNES coordinate is already
trusted (coord_status = 'ok'). The distance to that coordinate is the measured
error of each tier, which is what makes the result reportable.

Inputs:  the cleaned CSV, the 39 CNEFE municipal zips, and DATABASE_URL in .env
         (only to read coord_status).
Outputs: database/geocoding/geocoded_facilities.csv   one row per unmapped facility
         database/geocoding/validation_by_tier.csv    measured error per tier

    python database/geocoding/geocode_cnefe.py --cnefe-dir ~/Downloads/cnefe_rmsp
"""

import argparse
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

ROOT = Path(__file__).resolve().parents[2]
HEALTH_CSV = ROOT / "culturaeduca_infraestrutura_saude_rmsp.csv"
OUT_DIR = Path(__file__).resolve().parent

TIERS = ["exact_cep", "exact_street", "street_cep", "cep"]

STREET_TYPES = {
    "RUA", "AVENIDA", "ESTRADA", "RODOVIA", "TRAVESSA", "ALAMEDA", "PRACA", "LARGO",
    "VIELA", "BECO", "VIA", "CAMINHO", "PASSAGEM", "PARQUE",
}
TYPE_ABBREVIATIONS = {
    "R": "RUA", "AV": "AVENIDA", "AVDA": "AVENIDA", "EST": "ESTRADA", "ESTR": "ESTRADA",
    "ROD": "RODOVIA", "TV": "TRAVESSA", "TRAV": "TRAVESSA", "AL": "ALAMEDA", "ALM": "ALAMEDA",
    "PCA": "PRACA", "PC": "PRACA", "PRC": "PRACA", "LGO": "LARGO", "VLA": "VIELA", "BC": "BECO",
}
TITLE_ABBREVIATIONS = {
    "DR": "DOUTOR", "DRA": "DOUTORA", "PROF": "PROFESSOR", "PROFA": "PROFESSORA",
    "CEL": "CORONEL", "GAL": "GENERAL", "ENG": "ENGENHEIRO", "STA": "SANTA", "STO": "SANTO",
    "PRES": "PRESIDENTE", "CAP": "CAPITAO", "MAL": "MARECHAL", "VER": "VEREADOR",
    "DEP": "DEPUTADO", "BRIG": "BRIGADEIRO", "TEN": "TENENTE", "SGT": "SARGENTO",
    "CONS": "CONSELHEIRO", "MONS": "MONSENHOR",
}
CONNECTIVES = {"DE", "DA", "DO", "DAS", "DOS", "E"}
NO_NUMBER = {"SN", "S N", "SEM NUMERO", "SEM NUM"}


def normalise_street(text):
    """Comparable form of a street name: no accents, no street type, no connectives."""
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().upper()
    text = re.sub(r"[^A-Z0-9 ]", " ", text)
    tokens = text.split()
    if not tokens:
        return ""
    tokens[0] = TYPE_ABBREVIATIONS.get(tokens[0], tokens[0])
    tokens = [TITLE_ABBREVIATIONS.get(t, t) for t in tokens]
    if tokens[0] in STREET_TYPES and len(tokens) > 1:
        tokens = tokens[1:]
    return " ".join(t for t in tokens if t not in CONNECTIVES)


def parse_number(text):
    if not isinstance(text, str):
        return None
    cleaned = re.sub(r"[^A-Z0-9 ]", " ", text.upper()).strip()
    if cleaned in NO_NUMBER or not cleaned:
        return None
    match = re.search(r"\d+", cleaned)
    number = int(match.group()) if match else None
    return number or None


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371000 * 2 * np.arcsin(np.sqrt(a))


def read_env(path):
    env = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip("'\"")
    return env


def load_cnefe(zip_path, ceps, streets):
    """Addresses of one municipality, reduced to those a facility could match."""
    with zipfile.ZipFile(zip_path) as archive:
        name = next(n for n in archive.namelist() if n.lower().endswith(".csv"))
        with archive.open(name) as handle:
            df = pd.read_csv(
                handle, sep=";", dtype=str, encoding="utf-8",
                usecols=["CEP", "NOM_TIPO_SEGLOGR", "NOM_TITULO_SEGLOGR", "NOM_SEGLOGR",
                         "NUM_ENDERECO", "LATITUDE", "LONGITUDE", "NV_GEO_COORD"],
            )
    parts = df[["NOM_TIPO_SEGLOGR", "NOM_TITULO_SEGLOGR", "NOM_SEGLOGR"]].fillna("")
    full = (parts["NOM_TIPO_SEGLOGR"] + " " + parts["NOM_TITULO_SEGLOGR"] + " " + parts["NOM_SEGLOGR"]).str.strip()
    lookup = {text: normalise_street(text) for text in full.unique()}
    df["street"] = full.map(lookup)
    df = df[df["CEP"].isin(ceps) | df["street"].isin(streets)].copy()
    df["num"] = pd.to_numeric(df["NUM_ENDERECO"], errors="coerce").replace(0, np.nan)
    df["lat"] = pd.to_numeric(df["LATITUDE"], errors="coerce")
    df["lon"] = pd.to_numeric(df["LONGITUDE"], errors="coerce")
    # 1-2: surveyed at the address; 3: estimated; 4-6: block face, locality, tract
    df["level"] = pd.to_numeric(df["NV_GEO_COORD"], errors="coerce").fillna(9).astype(int)
    return df.dropna(subset=["lat", "lon"])[["CEP", "street", "num", "lat", "lon", "level"]]


def centroid(points, tier, **extra):
    # use only the best-surveyed coordinates available among the matching addresses
    geo_level = int(points["level"].min())
    points = points[points["level"] == geo_level]
    extra["geo_level"] = geo_level
    lat, lon = points["lat"].median(), points["lon"].median()
    spread = float(haversine_m(lat, lon, points["lat"].to_numpy(), points["lon"].to_numpy()).max())
    return {"tier": tier, "lat": lat, "lon": lon, "n_points": len(points), "spread_m": round(spread, 1), **extra}


def match(facility, by_cep, by_street):
    """Best available tier for one facility, or None."""
    cep, street, muni = facility.cep, facility.street, facility.muni
    # a missing number reaches this point as NaN
    number = None if pd.isna(facility.number) else int(facility.number)
    in_cep = by_cep.get((muni, cep))
    if in_cep is not None and street and number is not None:
        hit = in_cep[(in_cep["street"] == street) & (in_cep["num"] == number)]
        if len(hit):
            return centroid(hit, "exact_cep")
    in_street = by_street.get((muni, street)) if street else None
    if in_street is not None and number is not None:
        hit = in_street[in_street["num"] == number]
        if len(hit):
            return centroid(hit, "exact_street")
    if in_cep is not None and street:
        same = in_cep[in_cep["street"] == street]
        if len(same):
            if number is not None and same["num"].notna().any():
                gap = (same["num"] - number).abs()
                nearest = same[gap == gap.min()]
                return centroid(nearest, "street_cep", number_gap=int(gap.min()))
            return centroid(same, "street_cep", number_gap=None)
    if in_cep is not None and len(in_cep):
        return centroid(in_cep, "cep")
    return None


def degraded(facility, by_cep, exact):
    """What the coarser tiers would return if this exactly-matched address were absent
    from CNEFE, as distances (m) from the exact point. Measures the coarse tiers without
    relying on CNES coordinates."""
    number = int(facility.number)
    in_cep = by_cep[(facility.muni, facility.cep)]
    others = in_cep[~((in_cep["street"] == facility.street) & (in_cep["num"] == number))]
    out = {}
    same = others[(others["street"] == facility.street) & others["num"].notna()]
    if len(same):
        gap = (same["num"] - number).abs()
        point = centroid(same[gap == gap.min()], "street_cep")
        out["street_cep_m"] = float(haversine_m(point["lat"], point["lon"], exact["lat"], exact["lon"]))
    if len(others):
        point = centroid(others, "cep")
        out["cep_m"] = float(haversine_m(point["lat"], point["lon"], exact["lat"], exact["lon"]))
    return out


def quantiles(values):
    return {
        "n": len(values), "median_m": round(values.median()), "p75_m": round(values.quantile(0.75)),
        "p90_m": round(values.quantile(0.90)), "p95_m": round(values.quantile(0.95)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cnefe-dir", required=True, type=Path)
    args = parser.parse_args()

    health = pd.read_csv(HEALTH_CSV, dtype=str)
    health["cnes"] = health["CO_CNES"].str.zfill(7)
    health["muni"] = health["CO_MUNICIPIO_GESTOR"].str.slice(0, 6)
    health["cep"] = health["CO_CEP"].str.zfill(8)
    health["street"] = health["NO_LOGRADOURO"].map(normalise_street)
    health["number"] = health["NU_ENDERECO"].map(parse_number)

    conn = psycopg2.connect(read_env(ROOT / ".env")["DATABASE_URL"])
    with conn.cursor() as cur:
        cur.execute('select "CO_CNES"::text, coord_status, st_y(coord::geometry), st_x(coord::geometry) from public.infraestrutura_saude')
        status = pd.DataFrame(cur.fetchall(), columns=["cnes", "coord_status", "ref_lat", "ref_lon"])
    conn.close()
    status["cnes"] = status["cnes"].str.zfill(7)
    health = health.merge(status, on="cnes", how="left")

    results, coarse = [], []
    for zip_path in sorted(args.cnefe_dir.glob("*.zip")):
        muni7 = zip_path.name.split("_")[0]
        muni6 = muni7[:6]
        local = health[health["muni"] == muni6]
        if local.empty:
            continue
        cnefe = load_cnefe(zip_path, set(local["cep"].dropna()), set(local["street"]) - {""})
        cnefe["muni"] = muni6
        by_cep = {key: group for key, group in cnefe.groupby(["muni", "CEP"])}
        by_street = {key: group for key, group in cnefe.groupby(["muni", "street"])}
        for facility in local.itertuples():
            found = match(facility, by_cep, by_street)
            if found:
                results.append({"cnes": facility.cnes, **found})
                if found["tier"] == "exact_cep" and found["geo_level"] == 1:
                    coarse.append(degraded(facility, by_cep, found))
        print(f"{zip_path.name}: {len(local)} facilities, {len(cnefe)} candidate addresses", flush=True)

    matched = pd.DataFrame(results).merge(health[["cnes", "coord_status", "ref_lat", "ref_lon"]], on="cnes")

    trusted = matched[matched["coord_status"] == "ok"].copy()
    trusted["error_m"] = haversine_m(trusted["lat"], trusted["lon"], trusted["ref_lat"], trusted["ref_lon"])
    rows = []
    for tier in TIERS:
        errors = trusted.loc[trusted["tier"] == tier, "error_m"]
        if len(errors):
            rows.append({
                "tier": tier, "n_validated": len(errors),
                "median_m": round(errors.median()), "p75_m": round(errors.quantile(0.75)),
                "p90_m": round(errors.quantile(0.90)), "p95_m": round(errors.quantile(0.95)),
                "share_within_100m": round((errors <= 100).mean(), 3),
                "share_within_250m": round((errors <= 250).mean(), 3),
            })
    validation = pd.DataFrame(rows)
    validation.to_csv(OUT_DIR / "validation_by_tier.csv", index=False)
    trusted[["cnes", "tier", "geo_level", "n_points", "spread_m", "lat", "lon", "ref_lat", "ref_lon", "error_m"]].to_csv(OUT_DIR / "validation_detail.csv", index=False)

    coarse = pd.DataFrame(coarse)
    precision = pd.DataFrame([
        {"tier": "street_cep", **quantiles(coarse["street_cep_m"].dropna())},
        {"tier": "cep", **quantiles(coarse["cep_m"].dropna())},
    ])
    precision.to_csv(OUT_DIR / "coarse_tier_precision.csv", index=False)
    print("\nCoarse tiers measured against the exact CNEFE point (leave-one-out):")
    print(precision.to_string(index=False))

    unmapped = matched[matched["coord_status"] != "ok"].drop(columns=["ref_lat", "ref_lon"])
    unmapped.to_csv(OUT_DIR / "geocoded_facilities.csv", index=False)

    total_unmapped = int((health["coord_status"] != "ok").sum())
    print("\nDisagreement with the CNES coordinate, facilities with coord_status = ok:")
    print(validation.to_string(index=False))
    print(f"\nUnmapped facilities: {total_unmapped}; matched: {len(unmapped)}")
    print(unmapped["tier"].value_counts().reindex(TIERS).fillna(0).astype(int).to_string())


if __name__ == "__main__":
    sys.exit(main())
