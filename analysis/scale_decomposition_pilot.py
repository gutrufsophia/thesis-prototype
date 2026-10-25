"""How much of the tract-level variation in sanitation and crowding lies between RMSP municipalities.

Usage: python3 -I analysis/scale_decomposition_pilot.py dados_censo_culturaeduca.csv
"""
import csv
import sys
from collections import defaultdict

SAO_PAULO = '3550308'


def number(value):
    return float(value) if value not in ('', 'nan', 'NaN') else None


def between_share(values):
    """Weighted share of variance between groups; values are (group, x, weight)."""
    total_w = sum(w for _, _, w in values)
    mean = sum(x * w for _, x, w in values) / total_w
    total = sum(w * (x - mean) ** 2 for _, x, w in values)
    groups = defaultdict(lambda: [0.0, 0.0])
    for group, x, w in values:
        groups[group][0] += w
        groups[group][1] += x * w
    between = sum(w * (s / w - mean) ** 2 for w, s in groups.values())
    return mean, between / total


def main(path):
    with open(path, encoding='utf-8') as f:
        tracts = [{
            'mun': r['cd_municipio'],
            'reported': number(r['domicilios_esgoto_informado']),
            'precarious': number(r['esgoto_precario']),
            'network': number(r['esgoto_rede_geral']),
            'crowding': number(r['media_moradores_domicilio']),
            'households': number(r['total_domicilios_ocupados']),
        } for r in csv.DictReader(f)]
    sewage = [t for t in tracts if t['reported'] and t['precarious'] is not None]

    indicators = {
        'precarious sewage share': [(t['mun'], t['precarious'] / t['reported'], t['reported']) for t in sewage],
        'not on network share': [(t['mun'], 1 - t['network'] / t['reported'], t['reported'])
                                 for t in sewage if t['network'] is not None],
        'residents per household': [(t['mun'], t['crowding'], t['households'])
                                    for t in tracts if t['crowding'] and t['households']],
    }
    for name, values in indicators.items():
        mean, between = between_share(values)
        print(f'{name}: tracts={len(values)} weighted mean={mean:.4f} '
              f'between municipalities={between:.3f} within={1 - between:.3f}')

    municipal = defaultdict(lambda: [0.0, 0.0])
    for t in sewage:
        municipal[t['mun']][0] += t['precarious']
        municipal[t['mun']][1] += t['reported']
    rate = {mun: p / r for mun, (p, r) in municipal.items()}

    flagged = [t for t in sewage
               if t['precarious'] / t['reported'] >= 2 * rate[t['mun']]
               and t['precarious'] / t['reported'] - rate[t['mun']] >= 0.10]
    households = sum(t['reported'] for t in sewage)
    in_flagged = sum(t['reported'] for t in flagged)
    print(f'households in tracts at least 2x and 10 pp above their municipality (precarious sewage): '
          f'{in_flagged:.0f} of {households:.0f} ({in_flagged / households:.2%}), tracts={len(flagged)}')

    sp = sorted(t['precarious'] / t['reported'] for t in sewage if t['mun'] == SAO_PAULO)
    quantile = lambda q: sp[int(q * (len(sp) - 1))]
    print(f'São Paulo city: municipal share={rate[SAO_PAULO]:.4f}; tract p50={quantile(.5):.4f} '
          f'p90={quantile(.9):.4f} p99={quantile(.99):.4f}; tracts={len(sp)}')


if __name__ == '__main__':
    main(sys.argv[1])
