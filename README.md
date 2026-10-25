# thesis-prototype

Prototype for my undergraduate thesis: a health data layer with spatial data storytelling for the CulturaEduca platform, covering the São Paulo Metropolitan Region.

## Running the frontend

The frontend is static (vanilla JS and Leaflet, no build step) and reads from Supabase.

1. Copy `public/js/config.example.js` to `public/js/config.js` and fill in the project URL and anon key.
2. Serve the `public/` folder over HTTP (ES modules do not load from `file://`):

   ```bash
   python3 -m http.server 8000 --directory public
   ```

3. Open <http://localhost:8000>.

## Deploying (Render)

The root `Dockerfile` serves `public/` with nginx. Create the service as a **Web Service** with runtime **Docker**, branch `main`, and set two environment variables in the Render dashboard:

| Variable | Value |
|---|---|
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` |
| `SUPABASE_ANON_KEY` | the project's anon (public) key |

The container writes `js/config.js` from them at start-up (`deploy/write-config.sh`) and refuses to start if either is missing. Render supplies `PORT`.

To try the image locally:

```bash
docker build -t thesis-prototype .
docker run --rm -p 10000:10000 -e SUPABASE_URL=... -e SUPABASE_ANON_KEY=... thesis-prototype
```

## Storytelling service (`backend-core/`)

A C++17 service that writes the short "Reading the territory" text on the facility page. It reads the same Supabase functions as the frontend, extracts facts at each scale (unit, radius, district, municipality, region), applies the caveat rules in `config/rules.json`, fills the bilingual templates in `config/pt.json` and `config/en.json`, and verifies the result before returning it. Numbers only enter the text through slots, never through the templates.

Build and test (needs CMake ≥ 3.16, a C++17 compiler and `libcurl4-openssl-dev`; other libraries are fetched by CMake):

```bash
cmake -S backend-core -B backend-core/build
cmake --build backend-core/build -j
ctest --test-dir backend-core/build --output-on-failure
```

Run it locally against the database, then add `export const STORY_API_URL = 'http://localhost:8080';` to `public/js/config.js`:

```bash
export SUPABASE_URL=... SUPABASE_ANON_KEY=... STORY_CONFIG_DIR=backend-core/config
backend-core/build/storyteller serve                          # GET /narrative?cnes=&radius=&lang=pt|en&public_only=0|1
backend-core/build/storyteller payload 2786826 1000 > f.json  # freeze a facility's data as a fixture
backend-core/build/storyteller narrate f.json pt --text        # tell it offline
backend-core/build/storyteller mutate backend-core/evaluation/fixtures/*.json   # fault-injection table
```

Deploy it on Render as a second **Web Service** (runtime Docker, root directory `backend-core`) with `SUPABASE_URL`, `SUPABASE_ANON_KEY` and `ALLOWED_ORIGIN` (the frontend's URL), and give the frontend service `STORY_API_URL` with the service's URL. Without `STORY_API_URL` the page works as before, without the text.

The evaluation sample (`backend-core/evaluation/sample.py`) draws facilities by stratum with a fixed seed; their frozen payloads are in `backend-core/evaluation/fixtures/` and are never used by the unit tests.

## Keeping the Supabase project awake

Supabase pauses free-tier projects after a week without activity. The workflow `.github/workflows/supabase-keepalive.yml` reads one row through the REST API every Monday and Thursday. It needs the repository secrets `SUPABASE_URL` and `SUPABASE_ANON_KEY` (Settings → Secrets and variables → Actions), and it only runs once it is on the default branch. A failed run usually means the project is already paused: restore it from the Supabase dashboard.

## Setting up the database

Requires a Supabase project with PostGIS and the census tract polygons already loaded into `setores_censitarios_grande_sp`. To reload the tract outlines from the original IBGE mesh with a light, gap-free simplification, run `python3 database/seeders/load_geometry.py ~/Downloads/SP_setores_CD2022.json --tolerance 10`. Put `DATABASE_URL=postgresql://...` in `.env`, then:

```bash
psql "$DATABASE_URL" -f database/migrations/001_frontend_read_api.sql
psql "$DATABASE_URL" -f database/migrations/002_geocoded_coordinates.sql
psql "$DATABASE_URL" -f database/migrations/003_corrected_coordinates.sql
psql "$DATABASE_URL" -f database/migrations/005_sector_and_sus.sql
psql "$DATABASE_URL" -f database/migrations/006_public_network_filter.sql
psql "$DATABASE_URL" -f database/migrations/007_territory_indicators.sql
psql "$DATABASE_URL" -f database/migrations/008_census_denominators.sql
psql "$DATABASE_URL" -f database/migrations/004_reapply_read_only_grants.sql
python3 database/seeders/seed.py          # add --replace to reload
```

The Data API must be enabled in the Supabase dashboard (Project Settings → Data API) with `public` as the exposed schema. Enabling it restores write privileges to the public roles, so re-run migration 004 afterwards.

The seeder also applies `database/geocoding/geocoded_facilities.csv`, which gives a position to facilities that have no usable coordinate in CNES. To regenerate it, download the CNEFE 2022 municipal files for the 39 municipalities from IBGE and run:

```bash
python3 database/geocoding/geocode_cnefe.py --cnefe-dir ~/Downloads/cnefe_rmsp
python3 database/geocoding/arbitrate_sample.py   # optional: three-way check against OpenStreetMap
python3 database/geocoding/compute_access.py --cnefe-dir ~/Downloads/cnefe_rmsp   # distance from homes to primary care
python3 database/seeders/seed.py --replace
```

## Layout

| Path | Contents |
|---|---|
| `public/` | Frontend: map page (`index.html`) and facility page (`facility.html`) |
| `database/migrations/` | SQL for access policies and the read API functions |
| `database/seeders/` | Loader for the cleaned CSVs |
| `limpeza.py`, `limpeza_ibge.py`, `limpeza_datasus.py` | ETL from the raw CNES, SIH, IBGE and DATASUS TabNet files to the cleaned CSVs |
| `database/geocoding/` | Address geocoding of facilities with CNEFE 2022, and its validation |
| `deploy/` | Files used by the Docker image |
| `backend-core/` | C++ storytelling service: facts, caveat rules, templates, verifier, tests and evaluation |
| `database/tabnet/` | Reproducible DATASUS and SMS-SP TabNet downloads, and the São Paulo district indicators |
