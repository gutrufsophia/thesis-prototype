"""Territorial typology of the 1 km surroundings of every mapped facility (geodemographic
classification; Singleton & Spielman 2014).

k-means with k-means++ seeding (Arthur & Vassilvitskii 2007), 10 restarts with a fixed seed, on
standardised variables. k is chosen by the mean silhouette (Rousseeuw 1987) on a fixed sample.
Clusters are numbered by mean income, poorest first, so the numbering is stable.

Usage: python3 -I analysis/typology.py [k]   (without k: report silhouettes and use the best)
Writes data/surroundings_types.csv, and each type's mean profile to public/data/typology.json for
the facility page.
"""
import csv
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261025
AREA_KM2 = math.pi  # 1 km radius
VARIABLES = {
    'precarious': lambda r: float(r['precarious_pct']),
    'off_network': lambda r: 100 - float(r['sewage_pct']),
    'no_garbage': lambda r: 100 - float(r['garbage_pct']),
    'crowded': lambda r: float(r['crowded_pct']),
    'far_primary': lambda r: float(r['far_primary_pct']),
    'log_income': lambda r: math.log(float(r['income'])),
    'log_density': lambda r: math.log(max(float(r['population']), 1) / AREA_KM2),
}


def load():
    rows, values = [], []
    for r in csv.DictReader(open(ROOT / 'data' / 'surroundings_1000.csv')):
        try:
            v = [f(r) for f in VARIABLES.values()]
        except (ValueError, TypeError):
            continue
        rows.append(r)
        values.append(v)
    means = [sum(c) / len(c) for c in zip(*values)]
    sds = [math.sqrt(sum((x - m) ** 2 for x in c) / (len(c) - 1)) for c, m in zip(zip(*values), means)]
    z = [[(x - m) / s for x, m, s in zip(v, means, sds)] for v in values]
    return rows, values, z


def dist2(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b))


def kmeans(points, k, rng, iterations=100):
    centres = [rng.choice(points)]
    while len(centres) < k:
        weights = [min(dist2(p, c) for c in centres) for p in points]
        pick = rng.random() * sum(weights)
        acc = 0.0
        for p, w in zip(points, weights):
            acc += w
            if acc >= pick:
                centres.append(p)
                break
    labels = [0] * len(points)
    for _ in range(iterations):
        new = [min(range(k), key=lambda j: dist2(p, centres[j])) for p in points]
        if new == labels and _ > 0:
            break
        labels = new
        for j in range(k):
            members = [p for p, l in zip(points, labels) if l == j]
            if members:
                centres[j] = [sum(c) / len(members) for c in zip(*members)]
    inertia = sum(dist2(p, centres[l]) for p, l in zip(points, labels))
    return labels, centres, inertia


def best_of(points, k, restarts=10):
    rng = random.Random(SEED + k)
    return min((kmeans(points, k, rng) for _ in range(restarts)), key=lambda r: r[2])


def silhouette(points, labels, sample):
    total = 0.0
    for i in sample:
        own = [math.sqrt(dist2(points[i], points[j])) for j in sample if j != i and labels[j] == labels[i]]
        if not own:
            continue
        a = sum(own) / len(own)
        b = min(sum(math.sqrt(dist2(points[i], points[j])) for j in sample if labels[j] == c) /
                max(1, sum(1 for j in sample if labels[j] == c))
                for c in set(labels) if c != labels[i])
        total += (b - a) / max(a, b)
    return total / len(sample)


def main():
    rows, raw, z = load()
    sample = random.Random(SEED).sample(range(len(z)), 1200)
    if len(sys.argv) > 1:
        k = int(sys.argv[1])
    else:
        scores = {}
        for k in range(3, 9):
            labels, _, _ = best_of(z, k)
            scores[k] = silhouette(z, labels, sample)
            print(f'k={k}: mean silhouette {scores[k]:.3f}')
        k = max(scores, key=scores.get)
    labels, centres, _ = best_of(z, k)
    quality = silhouette(z, labels, sample)

    names = list(VARIABLES)
    income = names.index('log_income')
    order = sorted(range(k), key=lambda j: centres[j][income])
    renumber = {old: new + 1 for new, old in enumerate(order)}
    with open(ROOT / 'data' / 'surroundings_types.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['cnes', 'territory_type'])
        for r, l in zip(rows, labels):
            w.writerow([r['cnes'], renumber[l]])

    print(f'k = {k}; {len(rows)} facilities classified')
    profiles = []
    for old in order:
        members = [v for v, l in zip(raw, labels) if l == old]
        mean = {n: sum(v[i] for v in members) / len(members) for i, n in enumerate(names)}
        profile = {'type': renumber[old], 'facilities': len(members),
                   'z': {n: round(c, 2) for n, c in zip(names, centres[old])},
                   'mean': {**{n: round(mean[n], 1) for n in names if not n.startswith('log_')},
                            'income': round(math.exp(mean['log_income'])),
                            'density_per_km2': round(math.exp(mean['log_density']))}}
        profiles.append(profile)
        print(json.dumps(profile, ensure_ascii=False))
    out = {'k': k, 'silhouette': round(quality, 3), 'facilities': len(rows), 'variables': names, 'types': profiles}
    (ROOT / 'public' / 'data' / 'typology.json').write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n')


if __name__ == '__main__':
    main()
