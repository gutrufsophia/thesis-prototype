"""Can household crowding predict tuberculosis below the scale where TB is published?

1. Association of district TB rates (São Paulo city, 96 districts) and municipal TB rates (38 other
   RMSP municipalities) with crowding and precarious sewage (Spearman).
2. Transfer across scales: an aggregate-data Poisson model, E[Y_i] = sum_t N_t exp(a + b x_t)
   (Prentice & Sheppard 1995), fitted on municipal totals only, predicts the 96 districts; compared
   with uniform inheritance of the city rate and with redistribution proportional to crowding.
3. Inverse care law (Tudor Hart 1971): share of residents within 1 km of public primary care
   against deprivation, by district and by municipality.

Usage: python3 -I analysis/tb_crowding_scale_transfer.py
"""
import csv
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
YEARS = ['2022', '2023', '2024', '2025']
SAO_PAULO = '355030'
CROWDED = 3.1  # regional 90th percentile of residents per household, as on the facility page


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2
        i = j + 1
    return out


def pearson(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return cov / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))


def spearman(a, b):
    return pearson(ranks(a), ranks(b))


def load_tracts():
    access = {r['cd_setor']: number(r['pct_ate_1000'])
              for r in csv.DictReader(open(ROOT / 'database' / 'geocoding' / 'setor_acesso.csv'))}
    tracts = []
    for r in csv.DictReader(open(ROOT / 'data' / 'dados_censo_culturaeduca.csv')):
        pop, x, hh = number(r['populacao_total']), number(r['media_moradores_domicilio']), number(r['total_domicilios_ocupados'])
        if not pop or not hh or x is None:
            continue
        reported, precarious = number(r['domicilios_esgoto_informado']), number(r['esgoto_precario'])
        tracts.append({'municipality': r['cd_municipio'][:6], 'district': r['cd_setor'][:9], 'pop': pop, 'x': x,
                       'hh': hh, 'precarious': precarious / reported if reported else None,
                       'near': access.get(r['cd_setor'])})
    return tracts


def area_covariates(tracts, key):
    sums = defaultdict(lambda: defaultdict(float))
    for t in tracts:
        s = sums[t[key]]
        s['pop'] += t['pop']
        s['hh'] += t['hh']
        s['x_hh'] += t['x'] * t['hh']
        s['crowded'] += t['pop'] if t['x'] >= CROWDED else 0
        if t['precarious'] is not None:
            s['precarious_hh'] += t['precarious'] * t['hh']
            s['reported_hh'] += t['hh']
        if t['near'] is not None:
            s['near_pop'] += t['near'] * t['pop']
            s['access_pop'] += t['pop']
    return {k: {'x': s['x_hh'] / s['hh'], 'crowded': s['crowded'] / s['pop'],
                'precarious': s['precarious_hh'] / s['reported_hh'] if s['reported_hh'] else 0,
                'near': s['near_pop'] / s['access_pop'] if s['access_pop'] else None, 'pop': s['pop']}
            for k, s in sums.items()}


def fit_aggregate_model(groups, cases, xbar):
    """Profile likelihood in b; a has a closed form given b. Golden-section search."""
    def weight(ts, b):
        return sum(t['pop'] * math.exp(b * (t['x'] - xbar)) for t in ts)

    def loglik(b):
        w = {k: weight(groups[k], b) for k in cases}
        scale = sum(cases.values()) / sum(w.values())
        return sum(y * math.log(scale * w[k]) - scale * w[k] for k, y in cases.items())

    lo, hi = -6.0, 6.0
    for _ in range(80):
        m1, m2 = lo + 0.382 * (hi - lo), lo + 0.618 * (hi - lo)
        if loglik(m1) < loglik(m2):
            lo = m1
        else:
            hi = m2
    b = (lo + hi) / 2
    w = {k: weight(groups[k], b) for k in cases}
    scale = sum(cases.values()) / sum(w.values())
    dispersion = sum((y - scale * w[k]) ** 2 / (scale * w[k]) for k, y in cases.items()) / (len(cases) - 2)
    return b, dispersion, weight


