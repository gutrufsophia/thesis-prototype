"""Distance from homes to the nearest public primary care unit, per census tract.

For every residential address in CNEFE 2022 (door-level coordinates), find the
straight-line distance to the nearest public-network primary care unit (Centro de
Saúde/UBS or Posto de Saúde with rede_sus) and summarise it per census tract: the
share of addresses within 500 m, 1 km and 2 km, and the median distance.

Measuring from addresses instead of one point per tract matters where tracts are
large: a rural tract several kilometres wide can contain a health centre and still
have most homes far from it.

Reads facility positions from the database, so run it again after they change.
Writes database/geocoding/setor_acesso.csv, which the seeder loads.

    python database/geocoding/compute_access.py --cnefe-dir ~/Downloads/cnefe_rmsp
"""

import argparse
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "database" / "seeders"))
from seed import PRIMARY_CARE_TYPES, read_env  # noqa: E402

RESIDENTIAL = {"1", "2"}  # COD_ESPECIE: private and collective dwellings
# Flat projection centred on the region; distortion is under 0.5% across the RMSP
LAT0 = -23.55
M_PER_DEG_LAT = 110_574
M_PER_DEG_LON = 111_320 * np.cos(np.radians(LAT0))


def to_metres(lat, lon):
    return np.column_stack([np.asarray(lon) * M_PER_DEG_LON, np.asarray(lat) * M_PER_DEG_LAT])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cnefe-dir", required=True, type=Path)
    args = parser.parse_args()

    conn = psycopg2.connect(read_env(ROOT / ".env")["DATABASE_URL"], options="-c search_path=public,extensions")
    with conn.cursor() as cur:
        cur.execute(
            "select st_y(coord::geometry), st_x(coord::geometry) from infraestrutura_saude "
            "where coord is not null and rede_sus and tipo_equipamento in %s",
            (PRIMARY_CARE_TYPES,),
        )
        units = np.array(cur.fetchall())
    conn.close()
    tree = cKDTree(to_metres(units[:, 0], units[:, 1]))
    print(f"{len(units)} public primary care units")

    parts = []
    for zip_path in sorted(args.cnefe_dir.glob("*.zip")):
        with zipfile.ZipFile(zip_path) as archive:
            name = next(n for n in archive.namelist() if n.lower().endswith(".csv"))
            with archive.open(name) as handle:
                df = pd.read_csv(handle, sep=";", dtype=str, encoding="utf-8",
                                 usecols=["COD_SETOR", "COD_ESPECIE", "LATITUDE", "LONGITUDE"])
        df = df[df["COD_ESPECIE"].isin(RESIDENTIAL)]
        lat = pd.to_numeric(df["LATITUDE"], errors="coerce")
        lon = pd.to_numeric(df["LONGITUDE"], errors="coerce")
        valid = lat.notna() & lon.notna()
        distance, _ = tree.query(to_metres(lat[valid], lon[valid]))
        # CNEFE tract codes carry a one-letter suffix after the 15 digits
        parts.append(pd.DataFrame({"cd_setor": df.loc[valid, "COD_SETOR"].str[:15].to_numpy(), "dist": distance}))
        print(f"{zip_path.name}: {int(valid.sum())} residential addresses", flush=True)

    homes = pd.concat(parts)
    grouped = homes.groupby("cd_setor")["dist"]
    result = pd.DataFrame({
        "enderecos": grouped.size(),
        "pct_ate_500": (grouped.apply(lambda d: (d <= 500).mean()) * 100).round(1),
        "pct_ate_1000": (grouped.apply(lambda d: (d <= 1000).mean()) * 100).round(1),
        "pct_ate_2000": (grouped.apply(lambda d: (d <= 2000).mean()) * 100).round(1),
        "dist_mediana_m": grouped.median().round().astype(int),
    }).reset_index()
    result.to_csv(HERE / "setor_acesso.csv", index=False)

    print(f"\n{len(homes)} residential addresses in {len(result)} census tracts")
    print("share of addresses within 500 m / 1 km / 2 km of a public primary care unit:",
          [round(float((homes['dist'] <= limit).mean()) * 100, 1) for limit in (500, 1000, 2000)])


if __name__ == "__main__":
    main()
