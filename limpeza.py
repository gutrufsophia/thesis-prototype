import pandas as pd
import re

print("Iniciando o ETL da Infraestrutura de Saúde (CulturaEduca) - RMSP...")

# =====================================================================
# 0. CONFIGURAÇÕES INICIAIS
# =====================================================================
rmsp_ibge6 = [
    '350390', '350570', '350660', '350900', '350920', '351060', '351300', 
    '351380', '351500', '351510', '351570', '351630', '351640', '351830', 
    '351880', '352220', '352250', '352310', '352500', '352620', '352850', 
    '352940', '353060', '353440', '353980', '353910', '354330', '354410', 
    '354500', '354680', '354730', '354780', '354870', '354880', '354995', 
    '355030', '355250', '355280', '355645'
]

ARQUIVO_SIH_MORBIDADE = '/home/sophia/Downloads/sih_cnv_nisp154808191_181_56_142.csv' 
ARQUIVO_SIH_PERMANENCIA = '/home/sophia/Downloads/sih_cnv_nisp154949191_181_56_142.csv'

# =====================================================================
# 1. A ESPINHA DORSAL: Estabelecimentos, Filtros e Front-end
# =====================================================================
print("Processando Estabelecimentos (A Espinha Dorsal)...")

colunas_estab = [
    'CO_CNES',
    'NO_FANTASIA', 
    'NO_RAZAO_SOCIAL', 
    'CO_MUNICIPIO_GESTOR', 
    'TP_UNIDADE', 
    'TP_GESTAO', 
    'NO_LOGRADOURO', 
    'NU_ENDERECO', 
    'NO_BAIRRO', 
    'CO_CEP', 
    'NU_LATITUDE', 
    'NU_LONGITUDE', 
    'CO_CLIENTELA', 
    'CO_TURNO_ATENDIMENTO', 
    'CO_NATUREZA_JUR',
    'NU_CNPJ_MANTENEDORA'
]

df_estab = pd.read_csv('/home/sophia/Downloads/BASE_DE_DADOS_CNES_202608/tbEstabelecimento202608.csv', 
                       sep=';', encoding='latin-1', usecols=colunas_estab, dtype=str)

df_rmsp = df_estab[df_estab['CO_MUNICIPIO_GESTOR'].isin(rmsp_ibge6)].copy()

# 1.1 TRADUÇÕES PARA O FRONT-END (Fica igualzinho ao seu protótipo)
df_rmsp['tipo_equipamento'] = df_rmsp['TP_UNIDADE'].map({
    '01': 'Posto de Saúde',
    '02': 'Centro de Saúde/UBS',
    '04': 'Policlínica',
    '05': 'Hospital Geral',
    '07': 'Hospital Especializado',
    '15': 'Unidade Mista',
    '20': 'Pronto Socorro Geral',
    '21': 'Pronto Socorro Especializado',
    '36': 'Clínica/Centro de Especialidade',
    '39': 'Unidade de Apoio Diagnose e Terapia (SADT Isolado)',
    '73': 'Pronto Atendimento (UPA)',
    '74': 'Polo Academia da Saúde',
    '70': 'Centro de Atenção Psicossocial (CAPS)'
}).fillna('Outros/Administrativo')

df_rmsp['TP_GESTAO'] = df_rmsp['TP_GESTAO'].map({
    'M': 'Municipal', 'E': 'Estadual', 'D': 'Dupla'
}).fillna('Não Informado')

df_rmsp['Fluxo_Clientela'] = df_rmsp['CO_CLIENTELA'].map({
    '1': 'Atendimento de Demanda Espontânea',
    '2': 'Atendimento de Demanda Referenciada',
    '3': 'Atendimento de Demanda Espontânea e Referenciada'
}).fillna('Não Informado')

df_rmsp['Dependencia'] = df_rmsp['NU_CNPJ_MANTENEDORA'].apply(
    lambda x: 'Individual' if pd.isna(x) or str(x).strip() == '' else 'Mantida'
)

# 1.2 A GRANDE LIMPEZA (Early Filtering)
# A) Joga fora equipamentos que não mapeamos
df_rmsp = df_rmsp[df_rmsp['tipo_equipamento'] != 'Outros/Administrativo'].copy()

