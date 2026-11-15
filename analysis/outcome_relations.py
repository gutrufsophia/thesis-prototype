"""Relations between disease outcomes (TB, dengue, leptospirosis, births to teenage mothers) and census
living conditions, at the two scales where outcomes exist: the 39 RMSP municipalities and the 96
districts of São Paulo city.

- Pairs are fixed in advance from the literature, not searched for.
- Spearman's rho with a 95% interval (Fisher z, SE = sqrt(1.06 / (n - 3)); Fieller, Hartley & Pearson 1957).
- Leptospirosis rates are smoothed by global empirical Bayes (Marshall 1991): counts are tiny.
- Expected counts come from a quasi-Poisson GLM; an area is flagged when its observed count falls
  outside the 95% prediction interval (dispersion plus parameter uncertainty). Models explaining
  less than MIN_DEVIANCE_EXPLAINED of the deviance are reported but never used to flag areas.

Writes public/data/relations.json (charts) and data/outcome_expected.csv (storytelling service).
Usage: python3 -I analysis/outcome_relations.py
"""
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tb_crowding_scale_transfer import (  # noqa: E402
    CROWDED, SAO_PAULO, YEARS, area_covariates, fit_aggregate_model, load_tracts, transfer)

ROOT = Path(__file__).resolve().parents[1]
MIN_DEVIANCE_EXPLAINED = 0.3
Z95 = 1.96

DETERMINANTS = {
    'precarious': 'Households with precarious sewage disposal',
    'no_garbage': 'Households without garbage collection',
    'crowded': f'Residents in tracts with {CROWDED} or more residents per household',
    'near': 'Residents within 1 km (straight line) of public primary care',
    'income': 'Mean monthly income of household heads with income (BRL)',
}
# (outcome, determinant): each pair has a stated mechanism in the literature
PAIRS = [
    ('tb', 'crowded'), ('tb', 'precarious'), ('tb', 'income'),
    ('dengue_2024', 'no_garbage'), ('dengue_2024', 'precarious'), ('dengue_2024', 'income'),
    ('lepto', 'precarious'), ('lepto', 'no_garbage'), ('lepto', 'income'),
    ('teen', 'crowded'), ('teen', 'income'),
]


# ---------- statistics ----------

def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    out, i = [0.0] * len(values), 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2
        i = j + 1
    return out


def spearman(a, b):
    ra, rb = ranks(a), ranks(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    spread = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    if spread == 0:
        return None, None, None  # no variation left to rank (e.g. every rate shrunk to the mean)
    rho = cov / spread
    se = math.sqrt(1.06 / (len(a) - 3))
    z = math.atanh(max(-0.999999, min(0.999999, rho)))
    return rho, math.tanh(z - Z95 * se), math.tanh(z + Z95 * se)


def solve(a, b):
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c])]
    return [m[i][n] / m[i][i] for i in range(n)]


def inverse(a):
    n = len(a)
    cols = [solve(a, [1.0 if i == j else 0.0 for i in range(n)]) for j in range(n)]
    return [[cols[j][i] for j in range(n)] for i in range(n)]


