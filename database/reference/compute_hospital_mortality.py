"""In-hospital mortality of SUS admissions, read against the deaths each hospital's case mix predicts.

A hospital that treats cancer or intensive care patients has a high crude death rate whatever the
quality of its care. Comparing it with other hospitals therefore needs the deaths its own case mix
would produce at the regional rates: indirect standardisation, the logic of the hospital
standardised mortality ratio (Jarman et al. 1999):

    E_h = sum_k A_hk * r_k,   r_k = sum_h D_hk / sum_h A_hk,   ratio_h = O_h / E_h

with A admissions and D deaths over the RMSP hospitals (general, specialised, mixed units), and k a
cell of diagnosis group (the leaves of the ICD-10 morbidity list, about 300) x age group (13) x
admission type (elective or not), as in the HSMR's diagnosis, age and admission method. A first
version used the ICD-10 chapter alone; it made children's hospitals look far safer than expected
(respiratory deaths are mostly of old people) and gave eye and ENT institutes the death rate of
pneumonia (tonsillectomy is a respiratory diagnosis). The chapter-only figures are kept in the
summary for comparison. The adjustment still leaves out severity, comorbidity, transfers and
palliative care, so the ratio is a screening figure, not a quality judgement (Lilford & Pronovost
2010; Shahian et al. 2010).

Whether a ratio departs from 1 more than chance allows is read on a funnel plot (Spiegelhalter
2005) on the log scale, the usual one for ratios: log(O/E) has variance about 1/E under the null,
with 0.5 added to O when no death occurred. The z-scores are Winsorised at 10% to estimate the
overdispersion phi, and when phi > 1 an additive random-effects variance tau^2 widens the limits
(Spiegelhalter 2005, sections 3.5 and 3.6): exp(+-z_p sqrt(1/E + tau^2)), at 95% and 99.8%.

The narrative does not label hospitals above or below expected: phi measures how much of the
variation the diagnosis chapter leaves unexplained, and it is large. It tells the crude rate and the
rate the case mix alone predicts, with the caveat. The funnel is shown on the facility page.

What makes a hospital's expected rate e_h differ from the regional crude rate R is a matter of
composition (Kitagawa 1955; Das Gupta 1993). Let f(S) be the rate the hospital's admissions would
have at regional rates stratified only by the dimensions in S, the others pooled: f({}) = R and
f(all three) = e_h. The Shapley value of each dimension (Shorrocks 2013) splits e_h - R among
diagnosis, age and admission type without depending on the order they are added. The narrative
names the dimension that moves the expected rate most in the direction it moved, with the hospital's
and the region's share of what that dimension is about: admissions aged 70 or more, urgent
admissions, or the ICD-10 chapter whose over- or under-representation counts most,
(p_h(c) - p_R(c)) (r_c - R). This explains the expected rate, that is the model, not the deaths.

Inputs: database/tabnet/raw/sih_internacoes_cap.csv and sih_obitos_cap.csv (fetch_tabnet.py), the
per-hospital tables in database/tabnet/raw/sih_hospitals/ (fetch_sih_hospitals.py), and the
facility list in the database. Writes data/hospital_mortality.csv,
data/hospital_mortality_summary.json and public/data/hospital_mortality.json (funnel points).

    python3 database/reference/compute_hospital_mortality.py
"""

import csv
import io
import json
import math
import sys
from pathlib import Path

import numpy as np
import psycopg2
from scipy.stats import norm, spearmanr

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "database" / "tabnet" / "raw"
sys.path.insert(0, str(ROOT / "database" / "seeders"))
from seed import read_env  # noqa: E402

