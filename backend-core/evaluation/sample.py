"""Draw the held-out evaluation sample: facilities stratified by the situations the caveat rules
are about, with a fixed seed, excluding the four facilities used while developing the rules.

Usage: python3 -I backend-core/evaluation/sample.py   (reads SUPABASE_URL and SUPABASE_ANON_KEY)
Writes backend-core/evaluation/sample.csv.
"""
import csv
import json
import os
import random
import urllib.request
from pathlib import Path

SEED = 20261025
PER_STRATUM = 5
DEVELOPMENT = {9840559, 2078015, 2786826, 9156844}
SAO_PAULO = 355030
HOSPITALS = {'Hospital Geral', 'Hospital Especializado', 'Unidade Mista'}
PRIMARY_CARE = {'Centro de Saúde/UBS', 'Posto de Saúde'}
# Municipalities where more than 10% of deaths at ages 30-69 have no defined cause (monograph log, 2026-10-25)
HIGH_ILL_DEFINED = {353980, 352310, 350660, 351570, 351830}

URL = os.environ['SUPABASE_URL'].rstrip('/')
KEY = os.environ['SUPABASE_ANON_KEY']


def get(path):
    req = urllib.request.Request(f'{URL}/rest/v1/{path}', headers={'apikey': KEY, 'Authorization': f'Bearer {KEY}'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def all_facilities():
    columns = 'CO_CNES,tipo_equipamento,rede_sus,coord_source,coord_shift_m,LEITOS_EXISTENTES,CO_MUNICIPIO_GESTOR'
    rows, offset = [], 0
    while True:
        page = get(f'infraestrutura_saude?select={columns}&coord=not.is.null&order=CO_CNES&limit=1000&offset={offset}')
        rows += page
        if len(page) < 1000:
            return rows
        offset += 1000


def main():
    req = urllib.request.Request(f'{URL}/rest/v1/rpc/municipal_indicators', data=b'{}', method='POST',
                                 headers={'apikey': KEY, 'Authorization': f'Bearer {KEY}',
                                          'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        population = {int(m['cd_municipio6']): m['populacao'] for m in json.load(r)}
    small = {code for code, pop in population.items() if pop < 50000}

    facilities = [f for f in all_facilities() if f['CO_CNES'] not in DEVELOPMENT]
    strata = {
        'primary_care_sao_paulo': lambda f: f['tipo_equipamento'] in PRIMARY_CARE and f['rede_sus']
        and f['CO_MUNICIPIO_GESTOR'] == SAO_PAULO,
        'primary_care_elsewhere': lambda f: f['tipo_equipamento'] in PRIMARY_CARE and f['rede_sus']
        and f['CO_MUNICIPIO_GESTOR'] != SAO_PAULO,
        'large_hospital': lambda f: f['tipo_equipamento'] in HOSPITALS and (f['LEITOS_EXISTENTES'] or 0) >= 50,
        'private_without_sus': lambda f: not f['rede_sus'],
        'approximate_position': lambda f: f['coord_source'] in ('cnefe_street', 'cnefe_cep'),
        'corrected_position': lambda f: f['coord_source'] == 'cnefe_corrected' and (f['coord_shift_m'] or 0) >= 500,
        'small_municipality': lambda f: f['CO_MUNICIPIO_GESTOR'] in small,
        'many_ill_defined_deaths': lambda f: f['CO_MUNICIPIO_GESTOR'] in HIGH_ILL_DEFINED,
    }
    rng = random.Random(SEED)
    chosen, taken = [], set()
    for name, test in strata.items():
        pool = sorted(f['CO_CNES'] for f in facilities if test(f) and f['CO_CNES'] not in taken)
        picked = rng.sample(pool, min(PER_STRATUM, len(pool)))
        taken.update(picked)
        chosen += [(cnes, name, len(pool)) for cnes in picked]
        print(f'{name}: {len(pool)} eligible, {len(picked)} drawn')

    out = Path(__file__).resolve().parent / 'sample.csv'
    with open(out, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['cnes', 'stratum', 'stratum_size'])
        writer.writerows(chosen)
    print(f'{len(chosen)} facilities -> {out}')


if __name__ == '__main__':
    main()
