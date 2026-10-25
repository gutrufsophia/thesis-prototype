"""Audit every CNES coordinate replaced by the 1 km rule, one facility at a time.

Two tests, both independent of CNEFE:

  1. Municipality test: does the original CNES point fall inside the municipality
     the facility is registered in?
  2. Third geocoder: where does OpenStreetMap's Nominatim place the address, and
     which of the two candidate positions is it close to?

Writes database/geocoding/corrections_audit.csv with a verdict per facility.
Run after geocode_cnefe.py. Respects Nominatim's one-request-per-second policy.

    python database/geocoding/audit_corrections.py
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
import requests

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "database" / "seeders"))
from seed import AMBIGUOUS_SPREAD_M, CORRECTION_THRESHOLD_M, read_env  # noqa: E402

NOMINATIM = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "culturaeduca-health-thesis-prototype/0.1 (academic geocoding validation)"}
# The third source "confirms" a position when it lands this close to it and at
# least FAR_M from the other one.
HOUSE_LEVEL = ["amenity", "building", "healthcare", "office", "shop"]
NEAR_M = 500
FAR_M = 1000


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371000 * 2 * np.arcsin(np.sqrt(a))


def municipality_of_points(points):
    """IBGE code of the RMSP municipality containing each (cnes, lat, lon), or None."""
    conn = psycopg2.connect(read_env(ROOT / ".env")["DATABASE_URL"], options="-c search_path=public,extensions")
    found = {}
    with conn.cursor() as cur:
        for cnes, lat, lon in points:
            cur.execute(
                'select "CD_MUN" from setores_censitarios_grande_sp '
                "where st_intersects(geometry, st_setsrid(st_makepoint(%s, %s), 4326)) limit 1",
                (lon, lat),
            )
            hit = cur.fetchone()
            found[cnes] = hit[0] if hit else None
    conn.close()
    return found


def verdict(row):
    if pd.isna(row.osm_to_cnefe_m):
        return "no_third_source"
    if row.osm_to_cnefe_m <= NEAR_M and row.osm_to_cnes_m >= FAR_M:
        return "cnefe_confirmed"
    if row.osm_to_cnes_m <= NEAR_M and row.osm_to_cnefe_m >= FAR_M:
        return "cnes_confirmed"
    return "inconclusive"


def main():
    detail = pd.read_csv(HERE / "validation_detail.csv", dtype={"cnes": str})
    detail["cnes"] = detail["cnes"].str.zfill(7)
    replaced = detail[
        (detail["tier"] == "exact_cep") & (detail["geo_level"] == 1)
        & (detail["spread_m"] <= AMBIGUOUS_SPREAD_M) & (detail["error_m"] > CORRECTION_THRESHOLD_M)
    ]
    health = pd.read_csv(ROOT / "data" / "culturaeduca_infraestrutura_saude_rmsp.csv", dtype=str)
    health["cnes"] = health["CO_CNES"].str.zfill(7)
    names = {}
    for line in (Path.home() / "Downloads/cnefe_rmsp/to_download.txt").read_text().split():
        code, name = line[:-4].split("_", 1)
        names[code[:6]] = name.replace("_", " ").title()
    audit = replaced.merge(
        health[["cnes", "NO_FANTASIA", "NO_LOGRADOURO", "NU_ENDERECO", "NO_BAIRRO", "CO_MUNICIPIO_GESTOR"]], on="cnes")
    audit["registered_municipality"] = audit["CO_MUNICIPIO_GESTOR"].str[:6].map(names)

    where = municipality_of_points(list(zip(audit["cnes"], audit["ref_lat"], audit["ref_lon"])))
    audit["cnes_point_municipality"] = audit["cnes"].map(where).str[:6].map(names)
    audit["cnes_point_place"] = np.select(
        [audit["cnes_point_municipality"].isna(),
         audit["cnes_point_municipality"] == audit["registered_municipality"]],
        ["outside_region", "registered_municipality"], "other_municipality")

    osm = []
    for item in audit.itertuples():
        params = {
            "street": f"{item.NU_ENDERECO} {item.NO_LOGRADOURO}", "city": item.registered_municipality,
            "state": "São Paulo", "country": "Brazil", "format": "jsonv2", "limit": 1,
        }
        try:
            response = requests.get(NOMINATIM, params=params, headers=HEADERS, timeout=30)
            hits = response.json() if response.ok else []
        except requests.RequestException:
            hits = []
        if hits:
            lat, lon = float(hits[0]["lat"]), float(hits[0]["lon"])
            osm.append({
                "osm_match": hits[0].get("addresstype") or hits[0].get("type"),
                "osm_to_cnes_m": round(float(haversine_m(lat, lon, item.ref_lat, item.ref_lon))),
                "osm_to_cnefe_m": round(float(haversine_m(lat, lon, item.lat, item.lon))),
            })
        else:
            osm.append({"osm_match": None, "osm_to_cnes_m": np.nan, "osm_to_cnefe_m": np.nan})
        time.sleep(1.1)
    audit = pd.concat([audit.reset_index(drop=True), pd.DataFrame(osm)], axis=1)
    audit["verdict"] = [verdict(row) for row in audit.itertuples()]
    audit["shift_m"] = audit["error_m"].round()

    columns = ["cnes", "NO_FANTASIA", "NO_LOGRADOURO", "NU_ENDERECO", "NO_BAIRRO", "registered_municipality",
               "cnes_point_municipality", "cnes_point_place", "shift_m", "ref_lat", "ref_lon", "lat", "lon",
               "osm_match", "osm_to_cnes_m", "osm_to_cnefe_m", "verdict"]
    audit[columns].to_csv(HERE / "corrections_audit.csv", index=False)

    print(f"replaced coordinates audited: {len(audit)}")
    print("\nwhere the original CNES point falls:")
    print(audit["cnes_point_place"].value_counts().to_string())
    print("\nverdict of the third geocoder:")
    print(audit["verdict"].value_counts().to_string())
    print("\nby size of the shift:")
    bands = pd.cut(audit["shift_m"], [1000, 2000, 5000, 10000, 1e6], labels=["1-2 km", "2-5 km", "5-10 km", "over 10 km"])
    print(pd.crosstab(bands, audit["verdict"]).to_string())
    print("\nby where the CNES point falls:")
    print(pd.crosstab(audit["cnes_point_place"], audit["verdict"]).to_string())
    # Only a match on the building or facility itself is independent evidence at house
    # level; a street-level match returns a point along the street (or a street of the same name).
    house = audit[audit["osm_match"].isin(HOUSE_LEVEL)]
    print(f"\nhouse-level matches: {len(house)}; closer to CNEFE: "
          f"{(house['osm_to_cnefe_m'] < house['osm_to_cnes_m']).sum()}; "
          f"within 100 m of CNEFE: {(house['osm_to_cnefe_m'] <= 100).sum()}")
    print("\nby how precisely the third geocoder matched:")
    print(pd.crosstab(audit["osm_match"].fillna("none"), audit["verdict"]).to_string())


if __name__ == "__main__":
    main()
