# Health Data Architecture & Spatial Strategy
### Project: CulturaEduca — Prototype Data Model

This document outlines the data integration strategy for mapping health indicators across different territorial granularities, balancing patient privacy constraints with actionable spatial intelligence.

---

## 1. The Granularity Challenge & Spatial Modeling

Due to data protection laws (**LGPD** in Brazil), open microdata on patient diseases and mortality (**SINAN**, **SIM**, **SINASC**) are geographically masked to the District or Municipality level. To integrate these macro-level indicators with micro-level Census Tracts (**IBGE**) and Facility coordinates (**CNES**), three spatial modeling techniques are applied:

| Technique | Description |
|---|---|
| **Dasymetric Mapping** (Weighted Disaggregation) | Instead of assuming flat disease rates across a district, macro-level disease counts (e.g., Tuberculosis) are weighted and mathematically redistributed to Census Tracts based on their IBGE risk factors (e.g., household density). |
| **Context Inheritance** (Spatial Join) | Micro-territories inherit macro-rates with explicit contextual framing — e.g., *"This Census Tract is located within a District experiencing 120 hospitalizations for waterborne diseases."* |
| **Catchment Areas** (Accessibility Radii) | Exact facility coordinates are used to draw 1 km or 15-minute walking buffers, intersected with IBGE population data to identify micro-zones of "Healthcare Isolation." |

---

## 2. Product Strategy: Risk vs. Outcome

Because block-level disease data is inaccessible, the platform's narrative shifts from **"who is sick on this street"** to **"what is the risk profile of this street, and how is the broader district impacted?"**

This is achieved by displaying **Micro-Causes** (Census data, e.g., lack of sanitation) alongside **Macro-Effects** (District data, e.g., Dengue outbreaks). Combining IBGE, CNES, and DATASUS layers further enables a proprietary **Health Vulnerability Index**, helping managers understand the epidemiological context surrounding cultural and educational centers.

---

## 3. Recommended Health Data Metrics

### A. Facility-Level Data ("The Equipment")
**Granularity:** Exact Latitude/Longitude (CNES, SIH, SIA)

- **Bed Capacity Distribution** — Total installed beds by function (Clinical, Surgical, Obstetrical, Adult/Pediatric/Neonatal ICU). Immediately reveals whether a facility is for inpatient care or strictly outpatient.
- **Clinical Workforce Density** — Active professionals grouped by Brazilian Occupation Classification (CBO). Quantifying GPs, Pediatricians, OB/GYNs, and Nurses maps the unit's care focus.
- **Diagnostic Infrastructure** — Presence of high-impact medical equipment (X-Ray, CT Scanners, Mammography, ECG, Ultrasound).
- **High-Complexity Accreditations** — Categorical flags for authorized specialized services (e.g., ER/Trauma, Oncology, CAPS/Mental Health, Cardiovascular Care, Renal Therapy).
- **Hospital Morbidity & Admission Profile** — For inpatient units: primary diagnosis codes (ICD-10) and average length of stay (SIH data). Differentiates acute trauma centers from chronic/palliative care hospitals.
- **Throughput & Demand Flow** — Monthly volume of low- vs. high-complexity procedures (SIA/SIH), indicating whether the facility absorbs local preventive demand or acts as a regional referral hub.

### B. Surrounding Territory Data ("The Environment")
**Granularity:** Hybrid (Micro-Risk factors crossed with Macro-Outcomes)

