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

Supply is counted in primary care teams, the unit of the National Primary Care Policy (PNAB 2017,
section 3.3: 2,000 to 3,500 people per team). A Family Health team (eSF, CNES type 70) counts 1; a
Primary Care team (eAP, type 76) counts 0.5 or 0.75, the shares of an eSF that federal funding gives
its 20-hour and 30-hour modalities, inferred from the ambulatory hours its physician and nurse have
at the unit. Units with no active eSF or eAP still take patients and enter with one team-equivalent;
their people-per-team figure is left empty.

Need is measured on the same people: D_j is the share of L_j living in deprived tracts (the union
rule of database/reference/build_surroundings.sh). Reach is measured on them too: the mean
straight-line distance from their homes to the unit, and the share living beyond FAR_M.

CNEFE covers the RMSP only, so a unit whose residents' catchments cross the region's outer boundary
misses people from outside and may take people who would use a unit outside. Such units are marked
near_edge: distance to the boundary below the mean catchment radius of the people allocated to them.

Writes data/catchment_units.csv, data/catchment_tracts.csv and data/catchment_summary.json.

    python3 database/reference/compute_catchment.py --cnefe-dir ~/Downloads/cnefe_rmsp \
        --cnes-dir ~/Downloads/BASE_DE_DADOS_CNES_202608
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

MAIN = {"r0": 2000, "k": 2.0, "r_max": 20000, "decay": "gaussian", "supply": "teams", "allocation": "huff"}
# One parameter changed at a time against MAIN
VARIANTS = {
    "r0_1km": {"r0": 1000},
    "r0_3km": {"r0": 3000},
    "k_1.5": {"k": 1.5},
    "k_3": {"k": 3.0},
    "rmax_10km": {"r_max": 10000},
    "uniform_decay": {"decay": "uniform"},
    "unit_supply": {"supply": "units"},
    "physician_supply": {"supply": "physicians"},
    "eap_all_half": {"supply": "teams_eap_half"},
    "eap_all_three_quarters": {"supply": "teams_eap_075"},
    "no_team_units_half": {"supply": "teams_no_team_half"},
    "double_decay_3sfca": {"allocation": "double_decay"},
}
NEIGHBOURS = 64
PNAB_LOW, PNAB_HIGH = 2000, 3500  # people per team, PNAB 2017 section 3.3 item i
ESF, EAP = "70", "76"
EAP_WEIGHT = {20: 0.5, 30: 0.75}  # modality I and II, as shares of an eSF
FAR_M = 2000  # about 30 minutes on foot at 4 km/h before detours
PHYSICIAN_CBO = ("2251", "2252", "2253", "2231")
NURSE_CBO = ("2235",)
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


