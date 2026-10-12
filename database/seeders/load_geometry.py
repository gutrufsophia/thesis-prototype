"""Load the census tract outlines from the original IBGE mesh, lightly simplified.

The outlines first loaded had been simplified to about a fifth of their vertices one
polygon at a time, which left half of the tracts overlapping less than 82% with their
true shape. This script starts again from the original mesh and simplifies it as a
coverage: shared borders are simplified together, so neighbouring tracts keep meeting
exactly, with no gaps or overlaps. At the default tolerance about half of the vertices
remain and the median overlap with the true shape is 99.3%.

Updates the geometry of the existing rows in place, so policies, grants, indexes and
dependent views are kept.

    python database/seeders/load_geometry.py ~/Downloads/SP_setores_CD2022.json [--tolerance 10]
"""

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import shapely
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seed import ROOT, read_env  # noqa: E402

TABLE = "setores_censitarios_grande_sp"
STAGING = "_setores_full_resolution"
# Bounding box of the RMSP, to avoid reading the whole state
RMSP_BBOX = (-47.3, -24.2, -45.6, -23.1)
METRIC_CRS = "EPSG:31983"  # SIRGAS 2000 / UTM 23S, so the tolerance is in metres


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path)
    parser.add_argument("--tolerance", type=float, default=10,
                        help="coverage simplification tolerance in metres; 0 keeps every vertex")
    args = parser.parse_args()
    source = args.source.expanduser()
    engine = create_engine(read_env(ROOT / ".env")["DATABASE_URL"])

    mesh = gpd.read_file(source, bbox=RMSP_BBOX, columns=["CD_SETOR"])
    with engine.begin() as conn:
        wanted = {row[0] for row in conn.execute(text(f'select "CD_SETOR" from public.{TABLE}'))}
    mesh = mesh[mesh["CD_SETOR"].isin(wanted)].to_crs(METRIC_CRS).reset_index(drop=True)
    print(f"{len(mesh)} of {len(wanted)} tracts found in {source.name}")

    if args.tolerance > 0:
        original = mesh.geometry.buffer(0)
        simplified = gpd.GeoSeries(shapely.coverage_simplify(original.values, args.tolerance), crs=METRIC_CRS)
        shared = simplified.intersection(original).area
        overlap = shared / (simplified.area + original.area - shared)
        kept = shapely.get_num_coordinates(simplified.values).sum() / shapely.get_num_coordinates(original.values).sum()
        print(f"tolerance {args.tolerance} m: {kept:.0%} of vertices kept; overlap with the true shape: "
              f"median {overlap.median():.4f}, 1st percentile {overlap.quantile(0.01):.4f}")
        mesh = mesh.set_geometry(simplified)
    mesh = mesh.to_crs(4326)

    mesh.to_postgis(STAGING, engine, schema="public", if_exists="replace", index=False)
    with engine.begin() as conn:
        updated = conn.execute(text(
            f'update public.{TABLE} s set geometry = f.geometry '
            f'from public.{STAGING} f where s."CD_SETOR" = f."CD_SETOR"')).rowcount
        conn.execute(text(f"drop table public.{STAGING}"))
        conn.execute(text(f"analyze public.{TABLE}"))
        size, points, invalid = conn.execute(text(
            f"select pg_size_pretty(pg_total_relation_size('public.{TABLE}')), "
            f"sum(st_npoints(geometry)), count(*) filter (where not st_isvalid(geometry)) "
            f"from public.{TABLE}")).one()
    print(f"{updated} outlines replaced; table size {size}, {points} vertices, {invalid} invalid polygons")


if __name__ == "__main__":
    main()
