"""Population each public primary care unit is expected to serve, from a Huff-model allocation of
residents within variable floating catchments.

Demand points are CNEFE 2022 residential addresses. Each carries its tract's population divided by
the tract's residential addresses (a dasymetric weight), so a large rural tract puts its people
where its homes are rather than at one centroid.

A resident at distance d1 from the nearest public primary care unit (SUS-linked UBS or health post)
considers the units within

    r = min(max(R0, K * d1), R_MAX)

so the catchment widens where units are sparse (variable catchment: Luo & Whippo 2012; McGrail &
Humphreys 2009). The probability of using unit j follows the Huff model with a Gaussian distance
decay that reaches zero at r (Luo 2014; Gaussian form as in Dai 2010):

    P_ij = S_j W(d_ij) / sum_k S_k W(d_ik)
    W(d) = (exp(-d^2 / 2r^2) - exp(-1/2)) / (1 - exp(-1/2))   for d < r, else 0

The unit's expected population is L_j = sum_i w_i P_ij. Unlike the 2SFCA and 3SFCA denominators,
it applies the decay once, so every allocated resident is counted exactly once across units and
L_j reads as a number of people. Accessibility at an address is A_i = sum_j P_ij S_j / L_j.

Need is measured on the same people: D_j is the share of L_j living in deprived tracts (the union
rule of database/reference/build_surroundings.sh).

CNEFE covers the RMSP only, so a unit whose residents' catchments cross the region's outer boundary
misses people from outside and may take people who would use a unit outside. Such units are marked
near_edge: distance to the boundary below the mean catchment radius of the people allocated to them.

Writes data/catchment_units.csv, data/catchment_tracts.csv and data/catchment_summary.json.

    python3 database/reference/compute_catchment.py --cnefe-dir ~/Downloads/cnefe_rmsp
"""

import argparse
import json
import math
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from scipy.spatial import cKDTree
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "database" / "seeders"))
from seed import PRIMARY_CARE_TYPES, read_env  # noqa: E402

RESIDENTIAL = {"1", "2"}  # COD_ESPECIE: private and collective dwellings
# Same flat projection as database/geocoding/compute_access.py; distortion under 0.5% in the RMSP
LAT0 = -23.55
M_PER_DEG_LAT = 110_574
M_PER_DEG_LON = 111_320 * np.cos(np.radians(LAT0))

MAIN = {"r0": 2000, "k": 2.0, "r_max": 20000, "decay": "gaussian", "supply": "units", "allocation": "huff"}
# One parameter changed at a time against MAIN
VARIANTS = {
    "r0_1km": {"r0": 1000},
    "r0_3km": {"r0": 3000},
    "k_1.5": {"k": 1.5},
    "k_3": {"k": 3.0},
    "rmax_10km": {"r_max": 10000},
    "uniform_decay": {"decay": "uniform"},
    "physician_supply": {"supply": "physicians"},
    "double_decay_3sfca": {"allocation": "double_decay"},
}
NEIGHBOURS = 64
CHUNK = 100_000
NEED_HIGH = 0.75  # rules.json need_high
PADEIROS = 9840559
E_HALF = math.exp(-0.5)


def to_metres(lat, lon):
    return np.column_stack([np.asarray(lon) * M_PER_DEG_LON, np.asarray(lat) * M_PER_DEG_LAT])


