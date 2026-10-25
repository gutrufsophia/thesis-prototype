import os
from pathlib import Path

import geopandas as gpd
from sqlalchemy import create_engine


def read_env(path):
    env = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip("'\"")
    return env


# 1. Carrega o GeoJSON de 44MB
print("Lendo o arquivo GeoJSON...")
gdf = gpd.read_file("/home/sophia/Downloads/SP_setores_CD2022 (1).json")

# 2. A conexão vem do .env (DATABASE_URL), que não é versionado
uri_conexao = os.environ.get("DATABASE_URL") or read_env(Path(__file__).resolve().parents[2] / ".env")["DATABASE_URL"]
engine = create_engine(uri_conexao)

# 3. Envia os polígonos para o banco criando a tabela espacial
print("Enviando para o Supabase...")
gdf.to_postgis(
    name="setores_censitarios_grande_sp", # Nome da tabela que será criada
    con=engine,
    if_exists="replace",
    index=True # Cria automaticamente o índice espacial GIST (essencial para performance)
)
print("Sucesso!")