| Theme | Micro Layer | Macro Layer |
|---|---|---|
| **Environmental Vulnerability & Vector Diseases** | IBGE — % of households with uncollected garbage or open sewage (Census Tract) | SINAN — Incidence of arboviruses (Dengue, Zika, Chikungunya) and waterborne disease (Leptospirosis) (District) |
| **Respiratory Risk & Urban Crowding** | IBGE — Average residents per household; slum/tenement typologies (Census Tract) | SINAN — Incidence of Tuberculosis and severe respiratory infections (District) |
| **Maternal & Child Vulnerability** | — | SINASC — Premature birth rate, low birth weight, teenage pregnancy ratio, C-section vs. vaginal delivery rate (District). Directly informs early-childhood educational planning. |
| **Premature Mortality Profile** | — | SIM — Top 3 causes of premature mortality (ages 30–69), grouped by category (Cardiovascular, Cancer, Respiratory, External Causes/Violence) (District) |
| **Primary Care Chronic Tracking** | SISAB (Micro-Proxy) — % of patients actively monitored for chronic conditions (Hypertension, Diabetes) within Family Health Strategy micro-areas — highly granular, approximates Census Tract level | — |
| **Healthcare Accessibility Index** | Integrated — geographic overlap of facility locations (CNES) with local population density (IBGE), identifying "care deserts" immediately surrounding schools or cultural assets | |

---

## 4. Data Engineering: Implementation Blueprint

For each health theme below: how it's **displayed** (UI/UX), how it's **built** (pipeline), and exactly **where to source it**.

### 4.1 Environmental Vulnerability & Vector Diseases

**Display Approach (UI/UX)**
- **Visualization:** A choropleth map (polygon heat map) focused on the micro-territory (Census Tract). Warmer colors (red/orange) mark blocks with greater lack of sanitation/garbage collection.
- **Rich Narrative:** On hover, a tooltip/card shows the cause–effect relationship:
  > *"In this block, 35% of homes lack a sewage connection (Micro Data). The district it belongs to recorded 120 cases of Leptospirosis last year (Macro Data)."*

**Data Engineering (Pipeline)**
- **Technique:** Context Inheritance (Direct Spatial Join).
- **Processing:** In PostGIS/spatial database, run `ST_Within` (or `ST_Intersects`) crossing Census Tract polygons (IBGE) with the Administrative District polygon. This creates a simple relational table: Tract X "belongs to" District Y and therefore "inherits" the disease indicator for joint display — without altering the original value.