def load_database(url):
    conn = psycopg2.connect(url, options="-c search_path=public,extensions -c statement_timeout=900000")
    with conn.cursor() as cur:
        cur.execute(
            'select "CO_CNES", st_y(coord::geometry), st_x(coord::geometry), coalesce(total_medicos, 0) '
            "from infraestrutura_saude where coord is not null and rede_sus and tipo_equipamento in %s "
            'order by "CO_CNES"',
            (PRIMARY_CARE_TYPES,),
        )
        units = pd.DataFrame(cur.fetchall(), columns=["cnes", "lat", "lon", "physicians"])
        cur.execute(
            "select c.cd_setor, c.populacao_total, c.media_moradores_domicilio, c.esgoto_precario, "
            "c.domicilios_esgoto_informado, c.total_lixo_coletado, c.domicilios_lixo_informado, "
            "c.renda_media_responsavel, st_y(p.pt), st_x(p.pt) "
            "from dados_censo_grande_sp c "
            'left join setores_censitarios_grande_sp s on s."CD_SETOR"::bigint = c.cd_setor '
            "left join lateral (select st_pointonsurface(st_makevalid(s.geometry)) as pt) p on true"
        )
        tracts = pd.DataFrame(cur.fetchall(), columns=[
            "cd_setor", "population", "residents_per_household", "precarious", "sewage_den",
            "garbage", "garbage_den", "income", "lat", "lon"])
        # Outer boundary of the union of tracts; the simplified mesh needs a fixed-precision union
        cur.execute(
            "with region as (select st_union(st_makevalid(st_snaptogrid(geometry, 0.0001)), 0.0001) as g "
            "                from setores_censitarios_grande_sp), "
            "parts as (select (st_dump(g)).geom as p from region), "
            "outer_ring as (select st_exteriorring(p) as ring from parts order by st_area(p) desc limit 1) "
            'select i."CO_CNES", st_distance(i.coord, o.ring::geography) from infraestrutura_saude i, outer_ring o '
            "where i.coord is not null and i.rede_sus and i.tipo_equipamento in %s",
            (PRIMARY_CARE_TYPES,),
        )
        edge = dict(cur.fetchall())
    conn.close()
    units["edge_m"] = units["cnes"].map(edge).astype(float)
    for column in tracts.columns.drop("cd_setor"):
        tracts[column] = pd.to_numeric(tracts[column], errors="coerce")
    units["physicians"] = pd.to_numeric(units["physicians"])
    return units, tracts


def deprivation(tracts):
    """Union rule of build_surroundings.sh, on the same rounded tract values; missing values never count."""
    low_income = round(0.6 * tracts["income"].dropna().median())
    precarious = (100 * tracts["precarious"] / tracts["sewage_den"].where(tracts["sewage_den"] > 0)).round(1)
    garbage = (100 * tracts["garbage"] / tracts["garbage_den"].where(tracts["garbage_den"] > 0)).round(1)
    deprived = (precarious >= 20) | (tracts["residents_per_household"] >= 3.1) | (garbage <= 90) | \
        (tracts["income"].round() < low_income)
    return deprived.fillna(False).to_numpy(), low_income


def load_addresses(cnefe_dir):
    """Residential addresses grouped by tract and coordinate: apartments in one building share a point."""
    parts = []
    for zip_path in sorted(cnefe_dir.glob("*.zip")):
        chunks = []
        with zipfile.ZipFile(zip_path) as archive:
            name = next(n for n in archive.namelist() if n.lower().endswith(".csv"))
            with archive.open(name) as handle:
                # read in blocks: the capital's file alone has millions of rows
                for df in pd.read_csv(handle, sep=";", dtype=str, encoding="utf-8", chunksize=500_000,
                                      usecols=["COD_SETOR", "COD_ESPECIE", "LATITUDE", "LONGITUDE"]):
                    df = df[df["COD_ESPECIE"].isin(RESIDENTIAL)]
                    chunks.append(pd.DataFrame({
                        # CNEFE tract codes carry a one-letter suffix after the 15 digits
                        "cd_setor": pd.to_numeric(df["COD_SETOR"].str[:15], errors="coerce"),
                        "lat": pd.to_numeric(df["LATITUDE"], errors="coerce"),
                        "lon": pd.to_numeric(df["LONGITUDE"], errors="coerce"),
                    }).dropna())
        frame = pd.concat(chunks, ignore_index=True)
        grouped = frame.groupby(["cd_setor", "lat", "lon"]).size().rename("addresses").reset_index()
        parts.append(grouped)
        print(f"{zip_path.name}: {len(frame)} residential addresses at {len(grouped)} points", flush=True)
    points = pd.concat(parts, ignore_index=True)
    points["cd_setor"] = points["cd_setor"].astype(np.int64)
    return points


