"""Decide between a facility's CNES coordinate and its CNEFE address position using
the health establishments that census enumerators recorded on the ground.

CNEFE 2022 marks each address with what occupies it (COD_ESPECIE = 5: health
establishment) and the name the enumerator wrote down. For every facility that has
both a CNES coordinate and a CNEFE address match, this script looks for a health
establishment whose recorded name matches the facility's name, and measures how far
it is from each of the two candidate positions.

Evidence levels, per candidate position:
  named    a health establishment with a matching name within NEAR_M
  unnamed  some health establishment within NEAR_M, name not matching

Run after geocode_cnefe.py. Writes database/geocoding/establishment_evidence.csv.

    python database/geocoding/verify_establishments.py --cnefe-dir ~/Downloads/cnefe_rmsp
"""

import argparse
import re
import unicodedata
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
NEAR_M = 75
HEALTH_ESTABLISHMENT = "5"

# Words that describe the kind of facility, not which one it is
GENERIC = {
    "UBS", "USF", "UPA", "AMA", "AME", "CAPS", "PS", "PA", "UNIDADE", "BASICA", "SAUDE", "FAMILIA",
    "HOSPITAL", "HOSP", "MATERNIDADE", "CLINICA", "CLINICAS", "CENTRO", "POSTO", "PRONTO", "SOCORRO",
    "ATENDIMENTO", "MEDICO", "MEDICA", "MEDICOS", "MEDICINA", "CONSULTORIO", "CONSULTORIOS",
    "LABORATORIO", "LAB", "ANALISES", "DIAGNOSTICO", "DIAGNOSTICOS", "DIAGNOSTICA", "MED", "DIAG",
    "SERVICOS", "SERVICO", "ESPECIALIDADES", "ESPECIALIDADE", "AMBULATORIO", "MUNICIPAL", "ESTADUAL",
    "INSTITUTO", "ODONTOLOGICO", "ODONTOLOGICA", "ODONTOLOGIA", "LTDA", "SA", "ME", "EIRELI", "SS", "SC",
    "DE", "DA", "DO", "DAS", "DOS", "E", "EM", "DR", "DRA", "DOUTOR", "DOUTORA", "PROF", "PROFESSOR",
    "UNIDADE", "FILIAL", "NUCLEO", "ASSISTENCIA", "INTEGRADA", "INTEGRADO", "ESPECIALIZADO", "ESPECIALIZADA",
}
EXPAND = {"JD": "JARDIM", "VL": "VILA", "PQ": "PARQUE", "STA": "SANTA", "STO": "SANTO", "S": "SAO", "CID": "CIDADE"}


def distinctive_tokens(text):
    if not isinstance(text, str):
        return frozenset()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().upper()
    tokens = [EXPAND.get(t, t) for t in re.sub(r"[^A-Z0-9 ]", " ", text).split()]
    return frozenset(t for t in tokens if t not in GENERIC and len(t) >= 3 and not t.isdigit())


def names_match(facility_tokens, establishment_tokens):
    """True when at least half of the shorter name's distinctive words are shared."""
    if not facility_tokens or not establishment_tokens:
        return False
    shared = len(facility_tokens & establishment_tokens)
    return shared >= 1 and shared / min(len(facility_tokens), len(establishment_tokens)) >= 0.5


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371000 * 2 * np.arcsin(np.sqrt(a))


def load_establishments(zip_path):
    with zipfile.ZipFile(zip_path) as archive:
        name = next(n for n in archive.namelist() if n.lower().endswith(".csv"))
        with archive.open(name) as handle:
            df = pd.read_csv(handle, sep=";", dtype=str, encoding="utf-8",
                             usecols=["COD_ESPECIE", "DSC_ESTABELECIMENTO", "LATITUDE", "LONGITUDE"])
    df = df[df["COD_ESPECIE"] == HEALTH_ESTABLISHMENT].copy()
    df["lat"] = pd.to_numeric(df["LATITUDE"], errors="coerce")
    df["lon"] = pd.to_numeric(df["LONGITUDE"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])
    df["tokens"] = df["DSC_ESTABELECIMENTO"].map(distinctive_tokens)
    return df


