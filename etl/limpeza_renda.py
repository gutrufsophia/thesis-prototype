"""Renda dos responsáveis por setor censitário (Censo 2022) para os setores da RMSP.

Fonte: IBGE, Agregados por setores censitários, rendimento do responsável (publicado em
08/05/2026), arquivo Agregados_por_setores_renda_responsavel_BR_20260508_csv.zip.
V06001: responsáveis em domicílios particulares permanentes ocupados.
V06004 / V06006: rendimento nominal médio / mediano mensal dos responsáveis COM rendimento.
Células suprimidas ("X") ficam vazias.

Uso: python3 -I etl/limpeza_renda.py CAMINHO_DO_ZIP
"""
import csv
import io
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ARQUIVO = 'Agregados_por_setores_renda_responsavel_BR.csv'


def numero(valor):
    try:
        return float(valor)
    except ValueError:
        return None


def main(caminho_zip):
    setores_rmsp = {r['cd_setor'] for r in csv.DictReader(open(RAIZ / 'data' / 'dados_censo_culturaeduca.csv'))}
    saida = RAIZ / 'data' / 'renda_responsavel_rmsp.csv'
    encontrados = suprimidos = 0
    with zipfile.ZipFile(caminho_zip) as z, z.open(ARQUIVO) as f, open(saida, 'w', newline='') as out:
        escritor = csv.writer(out)
        escritor.writerow(['cd_setor', 'responsaveis', 'renda_media_responsavel', 'renda_mediana_responsavel'])
        for r in csv.DictReader(io.TextIOWrapper(f, encoding='utf-8'), delimiter=';'):
            if r['CD_SETOR'] not in setores_rmsp:
                continue
            encontrados += 1
            media, mediana = numero(r['V06004']), numero(r['V06006'])
            if media is None:
                suprimidos += 1
            escritor.writerow([r['CD_SETOR'], numero(r['V06001']), media, mediana])
    print(f'{encontrados} de {len(setores_rmsp)} setores da RMSP; {suprimidos} sem renda publicada -> {saida.name}')


if __name__ == '__main__':
    main(sys.argv[1])
