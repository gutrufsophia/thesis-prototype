# Data

The tables behind the prototype, for the São Paulo Metropolitan Region (RMSP, 39 municipalities). They are the files loaded into the database and the results computed from them. Every file is produced by a script in this repository, named below, from public sources. Run `update.sh` to rebuild them all.

- **Format:** CSV, comma separated, UTF-8, header row, decimal point.
- **Percentages:** stored from 0 to 100.
- **Distances:** in metres.
- **Keys:**
  - `CO_CNES` / `cnes` is the facility's CNES code;
  - `cd_setor` is the 15-digit IBGE census tract code;
  - `cd_municipio` is the 7-digit IBGE municipality code, and `cd_municipio6` the 6-digit code that DATASUS uses;
  - `cd_dist` is the 9-digit IBGE code of a São Paulo city district.
- **License:** CC BY 4.0 (see [LICENSE.md](LICENSE.md)).

## Sources

| Source | Content | Period |
|---|---|---|
| CNES (DATASUS) | Health establishments, beds, ICU beds, staff, equipment, teams | August 2026 |
| SIH (DATASUS TabNet) | SUS admissions by cause, length of stay, deaths | admissions processed Jan/2025 to Jul/2026 |
| SINAN, SINASC, SIM (DATASUS TabNet) | Tuberculosis, dengue and leptospirosis cases; births; deaths aged 30 to 69 | see each file |
| SMS-SP TabNet | The same outcomes for the 96 districts of São Paulo city | see each file |
| Census 2022 (IBGE) | Population, households, sewage, garbage collection, household-head income per tract | 2022 (income published 2026-05-08) |
| CNEFE 2022 (IBGE) | Residential addresses, used for geocoding and distances | 2022 |

## Tables

### Facilities and census

| File | Rows | Content | Script |
|---|---|---|---|
| `culturaeduca_infraestrutura_saude_rmsp.csv` | 6,763 | One row per health establishment. Contents: CNES record (name, address, type, management, flow, opening hours, SUS link); beds and ICU beds, total and SUS; equipment counts by category (`equip_*`); staff by specialty (`esp_*`, `total_*`); SUS admissions by ICD-10 chapter (`internacoes_*`) and mean length of stay. The database adds the geocoded position and the in-hospital mortality (`hospital_mortality.csv`). | `etl/limpeza.py` |
| `dados_censo_culturaeduca.csv` | 47,293 | One row per census tract: population, households, mean residents per household, households on the sewage network, with precarious sewage (cesspit, ditch, river, no bathroom), with garbage collected, and the households informing each. | `etl/limpeza_ibge.py` |
| `renda_responsavel_rmsp.csv` | 46,461 | Household heads and their mean and median monthly income per tract. Withheld cells are empty. | `etl/limpeza_renda.py` |

### Health outcomes

| File | Rows | Content | Script |
|---|---|---|---|
| `indicadores_municipais_rmsp.csv` | 39 | Per municipality of residence: probable dengue and confirmed leptospirosis cases by year (2022–2026), tuberculosis cases (2022–2025), births and births to mothers under 20 and preterm (2022–2024), deaths aged 30–69 by ICD-10 chapter (`obitos_cap_*`, 2022–2024). | `etl/limpeza_datasus.py` |
| `indicadores_distrito_sp.csv` | 96 | The same outcomes for São Paulo city's districts (SMS-SP systems: tuberculosis among residents with an address; births; deaths), with census figures summed from tracts. | `database/tabnet/build_district_indicators.py` |
| `municipalities.csv` | 39 | 6-digit code and name of each municipality. | — |
| `outcome_expected.csv` | 270 | For each district or municipality and outcome: observed count, count expected by a quasi-Poisson model of income, crowding and sanitation, and its 95% prediction interval. `flag` is `above` or `below` where the observation falls outside, for the models used to flag areas. | `analysis/outcome_relations.py` |

### Surroundings and access

| File | Rows | Content | Script |
|---|---|---|---|
| `surroundings_1000.csv` | 6,687 | The 1 km surroundings of every mapped facility, by area weighting of tracts, as on the facility page:<br>• residents and households;<br>• % of households not on the sewage network (`sewage_pct` is the share on it), with precarious sewage, and with garbage collected;<br>• residents per household and % in the region's most crowded decile of tracts;<br>• % of residents more than 1 km from public primary care;<br>• mean household-head income and tracts touched;<br>• public primary care units nearby;<br>• residents in deprived tracts (at least one of: precarious sewage ≥ 20%, ≥ 3.1 residents per household, garbage collection ≤ 90%, income below 60% of the regional median). | `database/reference/build_surroundings.sh` |
| `surroundings_types.csv` | 6,685 | Territorial type of each facility's 1 km surroundings (k-means, k = 3): 1 rural fringe with poor sanitation, 2 crowded lower-income urban periphery, 3 consolidated higher-income urban area. | `analysis/typology.py` |
| `catchment_units.csv` | 1,316 | For each public primary care unit:<br>• people expected to use it (Huff model over CNEFE addresses within variable catchments);<br>• % of them in deprived tracts;<br>• catchment radius and distance to the RMSP edge;<br>• teams (Family Health, and Primary Care 20 h and 30 h), their equivalents and people per team;<br>• mean distance of the people served and % of them beyond 2 km. | `database/reference/compute_catchment.py` |
| `catchment_summary.json` | — | Parameters and totals of the catchment model. | same |
| `hospital_mortality.csv` | 144 | For each hospital with SUS admissions:<br>• admissions, deaths and crude rate;<br>• deaths expected from its case mix (diagnosis group × age group × admission type at regional rates), the observed ÷ expected ratio and the funnel limits at 95% and 99.8%, with `band` within/above/below;<br>• the most frequent chapter;<br>• the regional rate and the Shapley split of expected minus regional rate (`shapley_*_pp`, percentage points), with the shares of admissions aged 70+, urgent and in the chapter that weighs most, against the region. | `database/reference/compute_hospital_mortality.py` |
| `hospital_mortality_summary.json` | — | Totals, overdispersion and model checks of the mortality computation. | same |

### Geocoding (in `database/geocoding/`)

| File | Rows | Content | Script |
|---|---|---|---|
| `geocoded_facilities.csv` | 1,270 | Positions from CNEFE addresses for establishments without a usable CNES coordinate. `tier` gives the match (exact address, street, postcode) and `spread_m` the uncertainty. | `geocode_cnefe.py` |
| `setor_acesso.csv` | 46,000 | Per census tract: residential addresses and the % within 500 m, 1 km and 2 km (straight line) of the nearest public primary care unit, and the median distance. | `compute_access.py` |
| `validation_*.csv`, `establishment_evidence.csv`, `corrections_audit.csv`, `arbitration_sample.csv`, `coarse_tier_precision.csv` | — | Validation of the geocoding against CNES coordinates and OpenStreetMap, and the audit of the 337 coordinates replaced. | `audit_corrections.py`, `verify_establishments.py`, `arbitrate_sample.py` |

## Not in the repository

- **Census tract polygons:** IBGE's 2022 mesh, loaded with `database/seeders/load_geometry.py`.
- **`catchment_tracts.csv`:** the allocation of each tract's residents to units, which is large; `compute_catchment.py` regenerates it.
- **Raw downloads:** TabNet exports are in `database/tabnet/raw/`; the CNES, Census and CNEFE files are downloaded from DATASUS and IBGE.
- **The live database:** the published site reads the same tables through a read-only API.
