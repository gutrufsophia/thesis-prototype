"""Build indicadores_distrito_sp.csv: outcomes and census factors for São Paulo city's 96 districts.

Reads the SMS-SP exports in database/tabnet/raw (run fetch_tabnet.py first). Column definitions
match limpeza_datasus.py.

Usage: python3 -I database/tabnet/build_district_indicators.py
"""
import csv
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RAW = HERE / 'raw'
ROMAN = ['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x', 'xi', 'xii', 'xiii', 'xiv',
         'xv', 'xvi', 'xvii', 'xviii', 'xix', 'xx', 'xxi', 'xxii']
UNASSIGNED = {'EM BRANCO', 'IGNORADO', 'DESCONHECIDO'}
# TBWEB has no "SOCORRO" row; it labels that district with its subprefecture's name.
ALIASES = {'CAPELA DO SOCORRO': 'SOCORRO'}
CENSUS = ['populacao_total', 'total_domicilios_ocupados', 'esgoto_rede_geral', 'esgoto_precario',
          'domicilios_esgoto_informado', 'total_lixo_coletado', 'domicilios_lixo_informado']


def norm(name):
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    return ' '.join(name.upper().replace("'", ' ').split())


def number(value):
    return float(value) if value not in ('', 'nan') else None


def read_tabnet(name):
    lines = [l for l in (RAW / f'{name}.csv').read_text(encoding='utf-8').splitlines()
             if l and not l.startswith('#')]
    columns = [c.strip('"') for c in lines[0].split(';')][1:]
    rows = {}
    for line in lines[1:]:
        cells = line.split(';')
        label = norm(cells[0].strip('"'))
        if label == 'TOTAL':
            break
        rows[ALIASES.get(label, label)] = [0 if v.strip() in ('-', '') else int(v) for v in cells[1:]]
    return columns, rows


def attach(districts, name, build):
    columns, rows = read_tabnet(name)
    unknown = sorted(set(rows) - set(districts) - UNASSIGNED)
    if unknown:
        raise SystemExit(f'{name}: district names not in the IBGE list: {unknown}')
    for key, district in districts.items():
        district.update(build(dict(zip(columns, rows.get(key, [0] * len(columns))))))
    unassigned = {k: rows[k][-1] for k in UNASSIGNED & set(rows)}
    print(f'{name}: without district {unassigned or 0}')


def deaths(v):
    out = {'obitos_total': v['Total']}
    for label, count in v.items():
        if label.startswith('Cap '):
            out['obitos_cap_' + ROMAN[int(label[4:]) - 1]] = count
    return out


def add_census(by_code):
    for d in by_code.values():
        d.update({k: 0.0 for k in CENSUS}, tracts=0, residents=0.0)
    with open(ROOT / 'dados_censo_culturaeduca.csv', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            # The tract code starts with the district code (UF + municipality + district, 9 digits).
            d = by_code.get(r['cd_setor'][:9])
            if d is None:
                continue
            d['tracts'] += 1
            for k in CENSUS:
                d[k] += number(r[k]) or 0.0
            mean, households = number(r['media_moradores_domicilio']), number(r['total_domicilios_ocupados'])
            if mean and households:
                d['residents'] += mean * households
    for d in by_code.values():
        residents = d.pop('residents')
        households = d['total_domicilios_ocupados']
        d['media_moradores_domicilio'] = round(residents / households, 3) if households else None
        for k in CENSUS:
            d[k] = round(d[k], 1)


def main():
    with open(HERE / 'sp_districts.csv', encoding='utf-8') as f:
        districts = {norm(r['nm_dist']): dict(r) for r in csv.DictReader(f)}

    attach(districts, 'sp_tb_dist', lambda v: {f'tb_{y}': v[y] for y in ('2022', '2023', '2024', '2025')})
    attach(districts, 'sp_nasc_idade_dist', lambda v: {
        'nasc_total': v['Total'],
        'nasc_idade_conhecida': v['Total'] - v.get('Nao informado', 0),
        'nasc_mae_menor_20': v['10 a 14'] + v['15 a 19'],
    })
    attach(districts, 'sp_nasc_gestacao_dist', lambda v: {
        'nasc_gestacao_conhecida': v['Total'] - v['Ignorado'],
        'nasc_pretermo': v['< 22 semanas'] + v['22-27 semanas'] + v['28-31 semanas'] + v['32-36 semanas'],
    })
    attach(districts, 'sp_obitos_30a69_dist', deaths)

    by_code = {d['cd_dist']: d for d in districts.values()}
    add_census(by_code)

    sample = next(iter(by_code.values()))
    fields = ['cd_dist', 'nm_dist', 'tracts'] + CENSUS + ['media_moradores_domicilio'] + \
             [k for k in sample if k.startswith(('tb_', 'nasc_', 'obitos_'))]
    out = ROOT / 'indicadores_distrito_sp.csv'
    with open(out, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(by_code.values(), key=lambda d: d['cd_dist']))
    population = sum(d['populacao_total'] for d in by_code.values())
    print(f'{out.name}: {len(by_code)} districts, {sum(d["tracts"] for d in by_code.values())} tracts, '
          f'population {population:,.0f}')


if __name__ == '__main__':
    main()