def poisson_glm(y, x, offset):
    """IRLS for log(mu) = offset + b0 + b.x, with quasi-Poisson dispersion."""
    rows = [[1.0] + xi for xi in x]
    p = len(rows[0])
    beta = [math.log(sum(y) / sum(math.exp(o) for o in offset))] + [0.0] * (p - 1)
    for _ in range(100):
        eta = [sum(b * v for b, v in zip(beta, r)) + o for r, o in zip(rows, offset)]
        mu = [math.exp(e) for e in eta]
        z = [e - o + (yi - m) / m for e, o, yi, m in zip(eta, offset, y, mu)]
        xtwx = [[sum(m * r[i] * r[j] for r, m in zip(rows, mu)) for j in range(p)] for i in range(p)]
        xtwz = [sum(m * r[i] * zi for r, m, zi in zip(rows, mu, z)) for i in range(p)]
        new = solve(xtwx, xtwz)
        done = max(abs(a - b) for a, b in zip(new, beta)) < 1e-10
        beta = new
        if done:
            break
    mu = [math.exp(sum(b * v for b, v in zip(beta, r)) + o) for r, o in zip(rows, offset)]
    xtwx = [[sum(m * r[i] * r[j] for r, m in zip(rows, mu)) for j in range(p)] for i in range(p)]

    def deviance(fitted):
        return 2 * sum((yi * math.log(yi / m) if yi > 0 else 0) - (yi - m) for yi, m in zip(y, fitted))

    null_mu = [math.exp(o) * sum(y) / sum(math.exp(o2) for o2 in offset) for o in offset]
    dispersion = sum((yi - m) ** 2 / m for yi, m in zip(y, mu)) / (len(y) - p)
    cov = [[dispersion * v for v in row] for row in inverse(xtwx)]
    return {'beta': beta, 'cov': cov, 'mu': mu, 'rows': rows, 'dispersion': dispersion,
            'deviance_explained': 1 - deviance(mu) / deviance(null_mu)}


def empirical_bayes(cases, population):
    """Global empirical Bayes rates (Marshall 1991)."""
    k = len(cases)
    m = sum(cases) / sum(population)
    n_bar = sum(population) / k
    rates = [c / n for c, n in zip(cases, population)]
    s2 = sum(n * (r - m) ** 2 for n, r in zip(population, rates)) / sum(population)
    a = max(0.0, s2 - m / n_bar)
    return [m + (a / (a + m / n)) * (r - m) if a > 0 else m for r, n in zip(rates, population)]


# ---------- data ----------

def load_areas():
    tracts = load_tracts()
    garbage = {}
    for r in csv.DictReader(open(ROOT / 'data' / 'dados_censo_culturaeduca.csv')):
        reported = float(r['domicilios_lixo_informado'] or 0)
        if reported:
            garbage[r['cd_setor']] = (float(r['total_lixo_coletado'] or 0), reported)

    def no_garbage(key):
        sums = defaultdict(lambda: [0.0, 0.0])
        for r in csv.DictReader(open(ROOT / 'data' / 'dados_censo_culturaeduca.csv')):
            if r['cd_setor'] in garbage:
                area = r['cd_setor'][:9] if key == 'district' else r['cd_municipio'][:6]
                sums[area][0] += garbage[r['cd_setor']][0]
                sums[area][1] += garbage[r['cd_setor']][1]
        return {k: 100 * (1 - c / t) for k, (c, t) in sums.items()}

    income = defaultdict(lambda: [0.0, 0.0])
    for r in csv.DictReader(open(ROOT / 'data' / 'renda_responsavel_rmsp.csv')):
        if r['renda_media_responsavel'] and r['responsaveis']:
            heads, mean = float(r['responsaveis']), float(r['renda_media_responsavel'])
            for area in (r['cd_setor'][:9], r['cd_setor'][:6]):
                income[area][0] += mean * heads
                income[area][1] += heads

    def mean_income(area):
        total, heads = income[area]
        return total / heads if heads else None

    names = {r['cd_municipio6']: r['nome'] for r in csv.DictReader(open(ROOT / 'data' / 'municipalities.csv'))}
    municipalities = []
    cov, ng = area_covariates(tracts, 'municipality'), no_garbage('municipality')
    for r in csv.DictReader(open(ROOT / 'data' / 'indicadores_municipais_rmsp.csv')):
        code = r['cd_municipio6']
        c = cov[code]
        municipalities.append({
            'code': code, 'name': names[code], 'population': round(c['pop']),
            'precarious': 100 * c['precarious'], 'no_garbage': ng[code], 'crowded': 100 * c['crowded'],
            'near': c['near'], 'income': mean_income(code), 'log_income': math.log(mean_income(code)),
            'cases': {'tb': sum(float(r[f'tuberculose_{y}']) for y in YEARS), 'dengue_2024': float(r['dengue_2024']),
                      'dengue_2025': float(r['dengue_2025']), 'lepto': sum(float(r[f'lepto_{y}']) for y in YEARS),
                      'teen': float(r['nasc_mae_menor_20'])},
            'denominator_births': float(r['nasc_idade_conhecida']),
        })
    districts = []
    cov, ng = area_covariates(tracts, 'district'), no_garbage('district')
    for r in csv.DictReader(open(ROOT / 'data' / 'indicadores_distrito_sp.csv')):
        code = r['cd_dist']
        c = cov[code]
        districts.append({
            'code': code, 'name': r['nm_dist'], 'population': round(c['pop']),
            'precarious': 100 * c['precarious'], 'no_garbage': ng[code], 'crowded': 100 * c['crowded'],
            'near': c['near'], 'income': mean_income(code), 'log_income': math.log(mean_income(code)),
            'cases': {'tb': sum(float(r[f'tb_{y}']) for y in YEARS), 'teen': float(r['nasc_mae_menor_20'])},
            'denominator_births': float(r['nasc_idade_conhecida']),
        })
    return municipalities, districts


