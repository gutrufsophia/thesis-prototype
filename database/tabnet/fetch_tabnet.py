"""Download the project's TabNet tabulations (DATASUS and SMS-SP) into database/tabnet/raw.

Usage:
    python3 -I database/tabnet/fetch_tabnet.py            # every query
    python3 -I database/tabnet/fetch_tabnet.py tb_res     # one query
"""
import datetime
import html
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / 'raw'

DATASUS = 'http://tabnet.datasus.gov.br/cgi/deftohtm.exe?'
DATASUS_TB = DATASUS + 'sinannet/cnv/tubercsp.def'
DATASUS_SINASC = DATASUS + 'sinasc/cnv/nvsp.def'
DATASUS_SIM = DATASUS + 'sim/cnv/obt10sp.def'
SMS = 'https://tabnet.saude.prefeitura.sp.gov.br/cgi/deftohtm3.exe?secretarias/saude/TABNET/'
SMS_TB = SMS + 'TBWEB/TBWEB.def'
SMS_SIM = SMS + 'sim/obito.def'
SMS_SINASC = SMS + 'sinasc/nascido.def'

YEARS_22_24 = ['2024', '2023', '2022']
AGES_30_69 = ['30 a 39 anos', '40 a 49 anos', '50 a 59 anos', '60 a 69 anos']
SMS_AGES_30_69 = ['30 - 39', '40 - 49', '50 - 59', '60 - 69']

# name: (form, row, column, files, {filter: [labels]}, increment or None for the form's default).
# Everything is matched by the label shown on the form, ignoring accents and case.
QUERIES = {
    'tb_notif': (DATASUS_TB, 'Município de notificação', 'Ano Diagnóstico',
                 ['2025', '2024', '2023', '2022'], {}, None),
    'tb_res': (DATASUS_TB, 'Município de residência', 'Ano Diagnóstico',
               ['2025', '2024', '2023', '2022'], {}, None),
    'nasc_idade_res': (DATASUS_SINASC, 'Município', 'Idade da mãe', YEARS_22_24, {}, 'Nascim p/resid.mãe'),
    'nasc_gestacao_res': (DATASUS_SINASC, 'Município', 'Duração gestação', YEARS_22_24, {}, 'Nascim p/resid.mãe'),
    'obitos_30a69_res': (DATASUS_SIM, 'Município', 'Capítulo CID-10', YEARS_22_24,
                         {'Faixa Etária': AGES_30_69}, 'Óbitos p/Residênc'),

    # TBWEB at SMS-SP only holds cases attended in the city, so it is used for city residents only.
    'sp_tb_dist': (SMS_TB, 'Distrito Administ(Res)', 'Ano incidência', ['2026'],
                   {'Município de residência': ['SAO PAULO']}, None),
    'sp_tb_dist_endereco': (SMS_TB, 'Distrito Administ(Res)', 'Tipo de Endereço', ['2026'],
                            {'Município de residência': ['SAO PAULO'],
                             'Ano incidência': ['2022', '2023', '2024', '2025']}, None),
    'sp_nasc_idade_dist': (SMS_SINASC, 'Distrito Administ. residência', 'Faixa etária mãe', YEARS_22_24,
                           {}, 'NV parturientes residentes MSP'),
    'sp_nasc_gestacao_dist': (SMS_SINASC, 'Distrito Administ. residência', 'Duração gestação', YEARS_22_24,
                              {}, 'NV parturientes residentes MSP'),
    'sp_obitos_30a69_dist': (SMS_SIM, 'Distrito Admin residência', 'Causa(Cap CID10)', YEARS_22_24,
                             {'Faixa Etária (13)': SMS_AGES_30_69}, 'Óbitos Residentes MSP'),

    # Cross-checks between the city and the national systems.
    'sp_nasc_ano': (SMS_SINASC, 'Ano nascimento', 'Não ativa', ['2026', '2025'] + YEARS_22_24,
                    {}, 'NV parturientes residentes MSP'),
    'nasc_ano_res': (DATASUS_SINASC, 'Município', 'Ano do nascimento', ['2026', '2025'] + YEARS_22_24,
                     {}, 'Nascim p/resid.mãe'),
    'sp_obitos_30a69_ano': (SMS_SIM, 'Ano do Óbito', 'Não ativa', YEARS_22_24,
                            {'Faixa Etária (13)': SMS_AGES_30_69}, 'Óbitos Residentes MSP'),
    'obitos_30a69_ano_res': (DATASUS_SIM, 'Município', 'Ano do Óbito', ['2026', '2025'] + YEARS_22_24,
                             {'Faixa Etária': AGES_30_69}, 'Óbitos p/Residênc'),
    'sp_obitos_30a69_cap_ano': (SMS_SIM, 'Causa(Cap CID10)', 'Ano do Óbito', YEARS_22_24,
                                {'Faixa Etária (13)': SMS_AGES_30_69}, 'Óbitos Residentes MSP'),
    'obitos_30a69_cap_ano_sp': (DATASUS_SIM, 'Capítulo CID-10', 'Ano do Óbito', YEARS_22_24,
                                {'Faixa Etária': AGES_30_69, 'Município': ['355030 SAO PAULO']},
                                'Óbitos p/Residênc'),
}