def demand_points(addresses, tracts, deprived):
    """Points carrying people: addresses weighted by tract population, plus one point per populated
    tract without any CNEFE residential address."""
    per_tract = addresses.groupby("cd_setor")["addresses"].sum()
    info = tracts.set_index("cd_setor")
    info["deprived"] = deprived
    pts = addresses.join(info[["population", "deprived"]], on="cd_setor")
    pts = pts[pts["population"] > 0].copy()
    pts["weight"] = pts["population"] * pts["addresses"] / pts["cd_setor"].map(per_tract)
    orphan = info[(info["population"] > 0) & ~info.index.isin(per_tract.index) & info["lat"].notna()]
    extra = pd.DataFrame({"cd_setor": orphan.index, "lat": orphan["lat"], "lon": orphan["lon"],
                          "addresses": 0, "population": orphan["population"],
                          "deprived": orphan["deprived"], "weight": orphan["population"]})
    pts = pd.concat([pts, extra], ignore_index=True)
    return pts, {"tracts_without_addresses": int(len(orphan)), "population_at_tract_points": float(orphan["population"].sum())}


def decay(d, r, kind):
    inside = d < r
    if kind == "uniform":
        return inside.astype(float)
    w = (np.exp(-0.5 * (d / r) ** 2) - E_HALF) / (1 - E_HALF)
    return np.where(inside, w, 0.0)


def allocate(xy, weight, deprived, tree, supply, params, with_access=False, n_units=None):
    """Returns expected population, deprived population and (optionally) per-point accessibility."""
    served = np.zeros(n_units)
    served_deprived = np.zeros(n_units)
    served_radius = np.zeros(n_units)
    catchment = np.zeros(len(xy))
    allocated = np.zeros(len(xy), dtype=bool)
    truncated = 0
    passes = [None] if not with_access else [None, "access"]
    access = np.zeros(len(xy)) if with_access else None
    for stage in passes:
        for start in range(0, len(xy), CHUNK):
            stop = min(start + CHUNK, len(xy))
            dist, idx = tree.query(xy[start:stop], k=NEIGHBOURS)
            r = np.clip(params["k"] * dist[:, 0], params["r0"], params["r_max"])
            w = decay(dist, r[:, None], params["decay"])
            attraction = supply[idx] * w
            total = attraction.sum(axis=1)
            ok = total > 0
            prob = np.divide(attraction, total[:, None], out=np.zeros_like(attraction), where=ok[:, None])
            if stage is None:
                truncated += int((dist[:, -1] < r).sum())
                share = prob * w if params["allocation"] == "double_decay" else prob
                served += np.bincount(idx.ravel(), (share * weight[start:stop, None]).ravel(), n_units)
                served_deprived += np.bincount(
                    idx.ravel(), (share * (weight[start:stop] * deprived[start:stop])[:, None]).ravel(), n_units)
                served_radius += np.bincount(idx.ravel(), (share * (weight[start:stop] * r)[:, None]).ravel(), n_units)
                catchment[start:stop] = r
                allocated[start:stop] = ok
            else:
                ratio = np.divide(supply, served, out=np.zeros(n_units), where=served > 0)
                access[start:stop] = (prob * ratio[idx]).sum(axis=1)
    mean_radius = np.divide(served_radius, served, out=np.zeros(n_units), where=served > 0)
    return served, served_deprived, catchment, allocated, access, truncated, mean_radius


def percentile(values):
    """Share below plus half the ties, as backend-core/src/payload.cpp computes it."""
    order = np.sort(values)
    below = np.searchsorted(order, values, side="left")
    equal = np.searchsorted(order, values, side="right") - below
    return (below + equal / 2) / len(values)


def classify(need, load):
    """need_supply variant as in backend-core/src/facts.cpp: pressure, served or none."""
    n, l = percentile(need), percentile(load)
    return np.where(n >= NEED_HIGH, np.where(l >= NEED_HIGH, "pressure", np.where(l <= 1 - NEED_HIGH, "served", "none")), "none")


