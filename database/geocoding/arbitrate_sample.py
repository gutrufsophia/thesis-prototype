"""Arbitrate CNES against CNEFE coordinates with a third, independent geocoder.

For facilities whose address matched CNEFE exactly (street, number and CEP, with a
door-surveyed coordinate), CNES and CNEFE sometimes place the facility far apart.
This script geocodes a fixed random sample of those addresses with OpenStreetMap's
Nominatim and reports which of the two official sources the third one sides with.

Run after geocode_cnefe.py. Respects Nominatim's one-request-per-second policy.

    python database/geocoding/arbitrate_sample.py
"""

import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
NOMINATIM = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "culturaeduca-health-thesis-prototype/0.1 (academic geocoding validation)"}
SEED = 20261012
# (label, lower bound, upper bound in metres of CNES-CNEFE disagreement, sample size)
STRATA = [("agree", 0, 50, 20), ("moderate", 250, 1000, 30), ("large", 1000, 50000, 30)]


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371000 * 2 * np.arcsin(np.sqrt(a))


def main():
    detail = pd.read_csv(HERE / "validation_detail.csv", dtype={"cnes": str})
    detail["cnes"] = detail["cnes"].str.zfill(7)
    detail = detail[(detail["tier"] == "exact_cep") & (detail["geo_level"] == 1)]

    health = pd.read_csv(ROOT / "data" / "culturaeduca_infraestrutura_saude_rmsp.csv", dtype=str)
    health["cnes"] = health["CO_CNES"].str.zfill(7)
    # municipality names come from the CNEFE file names
    names = {}
    for line in (Path.home() / "Downloads/cnefe_rmsp/to_download.txt").read_text().split():
        code, name = line[:-4].split("_", 1)
        names[code[:6]] = name.replace("_", " ").title()

    sample = pd.concat([
        detail[(detail["error_m"] >= low) & (detail["error_m"] < high)]
        .sample(size, random_state=SEED).assign(stratum=label)
        for label, low, high, size in STRATA
    ]).merge(health[["cnes", "NO_LOGRADOURO", "NU_ENDERECO", "CO_MUNICIPIO_GESTOR"]], on="cnes")

    rows = []
    for item in sample.itertuples():
        params = {
            "street": f"{item.NU_ENDERECO} {item.NO_LOGRADOURO}",
            "city": names[item.CO_MUNICIPIO_GESTOR[:6]],
            "state": "São Paulo", "country": "Brazil", "format": "jsonv2", "limit": 1,
        }
        response = requests.get(NOMINATIM, params=params, headers=HEADERS, timeout=30)
        hits = response.json() if response.ok else []
        row = {"cnes": item.cnes, "stratum": item.stratum, "cnes_cnefe_m": round(item.error_m)}
        if hits:
            lat, lon = float(hits[0]["lat"]), float(hits[0]["lon"])
            row.update(
                osm_match=hits[0].get("addresstype") or hits[0].get("type"),
                osm_to_cnes_m=round(float(haversine_m(lat, lon, item.ref_lat, item.ref_lon))),
                osm_to_cnefe_m=round(float(haversine_m(lat, lon, item.lat, item.lon))),
            )
        rows.append(row)
        time.sleep(1.1)

    result = pd.DataFrame(rows)
    result.to_csv(HERE / "arbitration_sample.csv", index=False)

    found = result.dropna(subset=["osm_to_cnes_m"]).copy()
    found["closer_to"] = np.where(found["osm_to_cnefe_m"] < found["osm_to_cnes_m"], "cnefe", "cnes")
    print(f"sampled {len(result)}, geocoded by Nominatim {len(found)}")
    summary = found.groupby("stratum").agg(
        n=("cnes", "size"),
        sides_with_cnefe=("closer_to", lambda s: (s == "cnefe").sum()),
        sides_with_cnes=("closer_to", lambda s: (s == "cnes").sum()),
        median_osm_to_cnefe_m=("osm_to_cnefe_m", "median"),
        median_osm_to_cnes_m=("osm_to_cnes_m", "median"),
    )
    print(summary.reindex([label for label, *_ in STRATA]).to_string())
    print("\nNominatim match type:", found["osm_match"].value_counts().to_dict())


if __name__ == "__main__":
    main()
