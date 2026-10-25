from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]

municipios_rmsp = [
    '3550308', '3503901', '3505708', '3506607', '3509007', '3509205', '3510609', '3513009', 
    '3513801', '3515004', '3515103', '3515707', '3516309', '3516408', '3518305', '3518800', 
    '3522208', '3522505', '3523107', '3525003', '3526209', '3528502', '3529401', '3530607', 
    '3534401', '3539103', '3539806', '3543303', '3544103', '3545001', '3546801', '3547304', 
    '3547809', '3548708', '3548807', '3549953', '3552502', '3552809', '3556453'
]

# CORREÇÃO 1: Colunas exatas conforme o seu teste (v minúsculo no básico, setor no domicílio)
colunas_basico = ['CD_SETOR', 'v0001', 'v0005', 'v0007'] 
# Destino do esgoto (V00309 a V00316) e do lixo (V00397 a V00402): todas as categorias,
# para que a soma delas sirva de denominador
colunas_esgoto = ['V00309', 'V00310', 'V00311', 'V00312', 'V00313', 'V00314', 'V00315', 'V00316']
colunas_lixo = ['V00397', 'V00398', 'V00399', 'V00400', 'V00401', 'V00402']
colunas_domicilio = ['setor'] + colunas_esgoto + colunas_lixo

print("Lendo arquivo do Básico...")
df_basico = pd.read_csv(
    "/home/sophia/Downloads/basico.csv", 
    sep=";", 
    encoding="latin1", # CORREÇÃO 2: Aplicado na leitura real
    usecols=colunas_basico,
    dtype={'CD_SETOR': str},
    decimal="," 
)

print("Lendo arquivo de Domicílios...")
df_domicilio = pd.read_csv(
    "/home/sophia/Downloads/domicilio2.csv", 
    sep=";", 
    encoding="latin1", # CORREÇÃO 2: Aplicado na leitura real
    usecols=colunas_domicilio,
    dtype={'setor': str},
    decimal=","
)

# CORREÇÃO 3: Renomear 'setor' para 'CD_SETOR' para podermos juntar as duas tabelas
df_domicilio = df_domicilio.rename(columns={'setor': 'CD_SETOR'})

# 2. Criar a coluna de município usando os 7 primeiros dígitos do Setor Censitário
df_basico['CD_MUN'] = df_basico['CD_SETOR'].str[:7]

# 3. Filtrar apenas a Grande São Paulo no arquivo básico primeiro (para ficar mais rápido)
print("Filtrando a Grande São Paulo...")
df_basico_rmsp = df_basico[df_basico['CD_MUN'].isin(municipios_rmsp)]

# 4. Juntar (Join) as tabelas usando o CD_SETOR
print("Unificando os dados (Join)...")
df_final = pd.merge(df_basico_rmsp, df_domicilio, on='CD_SETOR', how='left')

# 5. Tratamento de dados mascarados
# O IBGE omite com 'X' as contagens de 1 ou 2 domicílios (o menor valor publicado é 3).
# 'X' não é zero: vale 1,5 em média. Quando TODAS as categorias de um setor estão omitidas,
# não há informação nenhuma e o resultado fica vazio (sem dados), não zero.
VALOR_OMITIDO = 1.5

def somar_categorias(df, colunas):
    """Soma das colunas, com 'X' valendo VALOR_OMITIDO; vazio se o setor não tem nenhum valor publicado."""
    omitido = df[colunas].eq('X')
    valores = df[colunas].apply(pd.to_numeric, errors='coerce')
    sem_informacao = valores.isna().all(axis=1)
    soma = valores.fillna(0).sum(axis=1) + omitido.sum(axis=1) * VALOR_OMITIDO
    return soma.where(~sem_informacao).round()

# Ligados à rede: rede geral ou pluvial (V00309) + fossa séptica ou filtro ligada à rede (V00310)
df_final['esgoto_rede_geral'] = somar_categorias(df_final, ['V00309', 'V00310'])
df_final['domicilios_esgoto_informado'] = somar_categorias(df_final, colunas_esgoto)
# Esgotamento precário: fossa rudimentar ou buraco (V00312), vala (V00313), rio, lago, córrego
# ou mar (V00314), outra forma (V00315) e sem banheiro nem sanitário (V00316).
# A fossa séptica não ligada à rede (V00311) fica de fora: é solução individual aceita.
df_final['esgoto_precario'] = somar_categorias(df_final, ['V00312', 'V00313', 'V00314', 'V00315', 'V00316'])
# Coletado no domicílio (V00397) + em caçamba de serviço de limpeza (V00398)
df_final['total_lixo_coletado'] = somar_categorias(df_final, ['V00397', 'V00398'])
df_final['domicilios_lixo_informado'] = somar_categorias(df_final, colunas_lixo)

# Sem nenhum dado de esgoto/lixo no setor, as contagens também ficam vazias
for contagem, denominador in (('esgoto_rede_geral', 'domicilios_esgoto_informado'),
                              ('esgoto_precario', 'domicilios_esgoto_informado'),
                              ('total_lixo_coletado', 'domicilios_lixo_informado')):
    df_final.loc[df_final[denominador].isna(), contagem] = float('nan')

df_final['v0007'] = pd.to_numeric(df_final['v0007'].replace('X', 0, regex=False), errors='coerce').fillna(0)

# 6. Renomear as colunas para ficar elegante no banco de dados do Supabase
df_final = df_final.rename(columns={
    'CD_SETOR': 'cd_setor',
    'CD_MUN': 'cd_municipio',
    'v0001': 'populacao_total',
    'v0005': 'media_moradores_domicilio',
    'v0007': 'total_domicilios_ocupados'
})

# Vamos manter apenas as colunas amigáveis
colunas_finais = [
    'cd_setor', 'cd_municipio', 'populacao_total', 'media_moradores_domicilio',
    'total_domicilios_ocupados', 'esgoto_rede_geral', 'esgoto_precario', 'domicilios_esgoto_informado',
    'total_lixo_coletado', 'domicilios_lixo_informado'
]
df_final = df_final[colunas_finais]

# 7. Salvar o arquivo final!
print("Salvando arquivo limpo...")
df_final.to_csv(RAIZ / "data" / "dados_censo_culturaeduca.csv", index=False)
print("Sucesso! O arquivo dados_censo_culturaeduca.csv está pronto e levinho.")