**Where to Get It (100% Certainty)**
- **Micro:** IBGE — 2022 Demographic Census (Universe data; Sanitation and Garbage Collection tables aggregated by Census Tract. Download via SIDRA API or IBGE Geographic Meshes).
- **Macro:** DATASUS — SINAN (via the Municipal/State Health Department's TabNet portal. Tabulate "Confirmed Cases" by "Place of Residence," filtered territorially by "Administrative District").

---

### 4.2 Respiratory Risk & Urban Crowding

**Display Approach (UI/UX)**
- **Visualization:** A gauge chart ("thermometer") or dynamic risk indicator in the map's side panel.
- **Rich Narrative:** Rather than showing raw numbers, the system translates the cross-reference into a semantic alert:
  > *"Warning: High Respiratory Vulnerability. This facility sits in a tract with 4.5 residents/household (top 10% most crowded), within a district showing critical Tuberculosis incidence (45 cases/100k population)."*

**Data Engineering (Pipeline)**
- **Technique:** Dasymetric Mapping (Weighted Disaggregation).
- **Processing:** Take the district's total TB case count. Build a "Crowding Index" (residents/household) for each census tract in that district using IBGE data. Mathematically redistribute the district's cases across tracts using proportional weights — tracts with more people per household absorb a larger share of the estimated TB cases.

**Where to Get It (100% Certainty)**
- **Micro:** IBGE — 2022 Demographic Census ("Average residents per household" table, by Census Tract).
- **Macro:** DATASUS — SINAN (Active Tuberculosis Cases, via TabNet, grouped by District of residence).

---

### 4.3 Maternal & Child Vulnerability

**Display Approach (UI/UX)**
- **Visualization:** A comparative radar chart, where the user sees the macro-region polygon on the map while the side panel compares the selected district against the citywide average.
- **Rich Narrative:** Framed for educational planning:
  > *"Early Childhood Scenario: This district has 15% teenage mothers (5 points above the city average) and 12% premature births. Cultural facilities here call for parental support programs."*

**Data Engineering (Pipeline)**
- **Technique:** Direct Macro Aggregation via Point-in-Polygon.
- **Processing:** Since SINASC is robust at the district level, take the lat/long of the searched cultural/education facility, cross it with the District polygon (`ST_Contains`), and return the maternal-child KPIs.

**Where to Get It (100% Certainty)**
- **Macro:** DATASUS — SINASC (Live Birth Information System). An extremely high-quality dataset, extracted via Municipal TabNet or DATASUS FTP. Variables: Mother's Age, Birth Weight, Gestational Weeks, Delivery Type — cross-tabulated by District of residence.

---

### 4.4 Premature Mortality Profile

**Display Approach (UI/UX)**
- **Visualization:** A simple horizontal bar chart, or a waffle chart (dot matrix).
- **Rich Narrative:** The system isolates only premature deaths (ages 30–69, reflecting economic productivity loss and prevention failures):
  > *"The 3 Leading Fatal Threats in the Region: 1st — Cardiovascular Disease (42%); 2nd — External Causes/Violence (20%); 3rd — Cancer (15%)."*

**Data Engineering (Pipeline)**
- **Technique:** Age-Range Filter + ICD-10 Categorization.
- **Processing:** Simple ETL grouping thousands of disease codes (ICD-10) into WHO's macro "Chapters," then spatially linking the district to the searched facility.

**Where to Get It (100% Certainty)**
- **Macro:** DATASUS — SIM (Mortality Information System), via TabNet. Filter 1: Age range 30–69. Filter 2: Group by ICD-10 Chapter. Filter 3: District.

---

### 4.5 Primary Care Chronic Tracking

**Display Approach (UI/UX)**
- **Visualization:** A bubble map over Primary Health Units (UBS). The larger/redder the bubble over a UBS, the higher the proportion of hypertensive/diabetic patients monitored there.
- **Rich Narrative:**
  > *"Chronic Care Burden: The primary health unit (UBS) serving this street has 850 diabetics under active monitoring."*

**Data Engineering (Pipeline)**
- **Technique:** Geographic Proxy (Unit-to-Territory Matching).
- **Processing:** SISAB data isn't tied to IBGE polygons — it's tied to the UBS's CNES code. The pipeline attaches the UBS's exact coordinates to its health data. On the frontend, bubbles are rendered around the searched education/culture facility, revealing the surrounding chronic-health burden.

**Where to Get It (100% Certainty)**
- **Micro/Proxy:** SISAB — e-Gestor AB (Ministry of Health's public reporting portal). Select "Citizen Registry" or "Performance Indicators," filter by Municipality → Health Facility/CNES. Returns exact per-unit spreadsheets.

---

### 4.6 Healthcare Accessibility Index (Care Deserts / Isochrones)

**Display Approach (UI/UX)**
- **Visualization:** Isochrone polygons ("walkability blobs"). The map draws an irregular shape showing how far one can walk in 15 minutes from a health post. Census tracts outside these shapes are shaded gray or red.
- **Rich Narrative:**
  > *"Healthcare Desert: 450 elderly residents (IBGE data) live around this School/Cultural Center in an area requiring more than 2 km of walking to reach the nearest health post."*

**Data Engineering (Pipeline)**
- **Technique:** Network Analysis + Spatial Intersection.
- **Processing:**
  1. Take the coordinates (CNES) of all UBS units.
  2. Use a routing API (e.g., OSRM, or pgRouting with OpenStreetMap data) to generate the 15-minute walking polygon.
  3. Run `ST_Intersection` between that polygon and the IBGE Census Tracts to sum the population left "outside" the radius (the desert).

**Where to Get It (100% Certainty)**
- **Coordinates:** CNES — National Registry of Health Establishments (full database via DATASUS FTP, or Open Government Data API — Establishments table with Lat/Long).
- **Road Network:** OpenStreetMap (OSM) — for calculating walkable streets.
- **Population:** IBGE — 2022 Demographic Census (population count by age, at Tract level).

---

## 5. Infrastructure & Storage Strategy (Supabase Free Tier)

Supabase's free tier (500 MB of database storage) is sufficient for a prototype focused on the state of São Paulo — but it demands surgical geoprocessing. **The real risk to the storage quota isn't the volume of health statistics — it's the weight of the geometries in PostGIS.**

Here's how that space gets consumed, and how to optimize it so CulturaEduca runs without bottlenecks:

### Storage Budget Breakdown

| Component | Contents | Estimated Size |
|---|---|---|
| **Featherweight** — DATASUS, CNES & SISAB tables | Aggregated SINAN, SIM, and SINASC indicators for São Paulo's 645 municipalities (or the capital's 96 districts) | < 5 MB |
| CNES registry | ~30,000 statewide health establishments with lat/long + boolean service flags | < 10 MB |
| **Middleweight** — IBGE tables | ~85,000 census tracts statewide; relational table with demographic and sanitation data | ~15–25 MB |
| **The Quota Villain** — Geographic meshes/polygons | Exact `MultiPolygon` geometry for 85,000 census tracts. Raw IBGE shapefiles can exceed 300 MB due to extreme vertex detail (street curves, river outlines) | 300 MB+ (raw) |

### Strategies to Keep the Database Light & Fast

1. **Geometry Simplification** — Before uploading polygons to Supabase, run the IBGE mesh through a tool like Mapshaper (or run `ST_Simplify` locally). Reducing vertex resolution by 80% keeps the map visually identical on the frontend while dropping geometry weight from ~300 MB to ~40 MB.

2. **Separate the Map from the Data** — A common prototyping pattern: don't store polygons in the database at all. Export simplified meshes as GeoJSON files, host them in a bucket (Supabase's free Storage tier gives 1 GB) or serve them directly from the frontend, and keep only the census tract code + health indicators in PostgreSQL. The join between geometric shape and map color happens client-side, in the user's browser.

