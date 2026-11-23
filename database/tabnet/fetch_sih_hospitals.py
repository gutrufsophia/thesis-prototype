"""SUS admissions and in-hospital deaths of each RMSP hospital by diagnosis group (the 300-odd
groups of the ICD-10 morbidity list), age group and admission type (elective or not), for the case
mix adjustment of database/reference/compute_hospital_mortality.py.

TabNet tabulates two variables at a time, so each hospital takes four queries: admissions and
deaths, elective and non-elective, each a morbidity group x age group table filtered to that
hospital. Same period and source as fetch_tabnet.py's SIH queries (by place of admission, months
of processing Jan/2025 to Jul/2026). Files already downloaded are skipped, so the run can resume.

    python3 database/tabnet/fetch_sih_hospitals.py [HOSPITALS.csv]

The hospitals are those of the facility table (general, specialised, mixed units) with SUS admissions
in raw/sih_internacoes_cap.csv, or the `cnes` column of HOSPITALS.csv when given.
"""

import csv
import html
import re
import sys
import time
import urllib.parse
from pathlib import Path

import fetch_tabnet as ft

OUT = ft.OUT / 'sih_hospitals'
INCREMENTS = {'adm': 'Internações', 'obt': 'Óbitos'}
NON_ELECTIVE = ['Urgência', 'Acidente no local trabalho ou a serv da empresa', 'Acidente no trajeto para o trabalho',
                'Outros tipo de acidente de trânsito', 'Out tp lesões e envenen por agent quím físicos']


def query(action, selects, cnes, increment, admission_types):
    est = next((v for v, t in selects['SEstabelecimento'] if t.startswith(f'{cnes:07d} ')), None)
    if est is None:
        return None
    pairs = [('Linha', ft.pick(selects['Linha'], 'Lista Morb  CID-10', 'row')),
             ('Coluna', ft.pick(selects['Coluna'], 'Faixa Etária 1', 'column')),
             ('Incremento', ft.pick(selects['Incremento'], increment, 'increment'))]
    pairs += [('Arquivos', ft.pick(selects['Arquivos'], f, 'file')) for f in ft.SIH_MONTHS]
    chosen = {'SEstabelecimento': [est],
              'SCaráter_atendimento': [ft.pick(selects['SCaráter_atendimento'], t, 'type') for t in admission_types]}
    for key in selects:
        if key.startswith('S'):
            pairs += [(key, v) for v in chosen.get(key, ['TODAS_AS_CATEGORIAS__'])]
    pairs += [('formato', 'prn'), ('mostre', 'Mostra')]
    page = ft.fetch('http://tabnet.datasus.gov.br' + action, urllib.parse.urlencode(pairs, encoding='latin-1').encode())
    pre = re.search(r'<PRE>(.*?)</PRE>', page, re.S | re.I)
    if pre:
        return html.unescape(pre.group(1)).strip()
    if 'Nenhum registro' in page or 'nenhum registro' in page.lower():
        return ''
    raise RuntimeError(f'{cnes} {increment}: no table in the response')


HOSPITAL_TYPES = ('Hospital Geral', 'Hospital Especializado', 'Unidade Mista')


def hospitals_with_admissions():
    import psycopg2
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'seeders'))
    from seed import read_env
    lines = [l for l in (ft.OUT / 'sih_internacoes_cap.csv').read_text(encoding='utf-8').splitlines() if not l.startswith('#')]
    with_admissions = {int(r[0][:7]) for r in csv.reader(lines[1:], delimiter=';') if r and r[0][:7].isdigit() and r[-1] not in ('-', '0')}
    url = read_env(Path(__file__).resolve().parents[2] / '.env')['DATABASE_URL']
    with psycopg2.connect(url) as conn, conn.cursor() as cur:
        cur.execute('select "CO_CNES" from infraestrutura_saude where tipo_equipamento = any(%s)', (list(HOSPITAL_TYPES),))
        return sorted(c for (c,) in cur.fetchall() if c in with_admissions)


def main():
    hospitals = [int(r['cnes']) for r in csv.DictReader(open(sys.argv[1]))] if len(sys.argv) > 1 else hospitals_with_admissions()
    action, selects = ft.parse_form(ft.fetch(ft.DATASUS_SIH))
    OUT.mkdir(parents=True, exist_ok=True)
    for n, cnes in enumerate(hospitals, 1):
        for inc_key, increment in INCREMENTS.items():
            for type_key, types in (('ele', ['Eletivo']), ('urg', NON_ELECTIVE)):
                path = OUT / f'{cnes}_{inc_key}_{type_key}.csv'
                if path.exists():
                    continue
                for attempt in range(3):
                    try:
                        table = query(action, selects, cnes, increment, types)
                        break
                    except Exception as error:  # TabNet drops connections now and then
                        if attempt == 2:
                            raise
                        print(f'{cnes} {inc_key} {type_key}: {error}; retrying', flush=True)
                        time.sleep(10)
                if table is None:
                    print(f'{cnes}: not in the TabNet list of establishments', flush=True)
                    continue
                tmp = path.with_suffix('.tmp')
                tmp.write_text(table + '\n', encoding='utf-8')
                tmp.rename(path)
                time.sleep(1)
        print(f'[{n}/{len(hospitals)}] {cnes}', flush=True)


if __name__ == '__main__':
    main()