# B) Joga fora clínicas privadas comerciais
df_rmsp['CO_NATUREZA_JUR'] = df_rmsp['CO_NATUREZA_JUR'].astype(str)
clinicas_privadas = (df_rmsp['tipo_equipamento'] == 'Clínica/Centro de Especialidade') & (df_rmsp['CO_NATUREZA_JUR'].str.startswith('2'))
df_rmsp = df_rmsp[~clinicas_privadas].copy()

cnes_validos_rmsp = df_rmsp['CO_CNES'].unique()
print(f"Estabelecimentos clínicos válidos na RMSP: {len(cnes_validos_rmsp)}")

df_rmsp['CO_CLIENTELA'] = pd.to_numeric(df_rmsp['CO_CLIENTELA'], errors='coerce')
df_rmsp = df_rmsp[
    (df_rmsp['CO_NATUREZA_JUR'].str.startswith('1')) | 
    (df_rmsp['CO_CLIENTELA'].isin([1.0, 2.0, 3.0]))
].copy()

# =====================================================================
# 2. CAPACIDADE INSTALADA: Leitos
# =====================================================================
print("Processando Leitos...")
colunas_leitos = [
    'CNES', 'LEITOS_EXISTENTES', 'LEITOS_SUS', 'UTI_TOTAL_EXIST', 'UTI_TOTAL_SUS', 
    'UTI_ADULTO_EXIST', 'UTI_ADULTO_SUS', 'UTI_PEDIATRICO_EXIST', 'UTI_PEDIATRICO_SUS', 
    'UTI_NEONATAL_EXIST', 'UTI_NEONATAL_SUS', 'UTI_QUEIMADO_EXIST', 'UTI_QUEIMADO_SUS', 
    'UTI_CORONARIANA_EXIST', 'UTI_CORONARIANA_SUS'
]
df_leitos = pd.read_csv('/home/sophia/Downloads/Leitos_csv_2026/Leitos_2026.csv', sep=';', encoding='latin-1', dtype=str)
df_leitos = df_leitos[df_leitos['CNES'].isin(cnes_validos_rmsp)]
# O arquivo traz uma linha por competência mensal: usar só a mais recente, senão a soma multiplica os leitos
df_leitos = df_leitos[df_leitos['COMP'] == df_leitos['COMP'].max()]
colunas_para_somar = colunas_leitos[1:]
df_leitos[colunas_para_somar] = df_leitos[colunas_para_somar].apply(pd.to_numeric, errors='coerce').fillna(0)
leitos_agrupado = df_leitos.groupby('CNES')[colunas_para_somar].sum().reset_index()

# =====================================================================
# 3. INFRAESTRUTURA DE DIAGNÓSTICO: Equipamentos 
# =====================================================================
print("Processando Equipamentos...")
df_tipo_equip = pd.read_csv('/home/sophia/Downloads/BASE_DE_DADOS_CNES_202608/tbTipoEquipamento202608.csv', sep=';', encoding='latin-1', dtype=str)
df_equip = pd.read_csv('/home/sophia/Downloads/BASE_DE_DADOS_CNES_202608/rlEstabEquipamento202608.csv', sep=';', encoding='latin-1', dtype=str)

df_equip['CO_CNES'] = df_equip['CO_UNIDADE'].astype(str).str[-7:]
df_equip = df_equip[df_equip['CO_CNES'].isin(cnes_validos_rmsp)]
df_equip['QT_EXISTENTE'] = pd.to_numeric(df_equip['QT_EXISTENTE'], errors='coerce').fillna(0)
df_equip = pd.merge(df_equip, df_tipo_equip, on='CO_TIPO_EQUIPAMENTO', how='left')
df_equip['DS_TIPO_EQUIPAMENTO'] = (df_equip['DS_TIPO_EQUIPAMENTO']
                                   .astype(str).str.lower()
                                   .str.normalize('NFKD').str.encode('ascii', errors='ignore').str.decode('utf-8')
                                   .str.replace(' ', '_'))