def outcome_value(area, outcome, years=len(YEARS)):
    cases = area['cases'][outcome]
    if outcome == 'teen':
        return 100 * cases / area['denominator_births']
    per_year = cases / years if outcome in ('tb', 'lepto') else cases
    return per_year / area['population'] * 1e5


# ---------- analysis ----------

def relations(areas, scale):
    if scale == 'municipality':
        lepto_eb = empirical_bayes([a['cases']['lepto'] / len(YEARS) for a in areas], [a['population'] for a in areas])
        for a, rate in zip(areas, lepto_eb):
            a['lepto_eb'] = rate * 1e5
    out = []
    for outcome, determinant in PAIRS:
        if outcome not in areas[0]['cases']:
            continue
        ys = [a['lepto_eb'] if outcome == 'lepto' else outcome_value(a, outcome) for a in areas]
        xs = [a[determinant] for a in areas]
        rho, lo, hi = spearman(xs, ys)
        out.append({'scale': scale, 'outcome': outcome, 'determinant': determinant, 'n': len(areas),
                    'rho': None if rho is None else round(rho, 3),
                    'ci': None if rho is None else [round(lo, 3), round(hi, 3)]})
    return out


def expected_model(areas, outcome, covariates, scale):
    y = [a['cases'][outcome] for a in areas]
    exposure = [a['denominator_births'] if outcome == 'teen' else a['population'] * len(YEARS) for a in areas]
    means = {c: sum(a[c] for a in areas) / len(areas) for c in covariates}
    sds = {c: math.sqrt(sum((a[c] - means[c]) ** 2 for a in areas) / (len(areas) - 1)) for c in covariates}
    x = [[(a[c] - means[c]) / sds[c] for c in covariates] for a in areas]
    fit = poisson_glm(y, x, [math.log(e) for e in exposure])
    usable = fit['deviance_explained'] >= MIN_DEVIANCE_EXPLAINED
    rows = []
    for a, yi, mu, r in zip(areas, y, fit['mu'], fit['rows']):
        var_eta = sum(r[i] * fit['cov'][i][j] * r[j] for i in range(len(r)) for j in range(len(r)))
        sd = math.sqrt(fit['dispersion'] * mu + mu * mu * var_eta)
        lower, upper = max(0.0, mu - Z95 * sd), mu + Z95 * sd
        flag = ('above' if yi > upper else 'below' if yi < lower else '') if usable else ''
        rows.append({'scale': scale, 'code': a['code'], 'name': a['name'], 'outcome': outcome, 'observed': yi,
                     'expected': round(mu, 1), 'lower': round(lower, 1), 'upper': round(upper, 1), 'flag': flag})
    model = {'scale': scale, 'outcome': outcome, 'n': len(areas), 'covariates': covariates,
             'rate_ratio_per_sd': {c: round(math.exp(fit['beta'][i + 1]), 3) for i, c in enumerate(covariates)},
             'deviance_explained': round(fit['deviance_explained'], 3), 'dispersion': round(fit['dispersion'], 1),
             'used_for_flags': usable, 'flagged': sum(1 for r in rows if r['flag'])}
    return model, rows


