Health Data Architecture & Spatial Strategy
Project: CulturaEduca Prototype Data Model

This document outlines the data integration strategy for mapping health indicators across different territorial granularities, balancing patient privacy constraints with actionable spatial intelligence.

1. The Granularity Challenge & Spatial Modeling
Due to data protection laws (LGPD in Brazil), open microdata regarding patient diseases and mortality (SINAN, SIM, SINASC) are geographically masked to the District or Municipality level. To integrate these macro-indicators with micro-level Census Tracts (IBGE) and Facility coordinates (CNES), we apply three spatial modeling techniques:

Dasymetric Mapping (Weighted Disaggregation): Instead of assuming flat disease rates across a district, macro-level disease counts (e.g., Tuberculosis) are weighted and mathematically distributed to Census Tracts based on their IBGE risk factors (e.g., household density).

Context Inheritance (Spatial Join): Micro-territories inherit macro-rates with explicit contextual framing (e.g., "This Census Tract is located within a District experiencing 120 hospitalizations for waterborne diseases").

Catchment Areas (Accessibility Radii): Using exact facility coordinates to draw 1km or 15-minute walking buffers, intersecting them with IBGE population data to identify micro-zones of "Healthcare Isolation."

2. Product Strategy: Risk vs. Outcome
Because block-level disease data is inaccessible, the platform's narrative shifts from "who is sick on this street" to "what is the risk profile of this street, and how is the broader district impacted?"

This is achieved by displaying Micro-Causes (Census data like lack of sanitation) alongside Macro-Effects (District data like Dengue outbreaks). Furthermore, combining IBGE, CNES, and DATASUS layers allows the creation of a proprietary Health Vulnerability Index, helping managers understand the epidemiological context surrounding cultural and educational centers.

3. Recommended Health Data Metrics
A. Facility-Level Data (The Equipment)
Granularity: Exact Latitude/Longitude (CNES, SIH, SIA)

Bed Capacity Distribution: Total installed beds categorized by function (Clinical, Surgical, Obstetrical, and Adult/Pediatric/Neonatal ICU). Immediately defines if the facility is for inpatient care or strictly outpatient.

Clinical Workforce Density: Active professionals grouped by the Brazilian Occupation Classification (CBO). Quantifying General Practitioners, Pediatricians, OB/GYNs, and Nurses maps the unit's care focus.

Diagnostic Infrastructure: Presence of high-impact medical equipment (X-Ray, CT Scanners, Mammography machines, ECGs, and Ultrasound).

High-Complexity Accreditations: Categorical flags indicating authorized specialized services (e.g., ER/Trauma, Oncology, CAPS/Mental Health, Cardiovascular Care, or Renal Therapy).

Hospital Morbidity & Admission Profile: For inpatient units, primary diagnosis codes (ICD-10) and average length of stay (SIH data). Differentiates acute trauma centers from chronic/palliative care hospitals.

Throughput & Demand Flow: Monthly volume of low vs. high-complexity procedures (SIA/SIH), indicating if the facility absorbs local preventive demand or acts as a regional referral hub.

B. Surrounding Territory Data (The Environment)
Granularity: Hybrid (Micro-Risk factors crossed with Macro-Outcomes)

Environmental Vulnerability & Vector Diseases:

Micro (IBGE): Proportion of households with uncollected garbage or open sewage (Census Tract).

Macro (SINAN): Incidence of Arboviruses (Dengue, Zika, Chikungunya) and waterborne diseases (Leptospirosis) (District).

Respiratory Risk & Urban Crowding:

Micro (IBGE): Average residents per household and slum/tenement typologies (Census Tract).

Macro (SINAN): Incidence of Tuberculosis and severe respiratory infections (District).

Maternal & Child Vulnerability:

Macro (SINASC): Premature birth rates, low birth weight incidence, teenage pregnancy ratios, and cesarean vs. vaginal delivery rates (District). Directly informs early childhood educational planning.

Premature Mortality Profile:

Macro (SIM): Top three causes of premature mortality (ages 30-69), grouped by primary categories (Cardiovascular, Cancer, Respiratory, External Causes/Violence) (District).

Primary Care Chronic Tracking:

Micro-Proxy (SISAB): Proportion of patients actively monitored for systemic chronic conditions (Hypertension, Diabetes) within Family Health Strategy micro-areas (highly granular, approximates Census Tracts).

Healthcare Accessibility Index:

Integrated: The geographic overlap of facility locations (CNES) against local population density (IBGE), identifying "care deserts" immediately surrounding schools or cultural assets.

Data Engineering:

1. Environmental Vulnerability & Vector Diseases (Vulnerabilidade Ambiental e Vetores)
A Abordagem de Exibição (UI/UX):

Visualização: Um Mapa Coroplético (mapa de calor por polígonos) focado no micro-território (Setor Censitário). Cores mais quentes (vermelho/laranja) mostram quarteirões com maior ausência de saneamento/coleta de lixo.

Dado Rico (Narrativa): Ao passar o mouse sobre a área, um Tooltip/Card exibe a relação Causa-Efeito: "Neste quarteirão, 35% das casas não têm rede de esgoto (Dado Micro). O distrito ao qual ele pertence registrou 120 casos de Leptospirose no último ano (Dado Macro)."

A Engenharia de Dados (Pipeline):

Técnica: Herança de Contexto (Spatial Join Direto).

Processamento: No PostGIS/Banco Espacial, roda-se um ST_Within (ou ST_Intersects) cruzando os polígonos dos Setores Censitários (IBGE) com o polígono do Distrito Administrativo. O banco cria uma tabela relacional simples: o Setor X "pertence" ao Distrito Y e, portanto, "herda" o indicador de doenças para fins de exibição conjunta, sem alterar o valor original.

Onde conseguir (100% de Certeza):

Micro: IBGE - Censo Demográfico 2022. (Dados do Universo, tabelas de Saneamento e Coleta de Lixo agregadas por Setor Censitário. Download via API SIDRA ou Malhas Geográficas do IBGE).

Macro: DATASUS - SINAN. (Acessado via portal TabNet da Secretaria Municipal/Estadual de Saúde. Tabular "Casos Confirmados" por "Local de Residência" e filtrar territorialmente por "Distrito Administrativo").

2. Respiratory Risk & Urban Crowding (Risco Respiratório e Adensamento)
A Abordagem de Exibição (UI/UX):

Visualização: Um gráfico de Gauge (Termômetro) ou Risco Dinâmico no painel lateral do mapa.

Dado Rico (Narrativa): Em vez de jogar o dado cru, o sistema traduz o cruzamento em um alerta semântico: "Atenção: Alta Vulnerabilidade Respiratória. O equipamento está em um setor com 4.5 moradores/domicílio (Top 10% mais adensados) imerso num distrito com incidência crítica de Tuberculose (45 casos/100k hab)."

A Engenharia de Dados (Pipeline):

Técnica: Mapeamento Dasimétrico (Desagregação Ponderada).

Processamento: Você pega o total de casos de TB do Distrito. Em seguida, cria um "Índice de Adensamento" (habitantes/domicílio) para cada setor censitário daquele distrito via IBGE. Você redistribui matematicamente (pesos proporcionais) os casos do distrito para os setores. Setores com muita gente em poucas casas "puxam" a maior parte da estimativa de casos de Tuberculose.

Onde conseguir (100% de Certeza):

Micro: IBGE - Censo Demográfico 2022. (Tabela de "Média de moradores por domicílio" por Setor Censitário).

Macro: DATASUS - SINAN. (Tuberculose Casos Ativos, via TabNet, agrupados por Distrito de residência).

3. Maternal & Child Vulnerability (Vulnerabilidade Materno-Infantil)
A Abordagem de Exibição (UI/UX):

Visualização: Um Radar Chart (Gráfico de Teia) comparativo, onde o usuário vê o polígono da macrorregião no mapa, e o painel compara o distrito selecionado com a média da cidade.