3. **Spatial Indexes Are Survival Logic** — Supabase's free-tier instance has only 512 MB of RAM. Running `ST_Intersects` (e.g., to find which facilities fall within a district) without a **GIST spatial index** on the geometry column will cause the database to time out.

4. **Scope the Prototype** — If the goal is strictly to validate the concept (e.g., for a thesis/TCC), limiting scope to the São Paulo Metropolitan Region instead of the entire state reduces the base from ~85,000 to ~35,000 census tracts — giving hosting headroom and keeping map rendering smooth.

---

## Key Acronyms & Data Sources Reference

| Acronym | Meaning |
|---|---|
| **LGPD** | Lei Geral de Proteção de Dados — Brazil's General Data Protection Law |
| **SINAN** | Notifiable Diseases Information System (infectious/vector-borne disease cases) |
| **SIM** | Mortality Information System |
| **SINASC** | Live Birth Information System |
| **IBGE** | Brazilian Institute of Geography and Statistics (Census data, tract-level geometry) |
| **CNES** | National Registry of Health Establishments (facility coordinates & attributes) |
| **SIH** | Hospital Information System (inpatient admissions/procedures) |
| **SIA** | Outpatient Information System (ambulatory procedures) |
| **SISAB** | Primary Care Information System (chronic condition tracking) |
| **CBO** | Brazilian Occupation Classification (workforce roles) |
| **CID-10 / ICD-10** | International Classification of Diseases, 10th revision |
| **TabNet** | DATASUS's public tabulation/query portal |
| **PostGIS** | Spatial extension for PostgreSQL |
| **GIST** | Generalized Search Tree — spatial index type used for `ST_Intersects`/`ST_Within` performance |
| **OSRM / pgRouting** | Routing engines used to compute walking/driving isochrones over OpenStreetMap data |