def load_teams(cnes_dir, units):
    """Active eSF and eAP teams per unit, with eAP modality inferred from ambulatory hours."""
    # CO_UNIDADE is the establishment's municipality code followed by the 7-digit CNES
    wanted = {f"{c:07d}" for c in units["cnes"]}
    teams = pd.read_csv(cnes_dir / "tbEquipe202608.csv", sep=";", dtype=str, encoding="latin1",
                        usecols=["CO_MUNICIPIO", "CO_AREA", "SEQ_EQUIPE", "CO_UNIDADE", "TP_EQUIPE", "DT_DESATIVACAO"])
    teams = teams[teams["CO_UNIDADE"].str[6:].isin(wanted) & teams["TP_EQUIPE"].isin([ESF, EAP]) & teams["DT_DESATIVACAO"].isna()]
    unit_codes = set(teams["CO_UNIDADE"])
    key = ["CO_MUNICIPIO", "CO_AREA", "SEQ_EQUIPE"]

    members = []
    for chunk in pd.read_csv(cnes_dir / "rlEstabEquipeProf202608.csv", sep=";", dtype=str, encoding="latin1",
                             chunksize=1_000_000, usecols=key + ["CO_PROFISSIONAL_SUS", "CO_UNIDADE", "CO_CBO", "DT_DESLIGAMENTO"]):
        members.append(chunk[chunk["CO_UNIDADE"].isin(unit_codes) & chunk["DT_DESLIGAMENTO"].isna()])
    members = pd.concat(members).merge(teams.loc[teams["TP_EQUIPE"] == EAP, key], on=key)
    hours = []
    for chunk in pd.read_csv(cnes_dir / "tbCargaHorariaSus202608.csv", sep=";", dtype=str, encoding="latin1",
                             chunksize=2_000_000, usecols=["CO_UNIDADE", "CO_PROFISSIONAL_SUS", "CO_CBO", "QT_CARGA_HORARIA_AMBULATORIAL"]):
        hours.append(chunk[chunk["CO_UNIDADE"].isin(unit_codes)])
    hours = pd.concat(hours)
    hours["h"] = pd.to_numeric(hours["QT_CARGA_HORARIA_AMBULATORIAL"], errors="coerce")
    members = members.merge(hours[["CO_UNIDADE", "CO_PROFISSIONAL_SUS", "CO_CBO", "h"]],
                            on=["CO_UNIDADE", "CO_PROFISSIONAL_SUS", "CO_CBO"], how="left")
    # A team's modality is set by the shorter of its physician's and nurse's hours
    role = np.where(members["CO_CBO"].str.startswith(PHYSICIAN_CBO), "physician",
                    np.where(members["CO_CBO"].str.startswith(NURSE_CBO), "nurse", ""))
    by_role = members.assign(role=role)[role != ""].groupby(key + ["role"])["h"].max().unstack()
    team_hours = by_role.reindex(columns=["physician", "nurse"]).min(axis=1)

    eap = teams[teams["TP_EQUIPE"] == EAP].join(team_hours.rename("hours"), on=key)
    eap["modality_hours"] = np.where(eap["hours"] >= 30, 30, 20)  # unknown hours count as modality I
    teams["cnes"] = teams["CO_UNIDADE"].str[6:].astype(np.int64)
    eap["cnes"] = eap["CO_UNIDADE"].str[6:].astype(np.int64)
    esf = teams[teams["TP_EQUIPE"] == ESF].groupby("cnes").size()
    out = pd.DataFrame({"cnes": units["cnes"]})
    out["teams_esf"] = out["cnes"].map(esf).fillna(0).astype(int)
    for hours_, weight in EAP_WEIGHT.items():
        out[f"teams_eap_{hours_}h"] = out["cnes"].map(eap[eap["modality_hours"] == hours_].groupby("cnes").size()).fillna(0).astype(int)
    out["team_equivalents"] = out["teams_esf"] + sum(out[f"teams_eap_{h}h"] * w for h, w in EAP_WEIGHT.items())
    stats = {"teams_esf": int(out["teams_esf"].sum()),
             **{f"teams_eap_{h}h": int(out[f"teams_eap_{h}h"].sum()) for h in EAP_WEIGHT},
             "eap_without_hours": int(eap["hours"].isna().sum()),
             "units_without_team": int((out["team_equivalents"] == 0).sum())}
    return out, stats


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
    served_distance = np.zeros(n_units)
    served_far = np.zeros(n_units)
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
                weighted = share * weight[start:stop, None]
                served_distance += np.bincount(idx.ravel(), (weighted * dist).ravel(), n_units)
                served_far += np.bincount(idx.ravel(), (weighted * (dist > FAR_M)).ravel(), n_units)
                catchment[start:stop] = r
                allocated[start:stop] = ok
            else:
                ratio = np.divide(supply, served, out=np.zeros(n_units), where=served > 0)
                access[start:stop] = (prob * ratio[idx]).sum(axis=1)
    per = lambda total: np.divide(total, served, out=np.zeros(n_units), where=served > 0)  # noqa: E731
    reach = {"mean_radius": per(served_radius), "mean_distance": per(served_distance), "far_share": per(served_far)}
    return served, served_deprived, catchment, allocated, access, truncated, reach


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


