# thesis-prototype

Prototype for my undergraduate thesis: an improved health data layer, with spatial data storytelling, for the [CulturaEduca](https://culturaeduca.cc/) platform. It maps 6,687 health facilities of the São Paulo Metropolitan Region (RMSP) and, for each one, writes a short text that relates the facility to the territory around it, telling every number with its scale and the caveats it needs.

The RMSP is the development example; the integration into CulturaEduca will use national data.

**Live prototype:** <https://thesis-prototype-rdiz.onrender.com/>

## What is in it

- **Map** (`public/index.html`): every facility, filtered by type and by public or SUS network, sized by beds, hollow when the position is approximate.
- **Facility page** (`public/facility.html`), in tabs:

  | Tab | Contents | Scale |
  |---|---|---|
  | Reading the territory | the generated text and a key to its scale colours | all, each figure marked |
  | Record | CNES record, beds, staff, admissions, in-hospital deaths with a funnel plot | facility |
  | Surroundings data | census of the radius against municipality and region; 1 km peer comparison | radius |
  | Health indicators | tuberculosis, dengue, leptospirosis, births, premature mortality | district (capital) and municipality |
  | Nearby facilities | other facilities in the radius, by category | radius |

  The radius is adjustable, and the map banner expands to a full map with an indicator choropleth. Clicking a sentence opens the card or map layer with its data. The open tab is kept in the URL hash (`facility.html?cnes=2786826#health`).
- **Relations page** (`public/relations.html`): how tuberculosis, dengue, leptospirosis and teenage pregnancy relate to income, housing and sanitation, by municipality and by district of São Paulo city (static data in `public/data/relations.json`).
- **Storytelling service** (`backend-core/`): the C++17 service that writes the text (see [How the text is made](#how-the-text-is-made)).

## Repository layout

| Path | Contents |
|---|---|
| `public/` | Frontend: vanilla JS, HTML, CSS and Leaflet, no build step |
| `backend-core/` | C++ storytelling service: facts, caveat rules, templates, verifier, tests and evaluation |
| `database/migrations/` | Database schema, read API functions and access policies (001 to 020) |
| `database/seeders/` | Loaders for the cleaned CSVs and the tract geometry |
| `database/geocoding/` | Address geocoding of facilities with CNEFE 2022, distance from homes to primary care |
| `database/tabnet/` | Reproducible DATASUS and SMS-SP TabNet downloads, São Paulo district indicators |
| `database/reference/` | Batch computations: 1 km surroundings of every facility, catchments, hospital mortality |
| `etl/` | Cleaning of the raw CNES, SIH, IBGE and TabNet files into the CSVs in `data/` |
| `analysis/` | Statistical analyses: territorial typology, outcome relations, scale decomposition |
| `data/` | Cleaned and computed CSVs loaded into the database |
| `deploy/` | Files used by the frontend's Docker image |

## Running locally

### Frontend

1. Copy `public/js/config.example.js` to `public/js/config.js` and fill in the Supabase project URL and anon key.
2. Serve `public/` over HTTP (ES modules do not load from `file://`) and open <http://localhost:8000>:

   ```bash
   python3 -m http.server 8000 --directory public
   ```

### Storytelling service

Needs CMake ≥ 3.16, a C++17 compiler and `libcurl4-openssl-dev`; the other libraries are fetched by CMake.

```bash
cmake -S backend-core -B backend-core/build
cmake --build backend-core/build -j
ctest --test-dir backend-core/build --output-on-failure
```

Run it against the database, then add `export const STORY_API_URL = 'http://localhost:8080';` to `public/js/config.js`:

```bash
export SUPABASE_URL=... SUPABASE_ANON_KEY=... STORY_CONFIG_DIR=backend-core/config
backend-core/build/storyteller serve                          # GET /narrative?cnes=&radius=&lang=pt|en&public_only=0|1
backend-core/build/storyteller payload 2786826 1000 > f.json  # freeze a facility's data
backend-core/build/storyteller narrate f.json pt --text        # tell it offline
```

Without `STORY_API_URL` the page works without the text.

## Deploying (Render)

Two **Web Services**, both with runtime **Docker**:

| Service | Root directory | Environment variables |
|---|---|---|
| Frontend | repository root | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `STORY_API_URL` (the service's URL) |
| Storytelling | `backend-core` | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `ALLOWED_ORIGIN` (the frontend's URL) |

The frontend container writes `js/config.js` from its variables at start-up (`deploy/write-config.sh`) and refuses to start if the Supabase ones are missing. Render supplies `PORT`. To try the frontend image locally:

```bash
docker build -t thesis-prototype .
docker run --rm -p 10000:10000 -e SUPABASE_URL=... -e SUPABASE_ANON_KEY=... thesis-prototype
```

## Setting up the database

Needs a Supabase project with PostGIS, with the Data API enabled (Project Settings → Data API) and `public` as the exposed schema. Put `DATABASE_URL=postgresql://...` in `.env` (git-ignored); the scripts read it, and `eval "$(python3 -I database/pgenv.py)"` sets the `psql` variables without the password appearing on the command line.

1. Load the census tract outlines from the IBGE mesh, with a light, gap-free simplification:

   ```bash
   python3 database/seeders/load_geometry.py ~/Downloads/SP_setores_CD2022.json --tolerance 10
   ```

2. Apply the migrations in numeric order, except 004, which goes after 008. They can be re-run safely. The ones that need data (012 to 015, 019 and 020) give the `\copy` command for it in their header.
3. Load the cleaned CSVs: `python3 database/seeders/seed.py` (add `--replace` to reload).
4. Apply 018 again at the end, and whenever the Data API is re-enabled: enabling it restores write privileges to the public roles.

Migration 017 keeps the cost of a page visit independent of the size of the tract table. The parts of the surroundings that read every tract (crowding threshold, census × access join, municipal and regional sums) live in tables that statement-level triggers rebuild after any load. `select refresh_surroundings_tables();` does it by hand.

## Updating the data

The update is manual. Nothing in the repository downloads or recomputes the data on a schedule. When a source publishes a new version, download it and run the steps below in order; each step reads the outputs of the previous ones.

| Source | Where | Pace |
|---|---|---|
| CNES (establishments, beds, teams) | DATASUS, national monthly base | monthly |
| SIH, SINAN, SINASC, SIM | DATASUS and SMS-SP TabNet (downloaded by the scripts) | during the year |
| Census 2022 aggregates and income | IBGE, national files | once a decade |
| CNEFE 2022 addresses | IBGE, one file per municipality (the 39 of the RMSP) | once a decade |

1. **TabNet:**

   ```bash
   python3 -I database/tabnet/fetch_tabnet.py
   python3 database/tabnet/fetch_sih_hospitals.py
   python3 database/tabnet/build_district_indicators.py
   ```

   `fetch_sih_hospitals.py` makes four queries per hospital, about an hour for the RMSP.
2. **Cleaning:** `etl/limpeza.py` (CNES and SIH), `etl/limpeza_ibge.py` (Census), `etl/limpeza_datasus.py` (municipal indicators) and `python3 -I etl/limpeza_renda.py <income zip>`. The first three read their input paths from constants at the top of each file.
3. **Geocoding and access:**

   ```bash
   python3 database/geocoding/geocode_cnefe.py --cnefe-dir ~/Downloads/cnefe_rmsp
   python3 database/geocoding/compute_access.py --cnefe-dir ~/Downloads/cnefe_rmsp
   ```

   Then `python3 database/seeders/seed.py --replace`.
4. **Batch computations:**

   ```bash
   database/reference/build_surroundings.sh 3        # 1 km surroundings of every facility (~30 min)
   python3 -I analysis/typology.py                   # territorial types
   python3 -I analysis/outcome_relations.py          # relations page and district models
   python3 database/reference/compute_catchment.py --cnefe-dir ~/Downloads/cnefe_rmsp \
           --cnes-dir ~/Downloads/BASE_DE_DADOS_CNES_202608
   python3 database/reference/compute_hospital_mortality.py
   ```

5. **Load:** load the computed CSVs with the `\copy` commands in migrations 012 to 015, 019 and 020. The triggers of 017 rebuild the precomputed tables.

## How the text is made

The service follows the classic data-to-text pipeline.

1. **Facts.** It reads the same Supabase functions as the frontend and extracts facts at each scale: unit, radius, catchment, district, municipality, region.
2. **Caveats and plan.** It applies the caveat rules in `backend-core/config/rules.json`, which suppress, qualify or disclose what each number needs, and plans a fixed schema: a lead, then the unit, the surroundings and the outcomes.
3. **Templates.** It fills the bilingual templates in `config/pt.json` and `config/en.json`. Numbers only enter the text through slots tied to a datum and its scale.
4. **Verification.** A verifier runs eight checks (numbers, plan, facts, caveats, scale, direction, causal wording, length). A text that fails is not served: the response keeps its facts, drops the text and sets `withheld`, and the page shows only the cards.

Two parts carry most of the domain logic:

- **In-hospital deaths.**
  - Deaths are told against those each hospital's patients would predict, by indirect standardisation over diagnosis group, age group and admission type, read on a funnel plot (`database/reference/compute_hospital_mortality.py`).
  - When the case mix moves the expected rate far from the regional one, the text says what weighs most, from a Shapley split of the difference.
  - The text never calls a hospital good or bad and always says what the adjustment leaves out (rules C23 to C24).
- **Need and supply in primary care.**
  - These are told on each public unit's estimated catchment. Residents are split among the units nearest their homes by a Huff model with distance decay, within catchments that widen where units are sparse (`compute_catchment.py`).
  - Supply is counted in Family Health team equivalents and read against the PNAB range of 2,000 to 3,500 people per team.

## Evaluation

The evaluation sample (`backend-core/evaluation/sample.py`) draws 40 facilities by stratum with a fixed seed. `sample_need.py` adds 10 public primary care units that trigger the need-against-supply sentence. Their frozen payloads are in `backend-core/evaluation/fixtures/`; the unit tests never use them. Results go to `backend-core/evaluation/results/`.

- **Fault injection:** `storyteller mutate FIXTURE...` plants seven kinds of error in every text and counts what the verifier and a numbers-only check catch.
- **Sensitivity:** `storyteller sensitivity FIXTURE...` perturbs the selection weights and thresholds by ±50%.
- **Free LLM** (offline only; the site always uses the templates): in `backend-core/evaluation/llm/`, `run_llm.py` asks a local model (Gemma 4 E4B through Ollama, or any OpenAI-compatible endpoint) to write the text from the same content plan, freely or by rewriting the templates. `score_llm.py` runs the same verifier on the answers.
- **Human annotation** (10 facilities, about 45 minutes per annotator): in `backend-core/evaluation/annotation/`, `build_tasks.py` writes the tasks (`STORYTELLER=path/to/storyteller python3 .../build_tasks.py`).
  - Annotators open `annotate.html`. For every sentence they check the data and say whether it is relevant; then they mark the left-out facts that should have been told.
  - 2 of the 10 units show the free LLM text, without saying so.
  - The instructions are in `GUIA.md`, in Portuguese like the texts.
  - `agreement.py anotacao_*.json` computes the scores and the agreement.

## Keeping the Supabase project awake

Supabase pauses free-tier projects after a week without activity. `.github/workflows/supabase-keepalive.yml` reads one row through the REST API every Monday and Thursday. It needs the repository secrets `SUPABASE_URL` and `SUPABASE_ANON_KEY` (Settings → Secrets and variables → Actions).

GitHub Actions only runs it from the default branch, and not at all while the GitHub account is locked over billing. In that case the runs fail at once with "The job was not started because your account is locked due to a billing issue". Any external scheduler that sends the same request works as a replacement.

If the project is already paused, restore it from the Supabase dashboard.
