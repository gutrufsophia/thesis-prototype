import re

import pandas as pd

print("Iniciando o ETL dos indicadores municipais (DATASUS/TabNet) - RMSP...")

# =====================================================================
# 0. CONFIGURAÇÕES INICIAIS
# =====================================================================
# Mesma lista de limpeza.py (códigos IBGE de 6 dígitos, como o TabNet usa)
rmsp_ibge6 = [
    '350390', '350570', '350660', '350900', '350920', '351060', '351300',
    '351380', '351500', '351510', '351570', '351630', '351640', '351830',
    '351880', '352220', '352250', '352310', '352500', '352620', '352850',
    '352940', '353060', '353440', '353980', '353910', '354330', '354410',
    '354500', '354680', '354730', '354780', '354870', '354880', '354995',
    '355030', '355250', '355280', '355645'
]

PASTA = '/home/sophia/Downloads/'
ARQ_DENGUE = PASTA + 'sinannet_cnv_denguebsp180054191_181_56_142.csv'
ARQ_LEPTO = PASTA + 'sinannet_cnv_leptosp132731191_181_56_142.csv'
ARQ_TUBERCULOSE = PASTA + 'sinannet_cnv_tubercsp140656191_181_56_142.csv'
ARQ_NASC_IDADE_MAE = PASTA + 'sinasc_cnv_nvsp142026191_181_56_142.csv'   # por residência da mãe
ARQ_NASC_GESTACAO = PASTA + 'sinasc_cnv_nvsp142000191_181_56_142.csv'    # por residência da mãe
ARQ_OBITOS = PASTA + 'sim_cnv_obt10sp142208191_181_56_142.csv'           # 30 a 69 anos, por residência


# =====================================================================
# 1. LEITOR GENÉRICO DE EXPORTAÇÕES DO TABNET
# =====================================================================
def ler_tabnet(caminho):
    """Lê um CSV do TabNet (cabeçalho e rodapé de texto livre) e devolve só a RMSP,
    indexada pelo código IBGE de 6 dígitos."""
    with open(caminho, encoding='latin-1') as f:
        linhas = f.read().splitlines()
    inicio = next(i for i, linha in enumerate(linhas) if linha.startswith('"Munic'))
    fim = next(i for i, linha in enumerate(linhas) if linha.startswith('"Total"'))
    colunas = [c.strip('"') for c in linhas[inicio].split(';')]
    registros = []
    for linha in linhas[inicio + 1:fim]:
        campos = linha.split(';')
        codigo = re.match(r'"(\d{6}) ', campos[0])
        if not codigo:
            continue  # "MUNICIPIO IGNORADO"
        # "-" significa zero no TabNet
        valores = [0 if v.strip() == '-' else int(v) for v in campos[1:]]
        registros.append([codigo.group(1)] + valores)
    df = pd.DataFrame(registros, columns=['cd_municipio6'] + colunas[1:]).set_index('cd_municipio6')
    # municípios sem nenhuma ocorrência não aparecem na exportação: entram como zero
    return df.reindex(rmsp_ibge6).fillna(0).astype(int)


final = pd.DataFrame(index=pd.Index(rmsp_ibge6, name='cd_municipio6'))

# =====================================================================
# 2. SINAN: Dengue, Leptospirose e Tuberculose (casos por ano)
# =====================================================================
print("Processando SINAN...")
dengue = ler_tabnet(ARQ_DENGUE)
lepto = ler_tabnet(ARQ_LEPTO)
tuberculose = ler_tabnet(ARQ_TUBERCULOSE)

for ano in ['2022', '2023', '2024', '2025', '2026']:
    final[f'dengue_{ano}'] = dengue[ano]            # casos prováveis, por residência
    final[f'lepto_{ano}'] = lepto[ano]              # casos confirmados, por residência
for ano in ['2022', '2023', '2024', '2025']:
    final[f'tuberculose_{ano}'] = tuberculose[ano]  # casos confirmados, por município de NOTIFICAÇÃO

# =====================================================================
# 3. SINASC: Nascidos vivos por residência da mãe (2022-2026 agregados)
# =====================================================================
print("Processando SINASC...")
idade = ler_tabnet(ARQ_NASC_IDADE_MAE)
gestacao = ler_tabnet(ARQ_NASC_GESTACAO)

final['nasc_total'] = idade['Total']
final['nasc_idade_conhecida'] = idade['Total'] - idade['Idade ignorada']
final['nasc_mae_menor_20'] = idade[['Menor de 10 anos', '10 a 14 anos', '15 a 19 anos']].sum(axis=1)
final['nasc_gestacao_conhecida'] = gestacao['Total'] - gestacao['Ignorado']
final['nasc_pretermo'] = gestacao[['Menos de 22 semanas', 'De 22 a 27 semanas',
                                   'De 28 a 31 semanas', 'De 32 a 36 semanas']].sum(axis=1)

# =====================================================================
# 4. SIM: Óbitos de 30 a 69 anos por capítulo da CID-10 (2022-2026 agregados)
# =====================================================================
print("Processando SIM...")
obitos = ler_tabnet(ARQ_OBITOS)
final['obitos_total'] = obitos['Total']
for coluna in obitos.columns:
    if coluna.startswith('Cap '):
        final['obitos_cap_' + coluna.replace('Cap ', '').lower()] = obitos[coluna]

# =====================================================================
# 5. EXPORTAR
# =====================================================================
nome_saida = 'indicadores_municipais_rmsp.csv'
final.reset_index().to_csv(nome_saida, index=False)
print(f"SUCESSO! '{nome_saida}' pronto: {len(final)} municípios, {final.shape[1]} indicadores.")