df_equip['DS_TIPO_EQUIPAMENTO'] = 'equip_' + df_equip['DS_TIPO_EQUIPAMENTO']

equip_pivot = df_equip.pivot_table(index='CO_CNES', columns='DS_TIPO_EQUIPAMENTO', values='QT_EXISTENTE', aggfunc='sum', fill_value=0)
equip_pivot.reset_index(inplace=True)

# =====================================================================
# 4. VOCAÇÃO DE CUIDADO: Força de Trabalho
# =====================================================================
print("Processando Profissionais...")
colunas_prof = ['CO_UNIDADE', 'CO_CBO']
df_prof = pd.read_csv('/home/sophia/Downloads/BASE_DE_DADOS_CNES_202608/rlEstabEquipeProf202608.csv', sep=';', encoding='latin-1', usecols=colunas_prof, dtype=str)

df_prof['CO_CNES'] = df_prof['CO_UNIDADE'].astype(str).str[-7:]
df_prof = df_prof[df_prof['CO_CNES'].isin(cnes_validos_rmsp)].copy()
df_prof.drop(columns=['CO_UNIDADE'], inplace=True)

df_prof['total_medicos'] = df_prof['CO_CBO'].str.startswith(('225', '2231')).astype(int)
df_prof['total_enfermeiros'] = df_prof['CO_CBO'].str.startswith('2235').astype(int)
df_prof['total_saude_mental'] = (df_prof['CO_CBO'].str.startswith('2515') | (df_prof['CO_CBO'] == '225133') | (df_prof['CO_CBO'] == '223905')).astype(int)

df_prof['esp_psicologo'] = df_prof['CO_CBO'].str.startswith('2515').astype(int)
df_prof['esp_psiquiatra'] = (df_prof['CO_CBO'] == '225133').astype(int)
df_prof['esp_terapeuta_ocupacional'] = (df_prof['CO_CBO'] == '223905').astype(int)
df_prof['esp_pediatra'] = (df_prof['CO_CBO'] == '225124').astype(int)
df_prof['esp_ginecologista_obstetra'] = (df_prof['CO_CBO'] == '225250').astype(int)
df_prof['esp_clinico_geral'] = (df_prof['CO_CBO'] == '225125').astype(int)
df_prof['esp_medico_familia'] = (df_prof['CO_CBO'] == '225130').astype(int)
df_prof['esp_cardiologista'] = (df_prof['CO_CBO'] == '225120').astype(int)
df_prof['esp_endocrinologista'] = (df_prof['CO_CBO'] == '225155').astype(int)
df_prof['esp_infecto_pneumo'] = df_prof['CO_CBO'].isin(['225103', '225127']).astype(int)
df_prof['esp_oncologista'] = df_prof['CO_CBO'].isin(['225121', '225290', '225122']).astype(int)

colunas_contar = ['total_medicos', 'total_enfermeiros', 'total_saude_mental', 'esp_psicologo', 'esp_psiquiatra', 'esp_terapeuta_ocupacional', 'esp_pediatra', 'esp_ginecologista_obstetra', 'esp_clinico_geral', 'esp_medico_familia', 'esp_cardiologista', 'esp_endocrinologista', 'esp_infecto_pneumo', 'esp_oncologista']
prof_agrupado = df_prof.groupby('CO_CNES')[colunas_contar].sum().reset_index()

# =====================================================================
# 5. DEMANDA E MORBIDADE: TabNet SIH
# =====================================================================
def extrair_cnes_sih(filepath):
    try:
        df = pd.read_csv(filepath, sep=';', encoding='latin-1', skiprows=3, skipfooter=6, engine='python')
        coluna_estab = df.columns[0]
        df['CO_CNES'] = df[coluna_estab].str.extract(r'\b(\d{7})\b')
        df.dropna(subset=['CO_CNES'], inplace=True)
        df.drop(columns=[coluna_estab], inplace=True)
        for col in df.columns:
            if col != 'CO_CNES':
                df[col] = df[col].astype(str).str.replace('-', '0').str.replace(',', '.')
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df
    except Exception as e:
        print(f"Aviso: Não foi possível carregar {filepath} -> {e}")
        return pd.DataFrame(columns=['CO_CNES'])

