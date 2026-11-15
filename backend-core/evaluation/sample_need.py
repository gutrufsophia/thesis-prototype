"""Supplementary held-out sample for the need-against-supply sentence.

None of the 40 facilities in sample.csv triggers that sentence (it needs a public primary care unit
in the top quarter for need and in either extreme quarter for supply), so the fault-injection run
would never touch its templates. This draws 10 that do, with a fixed seed: 2 "served" near the
region's edge (rule C21b), 3 "served" elsewhere and 5 "pressure", using the same percentiles and
thresholds as backend-core/src/payload.cpp and facts.cpp.

    python3 backend-core/evaluation/sample_need.py   # writes backend-core/evaluation/sample_need.csv
"""

import random
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SEED = 20261115
NEED_HIGH = 0.75


def percentile(values):
    order = np.sort(values)
    below = np.searchsorted(order, values, side="left")
    equal = np.searchsorted(order, values, side="right") - below
    return (below + equal / 2) / len(values)


def main():
    units = pd.read_csv(ROOT / "data" / "catchment_units.csv")
    need = percentile(units["served_deprived_pct"].to_numpy())
    load = percentile(units["served_population"].to_numpy())
    units["variant"] = np.where(need >= NEED_HIGH,
                                np.where(load >= NEED_HIGH, "pressure", np.where(load <= 1 - NEED_HIGH, "served", "")), "")
    rng = random.Random(SEED)
    strata = [
        ("served_edge", units[(units["variant"] == "served") & units["near_edge"]], 2),
        ("served", units[(units["variant"] == "served") & ~units["near_edge"]], 3),
        ("pressure", units[units["variant"] == "pressure"], 5),
    ]
    rows = [(stratum, cnes) for stratum, frame, k in strata for cnes in rng.sample(sorted(frame["cnes"]), k)]
    pd.DataFrame(rows, columns=["stratum", "cnes"]).to_csv(Path(__file__).with_name("sample_need.csv"), index=False)
    print(" ".join(str(cnes) for _, cnes in rows))


if __name__ == "__main__":
    main()