HOSPITAL_TYPES = {"Hospital Geral", "Hospital Especializado", "Unidade Mista"}
LIMITS = {"95": 0.975, "998": 0.999}
WINSOR = 0.10  # Spiegelhalter (2005): Winsorise 10% at each end before estimating overdispersion
MIN_EXPECTED = 5  # rule C24 (backend-core/config/rules.json)
OLD_AGES = ("70 a 79 anos", "80 anos e mais")
FACTORS = ("diagnosis", "age", "urgency")  # positions 0, 1, 2 of a cell key (group, age, kind)
# ICD-10 chapter number of the morbidity list -> admissions column of infraestrutura_saude (etl/limpeza.py)
CHAPTER_KEYS = {
    "01": "internacoes_infecciosas_parasitarias", "02": "internacoes_neoplasias_tumores",
    "03": "internacoes_sangue_imunitarias", "04": "internacoes_endocrinas_nutricionais",
    "05": "internacoes_transtornos_mentais", "06": "internacoes_sistema_nervoso",
    "07": "internacoes_olho_anexos", "08": "internacoes_ouvido_mastoide",
    "09": "internacoes_aparelho_circulatorio", "10": "internacoes_aparelho_respiratorio",
    "11": "internacoes_aparelho_digestivo", "12": "internacoes_pele_tecido_subcutaneo",
    "13": "internacoes_osteomuscular_conjuntivo", "14": "internacoes_aparelho_geniturinario",
    "15": "internacoes_gravidez_parto_puerperio", "16": "internacoes_afeccoes_perinatais",
    "17": "internacoes_malformacoes_congenitas", "18": "internacoes_sintomas_sinais_anormais",
    "19": "internacoes_lesoes_envenenamentos", "20": "internacoes_causas_externas",
    "21": "internacoes_contatos_servicos_saude",
}


def read_tabnet(path):
    lines = [line for line in path.read_text(encoding="utf-8").splitlines(keepends=True) if not line.startswith("#")]
    rows = list(csv.reader(io.StringIO("".join(lines)), delimiter=";"))
    chapters = [h for h in rows[0][1:] if h != "Total"]
    out = {}
    for row in rows[1:]:
        if not row or not row[0][:7].isdigit():
            continue
        values = dict(zip(rows[0][1:], row[1:]))
        out[int(row[0][:7])] = {c: 0 if values.get(c) in (None, "-", "") else int(values[c]) for c in chapters}
    return chapters, out


