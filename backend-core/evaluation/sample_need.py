"""Supplementary held-out sample for the need-against-supply sentence.

None of the 40 facilities in sample.csv triggers that sentence (it needs a public primary care unit
in the top quarter for need), so the fault-injection run would never touch its templates. This draws
10 that do, with a fixed seed, one stratum per way the sentence can be told: 2 whose catchment lives
more than 2 km away on average (rule C22), then, among the rest, 3 above, 2 within and 2 below the
PNAB range of people per team, and 1 unit with no registered team (told by rank). Percentiles and
thresholds as in backend-core/src/payload.cpp, facts.cpp and config/rules.json.

    python3 backend-core/evaluation/sample_need.py   # writes backend-core/evaluation/sample_need.csv
"""

import random
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SEED = 20261115
NEED_HIGH = 0.75
PNAB_LOW, PNAB_HIGH = 2000, 3500
FAR_M = 2000


def percentile(values):
    order = np.sort(values)
    below = np.searchsorted(order, values, side="left")
    equal = np.searchsorted(order, values, side="right") - below
    return (below + equal / 2) / len(values)


def main():
    units = pd.read_csv(ROOT / "data" / "catchment_units.csv")
    need = percentile(units["served_deprived_pct"].to_numpy())
    units = units[need >= NEED_HIGH]
    per_team = units["served_per_team"]
    rng = random.Random(SEED)
    far = units[units["served_mean_distance_m"] > FAR_M]
    rest = units[~units["cnes"].isin(far["cnes"])]
    strata = [
        ("far", far, 2),
        ("above", rest[per_team.reindex(rest.index) > PNAB_HIGH], 3),
        ("within", rest[per_team.reindex(rest.index).between(PNAB_LOW, PNAB_HIGH)], 2),
        ("below", rest[per_team.reindex(rest.index) < PNAB_LOW], 2),
        ("no_team", rest[per_team.reindex(rest.index).isna()], 1),
    ]
    rows = [(stratum, cnes) for stratum, frame, k in strata for cnes in rng.sample(sorted(frame["cnes"]), k)]
    pd.DataFrame(rows, columns=["stratum", "cnes"]).to_csv(Path(__file__).with_name("sample_need.csv"), index=False)
    print(" ".join(str(cnes) for _, cnes in rows))


if __name__ == "__main__":
    main()