def describe(values, weights=None):
    v = np.asarray(values, dtype=float)
    if weights is None:
        q = np.percentile(v, [10, 50, 90])
    else:
        order = np.argsort(v)
        cum = np.cumsum(np.asarray(weights, dtype=float)[order])
        q = [v[order][np.searchsorted(cum, p * cum[-1])] for p in (0.1, 0.5, 0.9)]
    return {"p10": round(float(q[0]), 1), "median": round(float(q[1]), 1), "p90": round(float(q[2]), 1)}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cnefe-dir", required=True, type=Path)
    args = parser.parse_args()

    units, tracts = load_database(read_env(ROOT / ".env")["DATABASE_URL"])
    deprived_tract, low_income = deprivation(tracts)
    print(f"{len(units)} public primary care units; low-income line R$ {low_income}", flush=True)
    addresses = load_addresses(args.cnefe_dir)
    pts, orphan_stats = demand_points(addresses, tracts, deprived_tract)
    xy = to_metres(pts["lat"].to_numpy(), pts["lon"].to_numpy())
    weight = pts["weight"].to_numpy()
    dep = pts["deprived"].to_numpy(dtype=float)
    tree = cKDTree(to_metres(units["lat"], units["lon"]))
    supplies = {"units": np.ones(len(units)), "physicians": np.maximum(units["physicians"].to_numpy(dtype=float), 1)}

    def run(params, with_access=False):
        return allocate(xy, weight, dep, tree, supplies[params["supply"]], params, with_access, len(units))

    served, served_dep, catchment, allocated, access, truncated, mean_radius = run(MAIN, with_access=True)
    share_dep = np.divide(served_dep, served, out=np.zeros_like(served), where=served > 0) * 100
    nearest_distance, _ = tree.query(xy, k=1)

    near_edge = units["edge_m"].to_numpy() < mean_radius
    units_out = pd.DataFrame({
        "cnes": units["cnes"], "served_population": served.round(0), "served_deprived_pct": share_dep.round(1),
        "mean_catchment_m": mean_radius.round(0), "edge_m": units["edge_m"].round(0), "near_edge": near_edge})
    units_out.to_csv(ROOT / "data" / "catchment_units.csv", index=False)

    tract_frame = pd.DataFrame({"cd_setor": pts["cd_setor"], "w": weight, "wa": weight * access,
                                "dep": pts["deprived"].astype(bool)})
    by_tract = tract_frame.groupby("cd_setor").agg(population=("w", "sum"), wa=("wa", "sum"), deprived=("dep", "first"))
    by_tract["access_per_10k"] = (by_tract["wa"] / by_tract["population"] * 10_000).round(3)
    by_tract = by_tract.join(tracts.set_index("cd_setor")["income"])
    by_tract[["population", "deprived", "access_per_10k"]].assign(population=lambda f: f["population"].round(0)) \
        .to_csv(ROOT / "data" / "catchment_tracts.csv")

    # Comparison with the fixed 1 km measure the narrative used before
    ref = pd.read_csv(ROOT / "data" / "surroundings_1000.csv")
    ref = ref[(ref["rede_sus"] == "t") & ref["tipo_equipamento"].isin(PRIMARY_CARE_TYPES) & (ref["population"] > 0)]
    ref = ref.assign(load_1km=ref["population"] / (ref["public_primary_nearby"] + 1),
                     # an empty sum is NULL in SQL: no deprived tract, as payload.cpp reads it
                     need_1km=100 * ref["deprived_population"].fillna(0) / ref["population"])
    both = ref.merge(units_out, on="cnes")
    old_class = classify(both["need_1km"].to_numpy(), both["load_1km"].to_numpy())
    new_class = classify(both["served_deprived_pct"].to_numpy(), both["served_population"].to_numpy())
    types = pd.read_csv(ROOT / "data" / "surroundings_types.csv").set_index("cnes")["territory_type"]
    both["territory_type"] = both["cnes"].map(types)

    sensitivity = {}
    main_class = classify(share_dep, served)
    for name, change in VARIANTS.items():
        params = {**MAIN, **change}
        s, sd, _, _, _, trunc, _ = run(params)
        d = np.divide(sd, s, out=np.zeros_like(s), where=s > 0) * 100
        cls = classify(d, s)
        padeiros = int(np.flatnonzero(units["cnes"].to_numpy() == PADEIROS)[0])
        sensitivity[name] = {
            "spearman_served": round(float(spearmanr(s, served).statistic), 3),
            "spearman_deprived": round(float(spearmanr(d, share_dep).statistic), 3),
            "same_class_share": round(float((cls == main_class).mean()), 3),
            "pressure": int((cls == "pressure").sum()), "served": int((cls == "served").sum()),
            "padeiros_served": round(float(s[padeiros])), "padeiros_deprived_pct": round(float(d[padeiros]), 1),
            "padeiros_class": str(cls[padeiros]), "truncated_points": trunc,
        }
        print(name, sensitivity[name], flush=True)

    padeiros = int(np.flatnonzero(units["cnes"].to_numpy() == PADEIROS)[0])
    valid = by_tract.dropna(subset=["income"])
    summary = {
        "parameters": MAIN,
        "neighbours_queried": NEIGHBOURS,
        "low_income_line": low_income,
        "units": len(units),
        "residential_addresses": int(addresses["addresses"].sum()),
        "demand_points": len(pts),
        **orphan_stats,
        "population": round(float(weight.sum())),
        "allocated_population": round(float(weight[allocated].sum())),
        "unallocated_population": round(float(weight[~allocated].sum())),
        "allocated_check": round(float(served.sum())),
        "truncated_points": truncated,
        "catchment_radius_m_population_weighted": describe(catchment[allocated], weight[allocated]),
        "nearest_unit_m_population_weighted": describe(nearest_distance, weight),
        "served_population": describe(served),
        "served_deprived_pct": describe(share_dep),
        "classes": {"pressure": int((main_class == "pressure").sum()), "served": int((main_class == "served").sum())},
        "near_edge": {"units": int(near_edge.sum()), "of_them_pressure": int((near_edge & (main_class == "pressure")).sum()),
                      "of_them_served": int((near_edge & (main_class == "served")).sum())},
        "mean_catchment_m": describe(mean_radius),
        "padeiros": {"served_population": round(float(served[padeiros])), "served_deprived_pct": round(float(share_dep[padeiros]), 1),
                     "class": str(main_class[padeiros]), "mean_catchment_m": round(float(mean_radius[padeiros])),
                     "edge_m": round(float(units["edge_m"].iloc[padeiros])), "near_edge": bool(near_edge[padeiros])},
        "against_1km": {
            "units_compared": len(both),
            "spearman_load": round(float(spearmanr(both["load_1km"], both["served_population"]).statistic), 3),
            "spearman_need": round(float(spearmanr(both["need_1km"], both["served_deprived_pct"]).statistic), 3),
            "old": {"pressure": int((old_class == "pressure").sum()), "served": int((old_class == "served").sum())},
            "new": {"pressure": int((new_class == "pressure").sum()), "served": int((new_class == "served").sum())},
            "old_served_still_served": int(((old_class == "served") & (new_class == "served")).sum()),
            "old_served_now_pressure": int(((old_class == "served") & (new_class == "pressure")).sum()),
            "old_served_rural_edge": int(((old_class == "served") & (both["territory_type"] == 1)).sum()),
            "new_served_rural_edge": int(((new_class == "served") & (both["territory_type"] == 1)).sum()),
        },
        "inverse_care": {
            "tracts": len(valid),
            "spearman_income_access": round(float(spearmanr(valid["income"], valid["access_per_10k"]).statistic), 3),
            "access_per_10k_deprived": round(float(np.average(by_tract.loc[by_tract["deprived"], "access_per_10k"],
                                                              weights=by_tract.loc[by_tract["deprived"], "population"])), 3),
            "access_per_10k_not_deprived": round(float(np.average(by_tract.loc[~by_tract["deprived"], "access_per_10k"],
                                                                  weights=by_tract.loc[~by_tract["deprived"], "population"])), 3),
        },
        "sensitivity": sensitivity,
    }
    (ROOT / "data" / "catchment_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "sensitivity"}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