def evidence(lat, lon, establishments, matching):
    """(named, unnamed, distance to nearest name-matching establishment) for one position."""
    if establishments.empty:
        return False, False, np.nan
    distance = haversine_m(lat, lon, establishments["lat"].to_numpy(), establishments["lon"].to_numpy())
    nearest_named = float(distance[matching].min()) if matching.any() else np.nan
    return bool(nearest_named <= NEAR_M), bool((distance <= NEAR_M).any()), nearest_named


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cnefe-dir", required=True, type=Path)
    args = parser.parse_args()

    detail = pd.read_csv(HERE / "validation_detail.csv", dtype={"cnes": str})
    detail["cnes"] = detail["cnes"].str.zfill(7)
    health = pd.read_csv(ROOT / "data" / "culturaeduca_infraestrutura_saude_rmsp.csv", dtype=str)
    health["cnes"] = health["CO_CNES"].str.zfill(7)
    health["muni"] = health["CO_MUNICIPIO_GESTOR"].str[:6]
    facilities = detail.merge(health[["cnes", "muni", "NO_FANTASIA", "NO_RAZAO_SOCIAL"]], on="cnes")

    rows = []
    for zip_path in sorted(args.cnefe_dir.glob("*.zip")):
        local = facilities[facilities["muni"] == zip_path.name[:6]]
        if local.empty:
            continue
        establishments = load_establishments(zip_path)
        for item in local.itertuples():
            tokens = distinctive_tokens(item.NO_FANTASIA) | distinctive_tokens(item.NO_RAZAO_SOCIAL)
            matching = establishments["tokens"].map(lambda t: names_match(tokens, t)).to_numpy(dtype=bool)
            cnes_named, cnes_any, cnes_dist = evidence(item.ref_lat, item.ref_lon, establishments, matching)
            addr_named, addr_any, addr_dist = evidence(item.lat, item.lon, establishments, matching)
            rows.append({
                "cnes": item.cnes, "tier": item.tier, "geo_level": item.geo_level, "spread_m": item.spread_m,
                "disagreement_m": round(item.error_m), "name_matches_in_municipality": int(matching.sum()),
                "named_at_cnes": cnes_named, "named_at_address": addr_named,
                "any_at_cnes": cnes_any, "any_at_address": addr_any,
                "nearest_named_to_cnes_m": cnes_dist, "nearest_named_to_address_m": addr_dist,
            })
        print(f"{zip_path.name}: {len(local)} facilities, {len(establishments)} health establishments", flush=True)

    result = pd.DataFrame(rows)
    result["verdict"] = np.select(
        [result["named_at_address"] & ~result["named_at_cnes"],
         result["named_at_cnes"] & ~result["named_at_address"],
         result["named_at_address"] & result["named_at_cnes"]],
        ["address", "cnes", "both"], "no_named_evidence")
    result.to_csv(HERE / "establishment_evidence.csv", index=False)

    exact = result[(result["tier"] == "exact_cep") & (result["geo_level"] == 1) & (result["spread_m"] <= 100)]
    bands = pd.cut(exact["disagreement_m"], [-1, 50, 250, 500, 1000, 1e7],
                   labels=["0-50 m", "50-250 m", "250-500 m", "500 m-1 km", "over 1 km"])
    print("\nNamed health establishment found at which position (exact address matches):")
    print(pd.crosstab(bands, exact["verdict"], margins=True).to_string())
    unnamed = exact[exact["verdict"] == "no_named_evidence"]
    print("\nWhere no name matched: any health establishment within range of each position")
    print(pd.crosstab(pd.cut(unnamed["disagreement_m"], [-1, 50, 250, 500, 1000, 1e7],
                             labels=["0-50 m", "50-250 m", "250-500 m", "500 m-1 km", "over 1 km"]),
                      [unnamed["any_at_address"].map({True: "addr:yes", False: "addr:no"}),
                       unnamed["any_at_cnes"].map({True: "cnes:yes", False: "cnes:no"})]).to_string())


if __name__ == "__main__":
    main()