Dado Rico (Narrativa): Focado em planejamento educacional. "Cenário da Primeira Infância: Este distrito possui 15% de mães adolescentes (5% acima da média da cidade) e 12% de nascimentos prematuros. Equipamentos culturais aqui demandam projetos de acolhimento parental."

A Engenharia de Dados (Pipeline):

Técnica: Agregação Macro Direta via Ponto-Polígono.

Processamento: Como o SINASC é robusto por distrito, você pega a latitude/longitude do Equipamento de Cultura/Educação pesquisado, cruza com o polígono do Distrito (ST_Contains) e retorna os KPIs materno-infantis.

Onde conseguir (100% de Certeza):

Macro: DATASUS - SINASC (Sistema de Nascidos Vivos). (Base de extrema qualidade. Extraído via TabNet Municipal ou FTP DATASUS. Variáveis: Idade da Mãe, Peso ao Nascer, Semanas de Gestação, Tipo de Parto, cruzadas por Distrito de residência).

4. Premature Mortality Profile (Perfil de Mortalidade Prematura)
A Abordagem de Exibição (UI/UX):

Visualização: Um Gráfico de Barras Horizontais simples e direto ou Waffle Chart (matriz de pontinhos).

Dado Rico (Narrativa): O sistema isola apenas os óbitos precoces (30 a 69 anos, que reflete produtividade econômica e falhas de prevenção) e exibe: "As 3 Maiores Ameaças Fatais na Região: 1º Doenças Cardiovasculares (42%), 2º Causas Externas/Violência (20%), 3º Câncer (15%)."

A Engenharia de Dados (Pipeline):

Técnica: Filtro de Faixa Etária e Categorização CID-10.

Processamento: ETL simples agrupando os milhares de códigos de doenças (CID-10) nos "Capítulos" macro da OMS. Depois, linka-se espacialmente o distrito ao equipamento pesquisado.

Onde conseguir (100% de Certeza):

Macro: DATASUS - SIM (Sistema de Informações sobre Mortalidade). (Acessado via TabNet. Filtro 1: Faixa Etária 30-69. Filtro 2: Agrupar por Capítulo CID-10. Filtro 3: Distrito).

5. Primary Care Chronic Tracking (Acompanhamento Crônico na Atenção Básica)
A Abordagem de Exibição (UI/UX):

Visualização: Mapa de Bolhas (Bubble Map) sobre as Unidades Básicas de Saúde (UBS). Quanto maior/mais vermelha a bolha sobre a UBS, maior a proporção de hipertensos/diabéticos acompanhados ali.

Dado Rico (Narrativa): "Pressão Assistencial Crônica: A UBS que atende esta rua possui 850 diabéticos sob acompanhamento ativo."

A Engenharia de Dados (Pipeline):

Técnica: Proxy Geográfico (Matching de Unidade-Território).

Processamento: Os dados do SISAB não estão no polígono do IBGE, estão no "CNES da UBS". O pipeline atrela a coordenada exata da UBS ao dado de saúde. No frontend, você mostra as bolhas em volta do equipamento de educação/cultura pesquisado, revelando a saúde crônica da vizinhança.

Onde conseguir (100% de Certeza):

Micro/Proxy: SISAB - e-Gestor AB. (Portal Público de Relatórios do Ministério da Saúde. Selecionar "Cadastro de Cidadãos" ou "Indicadores de Desempenho", filtrando por Município -> Estabelecimento de Saúde/CNES. Retorna planilhas exatas por unidade).

6. Healthcare Accessibility Index (Desertos de Assistência / Isócronas)
A Abordagem de Exibição (UI/UX):

Visualização: Polígonos Isócronos (Manchas de Caminhabilidade). O mapa desenha uma mancha irregular mostrando até onde se consegue chegar andando em 15 minutos a partir dos postos de saúde. Setores censitários fora das manchas ficam acinzentados ou vermelhos.

Dado Rico (Narrativa): "Deserto de Saúde: 450 idosos (dado IBGE) vivem ao redor desta Escola/Centro Cultural em uma área que exige mais de 2 km de caminhada até o posto médico mais próximo."