def norm(text):
    text = unicodedata.normalize('NFKD', html.unescape(text)).encode('ascii', 'ignore').decode()
    return ' '.join(text.lower().split())


def fetch(url, data=None):
    req = urllib.request.Request(url, data=data, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read().decode('latin-1')


def parse_form(page):
    action = re.search(r'<form[^>]*action="?([^"\s>]+)', page, re.I).group(1)
    selects = {}
    for m in re.finditer(r'<select[^>]*name="?([^"\s>]+)"?[^>]*>(.*?)</select>', page, re.S | re.I):
        opts = re.findall(r'<option[^>]*value="?([^">]*)"?[^>]*>([^<]*)', m.group(2), re.I)
        selects[m.group(1)] = [(v, html.unescape(t).strip()) for v, t in opts]
    return action, selects


def pick(options, label, what):
    for value, text in options:
        if norm(text) == norm(label):
            return value
    raise SystemExit(f'{what}: no option labelled {label!r}')


def run(name):
    form_url, row, col, files, filters, increment = QUERIES[name]
    action, selects = parse_form(fetch(form_url))
    pairs = [('Linha', pick(selects['Linha'], row, 'row')),
             ('Coluna', pick(selects['Coluna'], col, 'column')),
             ('Incremento', pick(selects['Incremento'], increment, 'increment') if increment
              else selects['Incremento'][0][0])]
    pairs += [('Arquivos', pick(selects['Arquivos'], f, 'file')) for f in files]

    # Filter fields are named "S" + the variable name with underscores, e.g. SFaixa_Etária.
    # TabNet expects every one of them in the POST, so the unfiltered ones get "all categories".
    by_label = {norm(k[1:].replace('_', ' ')): k for k in selects if k.startswith('S')}
    chosen = {}
    for field, labels in filters.items():
        key = by_label.get(norm(field))
        if not key:
            raise SystemExit(f'filter field {field!r} not found')
        chosen[key] = [pick(selects[key], label, field) for label in labels]
    for key in selects:
        if key.startswith('S'):
            pairs += [(key, v) for v in chosen.get(key, ['TODAS_AS_CATEGORIAS__'])]
    pairs += [('formato', 'prn'), ('mostre', 'Mostra')]

    base = re.match(r'https?://[^/]+', form_url).group(0)
    page = fetch(base + action, urllib.parse.urlencode(pairs, encoding='latin-1').encode())
    pre = re.search(r'<PRE>(.*?)</PRE>', page, re.S | re.I)
    if not pre:
        raise SystemExit(f'{name}: no table in the response:\n' + re.sub(r'<[^>]+>', ' ', page)[:2000])
    table = html.unescape(pre.group(1)).strip()
    notes = [' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', n)).split())
             for n in re.findall(r'(?:Fonte|Nota|Notas|Dados)[^<]{0,400}', page)]

    header = [f'# query: {name}', f'# form: {form_url}', f'# row: {row} | column: {col}',
              f'# increment: {increment or selects["Incremento"][0][1]}', f'# files: {", ".join(files)}',
              f'# filters: {filters or "none"}', f'# downloaded: {datetime.date.today().isoformat()}']
    header += [f'# note: {n}' for n in notes if n]
    OUT.mkdir(exist_ok=True)
    path = OUT / f'{name}.csv'
    path.write_text('\n'.join(header) + '\n' + table + '\n', encoding='utf-8')
    print(f'{name}: {table.count(chr(10))} lines -> {path}')


if __name__ == '__main__':
    for name in sys.argv[1:] or QUERIES:
        run(name)
