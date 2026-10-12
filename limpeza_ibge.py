import pandas as pd

municipios_rmsp = [
    '3550308', '3503901', '3505708', '3506607', '3509007', '3509205', '3510609', '3513009', 
    '3513801', '3515004', '3515103', '3515707', '3516309', '3516408', '3518305', '3518800', 
    '3522208', '3522505', '3523107', '3525003', '3526209', '3528502', '3529401', '3530607', 
    '3534401', '3539103', '3539806', '3543303', '3544103', '3545001', '3546801', '3547304', 
    '3547809', '3548708', '3548807', '3549953', '3552502', '3552809', '3556453'
]

# CORREÇÃO 1: Colunas exatas conforme o seu teste (v minúsculo no básico, setor no domicílio)
colunas_basico = ['CD_SETOR', 'v0001', 'v0005', 'v0007'] 
colunas_domicilio = ['setor', 'V00309', 'V00397', 'V00398'] 

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

# 5. Tratamento de dados mascarados e soma matemática para o lixo coletado
# Transforma 'X' e valores não numéricos em '0' nas colunas originais, depois converte para número
df_final['V00397'] = pd.to_numeric(df_final['V00397'].replace('X', 0, regex=False), errors='coerce').fillna(0)
df_final['V00398'] = pd.to_numeric(df_final['V00398'].replace('X', 0, regex=False), errors='coerce').fillna(0)

# Agora sim, fazemos a soma matemática
df_final['total_lixo_coletado'] = df_final['V00397'] + df_final['V00398']

# Aproveite e garanta que as colunas numéricas de esgoto e domicílios não tenham 'X' escondidos
df_final['v0007'] = pd.to_numeric(df_final['v0007'].replace('X', 0, regex=False), errors='coerce').fillna(0)
df_final['V00309'] = pd.to_numeric(df_final['V00309'].replace('X', 0, regex=False), errors='coerce').fillna(0)

# 6. Renomear as colunas para ficar elegante no banco de dados do Supabase
df_final = df_final.rename(columns={
    'CD_SETOR': 'cd_setor',
    'CD_MUN': 'cd_municipio',
    'v0001': 'populacao_total',
    'v0005': 'media_moradores_domicilio',
    'v0007': 'total_domicilios_ocupados',
    'V00309': 'esgoto_rede_geral'
})

# Vamos manter apenas as colunas amigáveis
colunas_finais = [
    'cd_setor', 'cd_municipio', 'populacao_total', 'media_moradores_domicilio',
    'total_domicilios_ocupados', 'esgoto_rede_geral', 'total_lixo_coletado'
]
df_final = df_final[colunas_finais]

# 7. Salvar o arquivo final!
print("Salvando arquivo limpo...")
df_final.to_csv("dados_censo_culturaeduca.csv", index=False)
print("Sucesso! O arquivo dados_censo_culturaeduca.csv está pronto e levinho.")