def main():
    municipalities, districts = load_areas()
    pairs = relations(municipalities, 'municipality') + relations(districts, 'district')

    models, expected = [], []
    for areas, scale, outcome, covariates in [
        (districts, 'district', 'tb', ['crowded', 'precarious', 'log_income']),
        (municipalities, 'municipality', 'tb', ['crowded', 'precarious', 'log_income']),
        (municipalities, 'municipality', 'dengue_2024', ['no_garbage', 'precarious', 'log_income']),
        (districts, 'district', 'teen', ['crowded', 'precarious', 'log_income']),
    ]:
        model, rows = expected_model(areas, outcome, covariates, scale)
        models.append(model)
        expected += rows

    for scale, areas in (('municipality', municipalities), ('district', districts)):
        for a in areas:
            a['rates'] = {o: round(a['lepto_eb'] if o == 'lepto' else outcome_value(a, o), 3) for o in a['cases']}
            if 'lepto' in a['cases']:
                a['rates']['lepto_raw'] = round(outcome_value(a, 'lepto'), 3)
            for k in ('precarious', 'no_garbage', 'crowded', 'near', 'income'):
                a[k] = round(a[k], 2) if a[k] is not None else None
            a.pop('log_income', None)
            a.pop('lepto_eb', None)

    tracts = load_tracts()
    groups = defaultdict(list)
    for t in tracts:
        groups[t['municipality']].append(t)
    xbar = sum(t['x'] * t['pop'] for t in tracts) / sum(t['pop'] for t in tracts)
    others = {a['code']: a['cases']['tb'] for a in municipalities if a['code'] != SAO_PAULO}
    b, _, weight = fit_aggregate_model(groups, others, xbar)
    scale_transfer = transfer(tracts, {a['code']: {'cases': a['cases']['tb'], 'pop': a['population']} for a in districts},
                              others, b, weight)

    (ROOT / 'public' / 'data').mkdir(exist_ok=True)
    json.dump({'years': YEARS, 'crowded_threshold': CROWDED, 'determinants': DETERMINANTS, 'pairs': pairs,
               'models': models, 'expected': expected, 'scale_transfer': scale_transfer,
               'municipalities': municipalities, 'districts': districts},
              open(ROOT / 'public' / 'data' / 'relations.json', 'w'), ensure_ascii=False)
    with open(ROOT / 'data' / 'outcome_expected.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(expected[0]))
        w.writeheader()
        w.writerows(expected)

    for p in pairs:
        stat = 'no variation after smoothing' if p['rho'] is None else \
            f"rho {p['rho']:+.2f} [{p['ci'][0]:+.2f}, {p['ci'][1]:+.2f}]"
        print(f"{p['scale']:12s} {p['outcome']:12s} ~ {p['determinant']:10s} {stat} n={p['n']}")
    for m in models:
        print(f"model {m['scale']:12s} {m['outcome']:12s} deviance explained {m['deviance_explained']:.2f}, "
              f"dispersion {m['dispersion']}, RR/SD {m['rate_ratio_per_sd']}, flagged {m['flagged']}"
              f"{'' if m['used_for_flags'] else ' (not used)'}")
    for e in expected:
        if e['flag']:
            print(f"  {e['scale']} {e['outcome']} {e['name']}: observed {e['observed']:.0f}, expected {e['expected']:.0f} "
                  f"[{e['lower']:.0f}, {e['upper']:.0f}] -> {e['flag']}")


if __name__ == '__main__':
    main()