A Engenharia de Dados (Pipeline):

Técnica: Análise de Redes (Network Analysis) + Interseção Espacial.

Processamento:

Pega-se as coordenadas (CNES) de todas as UBS.

Usa-se uma API de rotas (como OSRM ou pgRouting com dados do OpenStreetMap) para gerar o polígono de 15 minutos a pé.

Realiza-se um ST_Intersection entre esse polígono e os Setores Censitários do IBGE para somar a população que ficou "de fora" do raio (O Deserto).

Onde conseguir (100% de Certeza):

Coordenadas: CNES - Cadastro Nacional de Estabelecimentos de Saúde (Base completa no FTP do DATASUS ou extração por API de Dados Abertos do Governo, tabela de Estabelecimentos com Lat/Long).

Malha Viária: OpenStreetMap (OSM) (Para calcular as ruas caminháveis).

População: IBGE - Censo Demográfico 2022 (Contagem populacional por idade no nível do Setor).


O free tier do Supabase (que oferece 500 MB de armazenamento de banco de dados) dá conta do recado para um protótipo focado no estado de São Paulo, mas você precisará ser cirúrgica no geoprocessamento. O segredo para não estourar a cota não está no volume das estatísticas de saúde, mas no peso das geometrias no PostGIS.Aqui está o mapa de como esse espaço será consumido e como otimizar para que o CulturaEduca rode sem gargalos:O peso-pena (Tabelas DATASUS, CNES e SISAB): Os indicadores agregados de SINAN, SIM e SINASC para os 645 municípios paulistas (ou 96 distritos da capital) não chegam a 5 MB. O cadastro do CNES, mesmo com ~30 mil estabelecimentos de saúde no estado contendo latitude, longitude e colunas booleanas de serviços, consome menos de 10 MB.O peso-médio (Tabelas do IBGE): O estado de São Paulo possui cerca de 85 mil setores censitários. Uma tabela relacional com 85 mil linhas contendo os dados demográficos e de saneamento vai ocupar algo em torno de 15 MB a 25 MB.O vilão da cota (Malhas Geográficas/Polígonos): Armazenar a geometria exata (MultiPolygon) desses 85 mil setores censitários é o que vai devorar seus 500 MB. Se você importar o shapefile bruto do IBGE direto para o banco, ele pode ultrapassar 300 MB por conta do nível absurdo de detalhes (curvas de ruas, contornos de rios).Estratégias para manter o banco leve e rápido:Simplificação de Geometria: Antes de subir os polígonos para o Supabase, passe a malha do IBGE em ferramentas como o Mapshaper (ou rode um ST_Simplify no banco local). Reduzir a resolução dos vértices em 80% deixa o mapa visualmente idêntico no front-end, mas derruba o peso da geometria de 300 MB para uns 40 MB.Separe o Mapa do Dado: Uma alternativa muito usada em protótipos é não salvar os polígonos no banco. Você exporta as malhas simplificadas como arquivos GeoJSON, hospeda em um bucket (o Supabase Storage gratuito dá 1 GB) ou serve direto no front-end, e deixa no banco PostgreSQL apenas o código do setor censitário e os indicadores de saúde. O join entre a forma geométrica e a cor do mapa ocorre no navegador do usuário.Índices Espaciais são Lógica de Sobrevivência: Como você já tem experiência com benchmarking e indexação de queries no PostgreSQL, vale o alerta: a máquina gratuita do Supabase tem apenas 512 MB de RAM. Se você for rodar ST_Intersects (para achar quais equipamentos estão dentro de um distrito) sem criar um índice espacial GIST na coluna de geometria, o banco vai dar timeout.Escopo do Protótipo: Se for estritamente para validar a ideia no TCC, focar apenas na Região Metropolitana de São Paulo em vez do estado inteiro reduz a base de 85 mil para uns 35 mil setores censitários. Garante folga na hospedagem e deixa a renderização do mapa fluida.