print("Processando Morbidade e Permanência (SIH)...")
df_sih_morbidade = extrair_cnes_sih(ARQUIVO_SIH_MORBIDADE)
df_sih_permanencia = extrair_cnes_sih(ARQUIVO_SIH_PERMANENCIA)

dicionario_cid10 = {
    'Cap 01': 'internacoes_infecciosas_parasitarias', 'Cap 02': 'internacoes_neoplasias_tumores',
    'Cap 03': 'internacoes_sangue_imunitarias', 'Cap 04': 'internacoes_endocrinas_nutricionais',
    'Cap 05': 'internacoes_transtornos_mentais', 'Cap 06': 'internacoes_sistema_nervoso',
    'Cap 07': 'internacoes_olho_anexos', 'Cap 08': 'internacoes_ouvido_mastoide',
    'Cap 09': 'internacoes_aparelho_circulatorio', 'Cap 10': 'internacoes_aparelho_respiratorio',
    'Cap 11': 'internacoes_aparelho_digestivo', 'Cap 12': 'internacoes_pele_tecido_subcutaneo',
    'Cap 13': 'internacoes_osteomuscular_conjuntivo', 'Cap 14': 'internacoes_aparelho_geniturinario',
    'Cap 15': 'internacoes_gravidez_parto_puerperio', 'Cap 16': 'internacoes_afeccoes_perinatais',
    'Cap 17': 'internacoes_malformacoes_congenitas', 'Cap 18': 'internacoes_sintomas_sinais_anormais',
    'Cap 19': 'internacoes_lesoes_envenenamentos', 'Cap 20': 'internacoes_causas_externas',
    'Cap 21': 'internacoes_contatos_servicos_saude', 'Total': 'internacoes_total'
}

df_sih_permanencia.rename(columns={'Média_permanência': 'media_dias_permanencia'}, inplace=True)
df_sih_morbidade.rename(columns=dicionario_cid10, inplace=True)

# =====================================================================
# 6. O GRANDE MERGE FINAL (Consolidação)
# =====================================================================
print("Iniciando o Merge Final para o Supabase...")

leitos_agrupado.rename(columns={'CNES': 'CO_CNES'}, inplace=True)
df_final = df_rmsp.copy()

df_final = pd.merge(df_final, leitos_agrupado, on='CO_CNES', how='left')
df_final = pd.merge(df_final, equip_pivot, on='CO_CNES', how='left')
df_final = pd.merge(df_final, prof_agrupado, on='CO_CNES', how='left')
df_final = pd.merge(df_final, df_sih_morbidade, on='CO_CNES', how='left')
df_final = pd.merge(df_final, df_sih_permanencia, on='CO_CNES', how='left')

# ---------------------------------------------------------------------
# LIMPEZA DOS NaNs
# ---------------------------------------------------------------------
# Atualizado com as novas colunas geradas
colunas_cadastrais = [
    'CO_CNES', 'NO_FANTASIA', 'NO_RAZAO_SOCIAL', 'CO_MUNICIPIO_GESTOR', 
    'TP_UNIDADE', 'TP_GESTAO', 'NO_LOGRADOURO', 'NU_ENDERECO', 
    'NO_BAIRRO', 'CO_CEP', 'NU_LATITUDE', 'NU_LONGITUDE', 
    'CO_CLIENTELA', 'CO_TURNO_ATENDIMENTO', 'tipo_equipamento',
    'CO_NATUREZA_JUR', 'NU_CNPJ_MANTENEDORA', 'Fluxo_Clientela', 'Dependencia'
]

colunas_metricas = df_final.columns.difference(colunas_cadastrais)
df_final[colunas_metricas] = df_final[colunas_metricas].fillna(0)

# =====================================================================
# 7. EXPORTAR PARA O BANCO DE DADOS
# =====================================================================
nome_saida = 'culturaeduca_infraestrutura_saude_rmsp.csv'
df_final.to_csv(nome_saida, index=False, encoding='utf-8')

print(f"SUCESSO! O arquivo limpo '{nome_saida}' está pronto para o Supabase/PostGIS.")
print(f"Total de estabelecimentos processados: {len(df_final)}")