def read_cells(path):
    """Leaf diagnosis group x age group counts from one per-hospital table."""
    text = path.read_text(encoding="utf-8").strip() if path.exists() else ""
    if not text:
        return {}
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=";") if r and r[0]]
    ages = rows[0][1:]
    body = [r for r in rows[1:] if not r[0].startswith("Total")]
    depth = [(len(r[0]) - len(r[0].lstrip("."))) // 2 for r in body]
    out, stack = {}, []
    for i, r in enumerate(body):
        stack = stack[:depth[i]] + [r[0].lstrip(". ").strip()]
        if i + 1 < len(body) and depth[i + 1] > depth[i]:
            continue  # a group with subgroups: its leaves carry the counts
        for age, value in zip(ages, r[1:]):
            if age != "Total" and value not in ("-", ""):
                out[(" > ".join(stack), age)] = int(value)
    return out


def case_mix(hospitals, folder):
    """Admissions and deaths of each hospital by cell (diagnosis group, age group, admission type)."""
    A, D = {}, {}
    for h in hospitals:
        A[h], D[h] = {}, {}
        for kind in ("ele", "urg"):
            for (group, age), n in read_cells(folder / f"{h}_adm_{kind}.csv").items():
                A[h][(group, age, kind)] = n
            for (group, age), n in read_cells(folder / f"{h}_obt_{kind}.csv").items():
                D[h][(group, age, kind)] = n
    return A, D


def load_facilities(url):
    with psycopg2.connect(url) as conn, conn.cursor() as cur:
        cur.execute('select "CO_CNES", tipo_equipamento, '
                    'coalesce(nullif(btrim("NO_FANTASIA"), \'\'), "NO_RAZAO_SOCIAL") from infraestrutura_saude')
        rows = cur.fetchall()
    return {c: t for c, t, _ in rows}, {c: n for c, _, n in rows}


def pooled_rates(pooled_A, pooled_D, keep):
    """Regional death rate by the dimensions in `keep`, the others pooled."""
    A_s, D_s = {}, {}
    for k, n in pooled_A.items():
        s = tuple(k[j] for j in keep)
        A_s[s] = A_s.get(s, 0) + n
        D_s[s] = D_s.get(s, 0) + pooled_D.get(k, 0)
    return {s: D_s[s] / n for s, n in A_s.items() if n > 0}


def shares(cells, test):
    total = sum(cells.values())
    return sum(n for k, n in cells.items() if test(k)) / total if total else 0.0


def chapter_of(group):
    return CHAPTER_KEYS[group[:2]]


def composition(cells):
    """Shares of admissions aged 70 or more, urgent, and in each ICD-10 chapter."""
    chapters = {}
    for k, n in cells.items():
        chapters[chapter_of(k[0])] = chapters.get(chapter_of(k[0]), 0) + n
    total = sum(cells.values())
    return {"age": shares(cells, lambda k: k[1] in OLD_AGES), "urgency": shares(cells, lambda k: k[2] == "urg"),
            "chapters": {c: n / total for c, n in chapters.items()}}


def profile(cells, subset_rates, region, chapter_rate, regional_rate):
    """Shapley split of expected - regional rate, with the shares that describe each factor.

    Which factors the text names is decided by the narrative (rule parameters casemix_*)."""
    total = sum(cells.values())
    f = {mask: sum(n * rates[tuple(k[j] for j in range(3) if mask >> j & 1)] for k, n in cells.items()) / total
         for mask, rates in subset_rates.items()}
    weight = {0: 1 / 3, 1: 1 / 6, 2: 1 / 3}  # |S|! (n - |S| - 1)! / n! for n = 3
    shapley = {}
    for j, name in enumerate(FACTORS):
        shapley[name] = sum(weight[bin(m).count("1")] * (f[m | 1 << j] - f[m]) for m in range(8) if not m >> j & 1)
    sign = 1 if f[7] >= regional_rate else -1
    own = composition(cells)

    def term(c):
        return (own["chapters"].get(c, 0) - region["chapters"].get(c, 0)) * (chapter_rate[c] - regional_rate)
    # A chapter the hospital has more of reads more plainly than one it lacks ("fewer childbirths
    # than the region" for a higher expected rate), so over-represented chapters come first.
    over = [c for c in chapter_rate if own["chapters"].get(c, 0) > region["chapters"].get(c, 0) and sign * term(c) > 0]
    chapter = max(over or chapter_rate, key=lambda c: sign * term(c))
    return {
        "factor": max(FACTORS, key=lambda name: sign * shapley[name]),
        "shapley_pp": {k: round(100 * v, 2) for k, v in shapley.items()},
        "old_pct": round(100 * own["age"], 1), "old_region_pct": round(100 * region["age"], 1),
        "urgent_pct": round(100 * own["urgency"], 1), "urgent_region_pct": round(100 * region["urgency"], 1),
        "chapter": chapter, "chapter_pct": round(100 * own["chapters"].get(chapter, 0), 1),
        "chapter_region_pct": round(100 * region["chapters"].get(chapter, 0), 1),
        "chapter_rate_region_pct": round(100 * chapter_rate[chapter], 2),
    }


def overdispersion(z):
    """Winsorised overdispersion factor phi = mean of z^2 (Spiegelhalter 2005, section 3.5)."""
    lo, hi = np.quantile(z, [WINSOR, 1 - WINSOR])
    zw = np.clip(z, lo, hi)
    return float(np.mean(zw ** 2))


def main():
    chapters, admissions = read_tabnet(RAW / "sih_internacoes_cap.csv")
    _, deaths = read_tabnet(RAW / "sih_obitos_cap.csv")
    types, names = load_facilities(read_env(ROOT / ".env")["DATABASE_URL"])

    hospitals = sorted(c for c in admissions if types.get(c) in HOSPITAL_TYPES and sum(admissions[c].values()) > 0)
    A = np.array([[admissions[h][c] for c in chapters] for h in hospitals], dtype=float)
    D = np.array([[deaths.get(h, {}).get(c, 0) for c in chapters] for h in hospitals], dtype=float)
    rates = D.sum(axis=0) / np.where(A.sum(axis=0) > 0, A.sum(axis=0), np.nan)
    rates = np.nan_to_num(rates)

    observed = D.sum(axis=1)
    expected_chapter = A @ rates
    chapter_ratio = observed / expected_chapter

    # Expected deaths from the full case mix: diagnosis group x age group x admission type
    cells_A, cells_D = case_mix(hospitals, RAW / "sih_hospitals")
    pooled_A, pooled_D = {}, {}
    for h in hospitals:
        for k, n in cells_A[h].items():
            pooled_A[k] = pooled_A.get(k, 0) + n
        for k, n in cells_D[h].items():
            pooled_D[k] = pooled_D.get(k, 0) + n
    cell_rate = {k: pooled_D.get(k, 0) / n for k, n in pooled_A.items() if n > 0}
    expected = np.array([sum(n * cell_rate[k] for k, n in cells_A[h].items()) for h in hospitals])
    cell_admissions = np.array([sum(cells_A[h].values()) for h in hospitals])
    cell_deaths = np.array([sum(cells_D[h].values()) for h in hospitals])
    mismatch = [(h, int(A[i].sum()), int(cell_admissions[i]), int(observed[i]), int(cell_deaths[i]))
                for i, h in enumerate(hospitals) if cell_admissions[i] != A[i].sum() or cell_deaths[i] != observed[i]]
    # A hospital whose patients all fall in cells without deaths in the region expects none: no ratio.
    usable = expected > 0
    safe = np.where(usable, expected, 1.0)
    ratio = np.where(usable, observed / safe, np.nan)
    log_ratio = np.log(np.where(observed > 0, observed, 0.5) / safe)
    se = 1 / np.sqrt(safe)  # SD of log(O/E) under the Poisson null, O ~ Poisson(E)
    z = log_ratio / se
    # Heterogeneity estimated on the hospitals the text compares (rule C24: at least 5 expected deaths)
    fit = expected >= MIN_EXPECTED
    phi = overdispersion(z[fit])
    n = int(fit.sum())
    w = 1 / se[fit] ** 2
    tau2 = max(0.0, (n * phi - (n - 1)) / (w.sum() - (w ** 2).sum() / w.sum())) if phi > 1 else 0.0
    spread = np.sqrt(se ** 2 + tau2)

    regional_rate = sum(pooled_D.values()) / sum(pooled_A.values())
    subset_rates = {mask: pooled_rates(pooled_A, pooled_D, tuple(j for j in range(3) if mask >> j & 1))
                    for mask in range(8)}
    chapter_A, chapter_D = {}, {}
    for k, n in pooled_A.items():
        c = chapter_of(k[0])
        chapter_A[c] = chapter_A.get(c, 0) + n
        chapter_D[c] = chapter_D.get(c, 0) + pooled_D.get(k, 0)
    chapter_rate = {c: chapter_D[c] / n for c, n in chapter_A.items() if n > 0}
    region = composition(pooled_A)

    rows = []
    for i, h in enumerate(hospitals):
        if not usable[i]:
            continue
        limits = {k: (math.exp(-norm.ppf(p) * spread[i]), math.exp(norm.ppf(p) * spread[i])) for k, p in LIMITS.items()}
        lo, hi = limits["998"]
        band = "above" if ratio[i] > hi else "below" if ratio[i] < lo else "within"
        top = int(np.argmax(A[i]))
        mix = profile(cells_A[h], subset_rates, region, chapter_rate, regional_rate)
        rows.append({
            "cnes": h, "admissions": int(A[i].sum()), "deaths": int(observed[i]),
            "mortality_pct": round(100 * observed[i] / A[i].sum(), 2),
            "expected_deaths": round(float(expected[i]), 1), "ratio": round(float(ratio[i]), 3),
            "expected_pct": round(100 * float(expected[i]) / A[i].sum(), 2),
            "lower_95": round(limits["95"][0], 3), "upper_95": round(limits["95"][1], 3),
            "lower_998": round(lo, 3), "upper_998": round(hi, 3), "band": band,
            "top_chapter": chapters[top], "top_chapter_pct": round(100 * A[i, top] / A[i].sum(), 1),
            "region_mortality_pct": round(100 * regional_rate, 2), "profile_factor": mix["factor"],
            "shapley_diagnosis_pp": mix["shapley_pp"]["diagnosis"], "shapley_age_pp": mix["shapley_pp"]["age"],
            "shapley_urgency_pp": mix["shapley_pp"]["urgency"],
            "old_pct": mix["old_pct"], "old_region_pct": mix["old_region_pct"],
            "urgent_pct": mix["urgent_pct"], "urgent_region_pct": mix["urgent_region_pct"],
            "chapter": mix["chapter"], "chapter_pct": mix["chapter_pct"], "chapter_region_pct": mix["chapter_region_pct"],
            "chapter_rate_region_pct": mix["chapter_rate_region_pct"],
        })

    with open(ROOT / "data" / "hospital_mortality.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    compared = [r for r in rows if r["expected_deaths"] >= MIN_EXPECTED and r["admissions"] >= 100]
    bands = {b: sum(1 for r in compared if r["band"] == b) for b in ("above", "within", "below")}
    # Shapley efficiency: the three parts add up to expected - regional rate (up to rounding)
    worst = max(abs(r["shapley_diagnosis_pp"] + r["shapley_age_pp"] + r["shapley_urgency_pp"]
                    - (r["expected_pct"] - 100 * regional_rate)) for r in rows)
    assert worst < 0.05, worst
    summary = {
        "period": "SIH, SUS admissions processed Jan/2025 to Jul/2026, by place of admission",
        "hospitals": len(hospitals), "hospitals_with_expected_deaths": int(usable.sum()),
        "hospitals_compared": len(compared), "hospitals_in_heterogeneity_fit": n,
        "admissions": int(A.sum()), "deaths": int(D.sum()),
        "regional_mortality_pct": round(100 * D.sum() / A.sum(), 2),
        "chapter_mortality_pct": {c: round(100 * r, 2) for c, r in zip(chapters, rates)},
        "overdispersion_phi": round(phi, 2), "tau2": round(tau2, 5), "tau": round(math.sqrt(tau2), 3),
        "bands_998_compared": bands, "within_95_compared": sum(1 for r in compared if r["lower_95"] <= r["ratio"] <= r["upper_95"]),
        "crude_mortality_pct": {"median": round(float(np.median(100 * observed / A.sum(axis=1))), 2),
                                "p10": round(float(np.percentile(100 * observed / A.sum(axis=1), 10)), 2),
                                "p90": round(float(np.percentile(100 * observed / A.sum(axis=1), 90)), 2)},
        "ratio": {"median": round(float(np.nanmedian(ratio)), 3), "p10": round(float(np.nanpercentile(ratio, 10)), 3),
                  "p90": round(float(np.nanpercentile(ratio, 90)), 3)},
        "crude_vs_ratio_spearman": None,
        "cells": len(pooled_A), "cells_with_deaths": sum(1 for k in pooled_A if pooled_D.get(k, 0) > 0),
        "hospitals_whose_cells_do_not_add_up": mismatch,
        "chapter_only": {"overdispersion_phi": None, "ratio_median": round(float(np.median(chapter_ratio)), 3)},
        "region_composition_pct": {"aged_70_or_more": round(100 * region["age"], 1),
                                   "urgent": round(100 * region["urgency"], 1)},
        "profile_factor_compared": {f: sum(1 for r in compared if r["profile_factor"] == f) for f in FACTORS},
        "shapley_efficiency_max_error_pp": round(worst, 4),
    }
    z_chapter = np.log(np.where(observed > 0, observed, 0.5) / expected_chapter) * np.sqrt(expected_chapter)
    summary["chapter_only"]["overdispersion_phi"] = round(overdispersion(z_chapter[fit]), 2)  # same hospitals as phi
    summary["chapter_only"]["crude_vs_ratio_spearman"] = round(float(spearmanr(observed / A.sum(axis=1), chapter_ratio)[0]), 3)
    summary["crude_vs_ratio_spearman"] = round(float(spearmanr((observed / A.sum(axis=1))[usable], ratio[usable])[0]), 3)
    (ROOT / "data" / "hospital_mortality_summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
    funnel = {"period": summary["period"], "hospitals": len(rows), "regional_mortality_pct": summary["regional_mortality_pct"],
              "tau2": round(tau2, 5), "z": {k: round(float(norm.ppf(p)), 4) for k, p in LIMITS.items()},
              # [cnes, name, admissions, deaths, expected deaths]
              "points": [[r["cnes"], names.get(r["cnes"], ""), r["admissions"], r["deaths"], r["expected_deaths"]]
                         for r in rows]}
    (ROOT / "public" / "data" / "hospital_mortality.json").write_text(json.dumps(funnel, separators=(",", ":")) + "\n")
    print(json.dumps(summary, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
