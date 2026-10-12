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

## Setting up the database

Requires a Supabase project with PostGIS and the census tract polygons already loaded into `setores_censitarios_grande_sp`. Put `DATABASE_URL=postgresql://...` in `.env`, then:

```bash
psql "$DATABASE_URL" -f database/migrations/001_frontend_read_api.sql
psql "$DATABASE_URL" -f database/migrations/002_geocoded_coordinates.sql
psql "$DATABASE_URL" -f database/migrations/003_corrected_coordinates.sql
psql "$DATABASE_URL" -f database/migrations/004_reapply_read_only_grants.sql
python3 database/seeders/seed.py          # add --replace to reload
```

The Data API must be enabled in the Supabase dashboard (Project Settings → Data API) with `public` as the exposed schema. Enabling it restores write privileges to the public roles, so re-run migration 004 afterwards.

The seeder also applies `database/geocoding/geocoded_facilities.csv`, which gives a position to facilities that have no usable coordinate in CNES. To regenerate it, download the CNEFE 2022 municipal files for the 39 municipalities from IBGE and run:

```bash
python3 database/geocoding/geocode_cnefe.py --cnefe-dir ~/Downloads/cnefe_rmsp
python3 database/geocoding/arbitrate_sample.py   # optional: three-way check against OpenStreetMap
python3 database/seeders/seed.py --replace
```

## Layout

| Path | Contents |
|---|---|
| `public/` | Frontend: map page (`index.html`) and facility page (`facility.html`) |
| `database/migrations/` | SQL for access policies and the read API functions |
| `database/seeders/` | Loader for the cleaned CSVs |
| `limpeza.py`, `limpeza_ibge.py` | ETL from the raw CNES, SIH and IBGE files to the cleaned CSVs |
| `database/geocoding/` | Address geocoding of facilities with CNEFE 2022, and its validation |
| `deploy/` | Files used by the Docker image |