def transfer(tracts, districts, municipal_cases, b, weight):
    """District predictions from municipal data only, by three methods."""
    tracts_by_district = defaultdict(list)
    for t in tracts:
        if t['municipality'] == SAO_PAULO:
            tracts_by_district[t['district']].append(t)
    ds = sorted(d for d in districts if d in tracts_by_district)
    rate = {d: districts[d]['cases'] / districts[d]['pop'] for d in ds}
    total = sum(districts[d]['cases'] for d in ds)
    candidates = {
        'uniform city rate': lambda d: districts[d]['pop'],
        'proportional to crowding': lambda d: sum(t['pop'] * t['x'] for t in tracts_by_district[d]),
        'aggregate-data model': lambda d: weight(tracts_by_district[d], b),
    }
    out = []
    for name, w in candidates.items():
        weights = {d: w(d) for d in ds}
        predicted = {d: total * weights[d] / sum(weights.values()) for d in ds}
        predicted_rate = [predicted[d] / districts[d]['pop'] for d in ds]
        varies = len(set(round(v, 12) for v in predicted_rate)) > 1
        out.append({'method': name,
                    'absolute_error': round(sum(abs(predicted[d] - districts[d]['cases']) for d in ds) / total, 3),
                    'rank_correlation': round(spearman(predicted_rate, [rate[d] for d in ds]), 3) if varies else None})
    return out


def main():
    tracts = load_tracts()
    by_district = area_covariates(tracts, 'district')
    by_municipality = area_covariates(tracts, 'municipality')
    districts = {r['cd_dist']: {'name': r['nm_dist'], 'cases': sum(float(r[f'tb_{y}']) for y in YEARS),
                                'pop': float(r['populacao_total'])}
                 for r in csv.DictReader(open(ROOT / 'data' / 'indicadores_distrito_sp.csv'))}
    municipal_cases = {r['cd_municipio6']: sum(float(r[f'tuberculose_{y}']) for y in YEARS)
                       for r in csv.DictReader(open(ROOT / 'data' / 'indicadores_municipais_rmsp.csv'))}

    ds = sorted(d for d in districts if d in by_district)
    rate = {d: districts[d]['cases'] / len(YEARS) / districts[d]['pop'] * 1e5 for d in ds}
    print('São Paulo city, 96 districts, Spearman with the TB rate (2022-2025):')
    for key, label in (('x', 'residents per household'), ('crowded', 'share in crowded tracts'),
                       ('precarious', 'precarious sewage')):
        print(f'  {label:26s} {spearman([by_district[d][key] for d in ds], [rate[d] for d in ds]):+.2f}')
    top = sorted(ds, key=lambda d: -rate[d])[:6]
    print('  highest rates:', ', '.join(f"{districts[d]['name']} {rate[d]:.1f} ({by_district[d]['x']:.2f}/hh)" for d in top))

    ms = sorted(m for m in municipal_cases if m in by_municipality and m != SAO_PAULO)
    mrate = [municipal_cases[m] / len(YEARS) / by_municipality[m]['pop'] * 1e5 for m in ms]
    print('Other 38 municipalities, Spearman with the TB rate:')
    for key, label in (('x', 'residents per household'), ('crowded', 'share in crowded tracts'),
                       ('precarious', 'precarious sewage')):
        print(f'  {label:26s} {spearman([by_municipality[m][key] for m in ms], mrate):+.2f}')

    groups = defaultdict(list)
    for t in tracts:
        groups[t['municipality']].append(t)
    xbar = sum(t['x'] * t['pop'] for t in tracts) / sum(t['pop'] for t in tracts)
    b, dispersion, weight = fit_aggregate_model(groups, {m: municipal_cases[m] for m in ms}, xbar)
    print(f'Aggregate-data model on municipal totals: rate ratio {math.exp(b):.2f} per extra resident per household; '
          f'Pearson chi2/df {dispersion:.1f}')

    print('Predicting the 96 districts from municipal data only:')
    for r in transfer(tracts, districts, municipal_cases, b, weight):
        rho = 'undefined' if r['rank_correlation'] is None else f"{r['rank_correlation']:+.2f}"
        print(f"  {r['method']:26s} rank correlation {rho}, absolute error {r['absolute_error']:.0%} of cases")

    print('Inverse care law: share of residents within 1 km of public primary care, Spearman with:')
    dd = [d for d in ds if by_district[d]['near'] is not None]
    mm = [m for m in by_municipality if by_municipality[m]['near'] is not None]
    for label, keys, cov in (('districts', dd, by_district), ('municipalities', mm, by_municipality)):
        near = [cov[k]['near'] for k in keys]
        print(f"  {label:15s} crowding {spearman(near, [cov[k]['crowded'] for k in keys]):+.2f}, "
              f"precarious sewage {spearman(near, [cov[k]['precarious'] for k in keys]):+.2f}")


if __name__ == '__main__':
    main()