def classify_teams(need, served, team_equivalents):
    """need_supply variant as the narrative tells it: with teams, people per team against the PNAB
    range; without, the unit's rank in people per unit."""
    n = percentile(need)
    per_team = np.divide(served, team_equivalents, out=np.full_like(served, np.nan), where=team_equivalents > 0)
    unit_class = classify(need, served)
    team_class = np.where(per_team > PNAB_HIGH, "above", np.where(per_team < PNAB_LOW, "below", "within"))
    return np.where(n < NEED_HIGH, "none", np.where(team_equivalents > 0, team_class, unit_class))


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
    parser.add_argument("--cnes-dir", required=True, type=Path)
    args = parser.parse_args()

    units, tracts = load_database(read_env(ROOT / ".env")["DATABASE_URL"])
    teams, team_stats = load_teams(args.cnes_dir, units)
    print(f"teams: {team_stats}", flush=True)
    deprived_tract, low_income = deprivation(tracts)
    print(f"{len(units)} public primary care units; low-income line R$ {low_income}", flush=True)
    addresses = load_addresses(args.cnefe_dir)
    pts, orphan_stats = demand_points(addresses, tracts, deprived_tract)
    xy = to_metres(pts["lat"].to_numpy(), pts["lon"].to_numpy())
    weight = pts["weight"].to_numpy()
    dep = pts["deprived"].to_numpy(dtype=float)
    tree = cKDTree(to_metres(units["lat"], units["lon"]))
    eq = teams["team_equivalents"].to_numpy(dtype=float)
    eap = {h: teams[f"teams_eap_{h}h"].to_numpy(dtype=float) for h in EAP_WEIGHT}
    esf = teams["teams_esf"].to_numpy(dtype=float)
    with_floor = lambda e, floor=1.0: np.where(e > 0, e, floor)  # noqa: E731
    supplies = {
        "units": np.ones(len(units)),
        "physicians": np.maximum(units["physicians"].to_numpy(dtype=float), 1),
        "teams": with_floor(eq),
        "teams_eap_half": with_floor(esf + 0.5 * (eap[20] + eap[30])),
        "teams_eap_075": with_floor(esf + 0.75 * (eap[20] + eap[30])),
        "teams_no_team_half": with_floor(eq, 0.5),
    }

    def run(params, with_access=False):
        return allocate(xy, weight, dep, tree, supplies[params["supply"]], params, with_access, len(units))

    served, served_dep, catchment, allocated, access, truncated, reach = run(MAIN, with_access=True)
    mean_radius = reach["mean_radius"]
    share_dep = np.divide(served_dep, served, out=np.zeros_like(served), where=served > 0) * 100
    per_team = np.divide(served, eq, out=np.full_like(served, np.nan), where=eq > 0)
    nearest_distance, _ = tree.query(xy, k=1)

    near_edge = units["edge_m"].to_numpy() < mean_radius
    units_out = pd.DataFrame({
        "cnes": units["cnes"], "served_population": served.round(0), "served_deprived_pct": share_dep.round(1),
        "mean_catchment_m": mean_radius.round(0), "edge_m": units["edge_m"].round(0), "near_edge": near_edge,
        "teams_esf": teams["teams_esf"], "teams_eap_20h": teams["teams_eap_20h"], "teams_eap_30h": teams["teams_eap_30h"],
        "team_equivalents": eq, "served_per_team": np.round(per_team, 0),
        "served_mean_distance_m": reach["mean_distance"].round(0), "served_far_pct": (100 * reach["far_share"]).round(1)})
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
    main_class = classify_teams(share_dep, served, eq)
    for name, change in VARIANTS.items():
        params = {**MAIN, **change}
        s, sd, _, _, _, trunc, _ = run(params)
        d = np.divide(sd, s, out=np.zeros_like(s), where=s > 0) * 100
        cls = classify_teams(d, s, eq)
        padeiros = int(np.flatnonzero(units["cnes"].to_numpy() == PADEIROS)[0])
        sensitivity[name] = {
            "spearman_served": round(float(spearmanr(s, served).statistic), 3),
            "spearman_deprived": round(float(spearmanr(d, share_dep).statistic), 3),
            "same_class_share": round(float((cls == main_class).mean()), 3),
            "classes": {c: int((cls == c).sum()) for c in ("above", "within", "below", "pressure", "served")},
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
        "teams": team_stats,
        "served_per_team": describe(per_team[eq > 0]),
        "per_team_against_pnab": {"below": int((per_team[eq > 0] < PNAB_LOW).sum()),
                                  "within": int(((per_team >= PNAB_LOW) & (per_team <= PNAB_HIGH)).sum()),
                                  "above": int((per_team[eq > 0] > PNAB_HIGH).sum())},
        "classes": {c: int((main_class == c).sum()) for c in ("above", "within", "below", "pressure", "served")},
        "near_edge": {"units": int(near_edge.sum()),
                      **{f"of_them_{c}": int((near_edge & (main_class == c)).sum()) for c in ("above", "within", "below")}},
        "reach": {"mean_distance_m": describe(reach["mean_distance"]), "far_pct": describe(100 * reach["far_share"]),
                  **{f"mean_distance_over_{m}m": int((reach["mean_distance"] > m).sum()) for m in (1500, 2000, 3000)},
                  "need_high_and_over_2000m": int(((main_class != "none") & (reach["mean_distance"] > FAR_M)).sum())},
        "mean_catchment_m": describe(mean_radius),
        "padeiros": {"served_population": round(float(served[padeiros])), "served_deprived_pct": round(float(share_dep[padeiros]), 1),
                     "class": str(main_class[padeiros]), "mean_catchment_m": round(float(mean_radius[padeiros])),
                     "team_equivalents": float(eq[padeiros]), "served_per_team": round(float(per_team[padeiros])),
                     "mean_distance_m": round(float(reach["mean_distance"][padeiros])),
                     "far_pct": round(float(100 * reach["far_share"][padeiros]), 1),
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
