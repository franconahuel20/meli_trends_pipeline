# meli_trends_pipeline

Mercado Libre search-trends pipeline. Every day it pulls the trending keywords of the
selected Mercado Libre subcategories (Argentina, Brazil, Chile, Colombia and Mexico),
stores them in a MinIO data lake, tags each keyword with the **brand** and **character /
franchise** it mentions, builds the final analytical table with **dbt** and serves it to
**Apache Superset**. **Dagster** orchestrates everything.

One command starts the whole platform, on Ubuntu, Debian or Windows:

```bash
docker compose up -d
```

---

## Contents

1. [Architecture](#1-architecture)
2. [Requirements](#2-requirements)
3. [Quick start](#3-quick-start)
4. [Services](#4-services)
5. [Configuration](#5-configuration)
6. [The Dagster pipeline](#6-the-dagster-pipeline)
7. [Brand and character matching](#7-brand-and-character-matching)
8. [Data model](#8-data-model)
9. [Superset dashboards](#9-superset-dashboards)
10. [Operations](#10-operations)
11. [Troubleshooting](#11-troubleshooting)
12. [Project structure](#12-project-structure)

---

## 1. Architecture

```text
data/input/*.xlsx ──► PostgreSQL reference tables (brands, characters, subcategories)
                                  │
Mercado Libre API ──► L1  MinIO  raw CSV          L1_delta/revenue_research_meli/trends/
   /trends/{site}/{category}      │
                       L2  MinIO  clean parquet    L2_databases/.../date_dte=YYYY-MM-DD/
                                  │
                       L3  brand/character matching
                           ├─► MinIO parquet       L3_standardization/.../date_dte=YYYY-MM-DD/
                           └─► PostgreSQL          stg_revenue_research_meli.meli_trends_l3
                                  │
                       dbt (incremental)  ──► mdm_revenue_research_meli.trends ──► Superset
                                                                          (dashboards as code,
                                                                           metadata in superset-db)
```

| Component | Role |
|---|---|
| Dagster 1.13 | Orchestration: assets, daily schedule, retries, lineage, run history (UI on port 3030) |
| PostgreSQL 15 | Reference tables, staging table and final dbt model (database `snowflake_dev`) |
| MinIO | S3-compatible data lake (L1 / L2 / L3) |
| dbt 1.11 | Final analytical model with data tests (run by Dagster, tests shown as asset checks) |
| Apache Superset 4.1 | Dashboards, provisioned from `superset/dashboard/` on start; metadata in its own PostgreSQL (`superset-db`) |
| Dozzle / Adminer | Container logs and a lightweight database browser |

## 2. Requirements

| | Ubuntu / Debian | Windows 10 / 11 |
|---|---|---|
| Docker | Docker Engine 24+ with the Compose v2 plugin (`docker compose`, not the old `docker-compose`) | Docker Desktop with the WSL 2 backend |
| Memory | 4 GB free for containers (the stack uses about 1 GB idle) | Same; check *Settings → Resources* in Docker Desktop |
| Disk | About 4 GB for images and data | Same |

Install Docker Engine from Docker's official repository (the distribution packages are often
too old, and Debian does not ship Compose v2):

```bash
curl -fsSL https://get.docker.com | sh
```

```bash
sudo usermod -aG docker $USER
```

Log out and back in after the second command so `docker` works without `sudo`. Check the versions with:

```bash
docker compose version
```

You also need Mercado Libre API credentials (`client_id` and `client_secret` of an app created at
<https://developers.mercadolibre.com>).

## 3. Quick start

**1. Get the code and create your `.env`**

Linux:

```bash
cp .env.example .env
```

Windows (PowerShell):

```powershell
Copy-Item .env.example .env
```

**2. Set your Mercado Libre credentials** in `.env`:

```env
ML_CLIENT_ID=your_client_id
ML_CLIENT_SECRET=your_client_secret
```

Every other value has a working default. For anything beyond a local machine, also change
`SUPERSET_SECRET_KEY` and the passwords.

**3. Start everything**

```bash
docker compose up -d
```

The first start builds two images (Dagster and Superset, a few minutes). Then:

1. PostgreSQL, MinIO and the Dagster metadata database start and become healthy.
2. The `meli-datalake` bucket is created.
3. The Dagster code server, UI and daemon start.
4. **The pipeline runs automatically once**, because the final table does not exist yet (the
   `meli_trends_first_run_sensor`). It takes about two minutes.
5. From then on it runs every day at 23:00, Buenos Aires time.

Follow the run in Dagster (<http://localhost:3030>, *Runs*). When it finishes, the final table
`mdm_revenue_research_meli.trends` is ready and the dashboard **Revenue Research - Mercado Libre
Trends** (created automatically, section 9) shows it. Check the containers with:

```bash
docker compose ps
```

## 4. Services

All ports are published on `127.0.0.1` only (see `HOST_BIND_IP`).

| Service | URL | Credentials (defaults) |
|---|---|---|
| Dagster UI | <http://localhost:3030> | none |
| Superset | <http://localhost:8088> | `admin` / `admin` |
| MinIO console | <http://localhost:9001> | `minioadmin` / `minioadmin` |
| MinIO S3 API | <http://localhost:9000> | same as the console |
| PostgreSQL | Not a web page: host `localhost`, port `5434`, database `snowflake_dev` (SQL clients only) | `postgres` / `postgres` |
| Adminer | <http://localhost:8082> (server `postgres`) | PostgreSQL credentials |
| Dozzle (logs) | <http://localhost:8888> | none |

### Connecting to PostgreSQL

PostgreSQL speaks its own protocol, not HTTP: opening `localhost:5434` in a browser returns an
empty response. Use one of these instead:

- **Browser (Adminer)**: open <http://localhost:8082> and log in with *System* `PostgreSQL`,
  *Server* `postgres` (the container name, not `localhost`), *Username* `postgres`,
  *Password* `postgres`, *Database* `snowflake_dev`.
- **Desktop client (DBeaver, pgAdmin, DataGrip, VS Code)**: host `localhost`, port **5434**
  (not 5432, which belongs to any PostgreSQL installed on your machine), database
  `snowflake_dev`, user `postgres`, password `postgres`, SSL disabled.
- **Terminal**:

  ```bash
  psql -h localhost -p 5434 -U postgres -d snowflake_dev
  ```

The final table is `mdm_revenue_research_meli.trends`. A client running inside another Docker
network, or on another machine, cannot reach the port because it is published on `127.0.0.1`
only; set `HOST_BIND_IP=0.0.0.0` in `.env` if you really need that.

## 5. Configuration

Everything is configured through `.env` (read by Docker Compose; every variable has a default).

| Variable | Default | Purpose |
|---|---|---|
| `ML_CLIENT_ID`, `ML_CLIENT_SECRET` | — | Mercado Libre application credentials (**required**) |
| `ML_GRANT_TYPE` | `client_credentials` | OAuth grant used to get the access token |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | `snowflake_dev`, `postgres`, `postgres` | Analytics database (applied when its volume is created) |
| `POSTGRES_EXTERNAL_PORT` | `5434` | Host port of PostgreSQL (5434 avoids clashing with a local PostgreSQL) |
| `DAGSTER_POSTGRES_PASSWORD` | `dagster` | Dagster metadata database |
| `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `MINIO_BUCKET` | `minioadmin`, `minioadmin`, `meli-datalake` | Data lake credentials (password ≥ 8 characters) and bucket |
| `SUPERSET_SECRET_KEY`, `SUPERSET_ADMIN_USERNAME`, `SUPERSET_ADMIN_PASSWORD` | local default, `admin`, `admin` | Superset |
| `SUPERSET_DB_PASSWORD` | `superset` | Superset metadata database (applied when its volume is created) |
| `SUPERSET_DASHBOARDS_IMPORT` | `missing` | `missing`: create the versioned dashboards only if they do not exist (UI edits are kept); `overwrite`: replace them with the repository version on every start |
| `PIPELINE_TIMEZONE` | `America/Argentina/Buenos_Aires` | Snapshot date and schedule time zone |
| `PIPELINE_SCHEDULE_CRON` | `0 23 * * *` | Daily schedule |
| `PIPELINE_RUN_ON_STARTUP` | `true` | Run once after the first `docker compose up -d` |
| `MELI_SELECTED_SUBCATEGORIES_ONLY` | `true` | Only subcategories with `id_seleccionado = 1` (756 of 1,389) |
| `MELI_MAX_WORKERS` | `4` | Parallel calls to the Mercado Libre API |
| `MATCHING_FUZZY_ENABLED` | `true` | Typo correction for character names (section 7) |
| `HOST_BIND_IP` | `127.0.0.1` | Interface for every published port; `0.0.0.0` exposes them to your network |
| `DAGSTER_PORT`, `SUPERSET_PORT`, `MINIO_API_PORT`, `MINIO_CONSOLE_PORT`, `DOZZLE_PORT`, `ADMINER_PORT` | `3030`, `8088`, `9000`, `9001`, `8888`, `8082` | Host ports |

After editing `.env`, apply the change with `docker compose up -d`.

## 6. The Dagster pipeline

The pipeline is a graph of [software-defined assets](https://docs.dagster.io/guides/build/assets)
in the code location `meli_trends_pipeline` (package `meli_trends_pipeline/`).

| Asset | Group | What it does |
|---|---|---|
| `standardization_revenue_research_meli/brands` | reference_data | Loads `data/input/brands.xlsx` into a typed table |
| `standardization_revenue_research_meli/characters` | reference_data | Loads `characters.xlsx` (owner, franchise N1–N3, content, curator comments) |
| `standardization_revenue_research_meli/mercado_libre_subcat` | reference_data | Loads `mercado_libre_subcat.xlsx` |
| `meli_datalake/trends_l1_raw` | trends | Calls the trends API for every selected subcategory (parallel, retries, token refresh) and writes the raw CSV to L1 |
| `meli_datalake/trends_l2_clean` | trends | Trims values, drops empty keywords and duplicates, writes parquet to L2 |
| `stg_revenue_research_meli/meli_trends_l3` | trends | Brand and character matching (section 7) and spaCy lemmas, writes parquet to L3 and loads the staging table |
| `trends` | analytics | dbt model `mdm_revenue_research_meli.trends` plus 15 data tests (asset checks) |

- **Job** `meli_trends_pipeline_job` materializes all assets in order; each step retries twice
  with exponential backoff.
- **Schedule** `meli_trends_daily_schedule`: `PIPELINE_SCHEDULE_CRON` in `PIPELINE_TIMEZONE`,
  enabled by default.
- **Sensor** `meli_trends_first_run_sensor`: runs the job after the first start when the final
  table has never been built (at most one attempt per day).
- **Idempotent**: the snapshot date comes from the pipeline time zone, and re-running a day
  replaces that day in staging and in the final table, so history is kept without duplicates.
- **Safe extraction**: if more than half of the API calls fail, the run fails instead of
  publishing partial data. Missing or placeholder credentials stop it with a clear message.
- **Self-healing history**: the L3 step also re-matches every day kept in L2 that is missing from
  the staging table (for example after its layout changed), and dbt refreshes exactly the days
  that were (re)loaded into staging. If the columns of the final table change, the dbt asset
  rebuilds it with a full refresh on its own.

After changing a word list or a reference Excel file, re-match the whole history (no API calls):
*Assets → stg_revenue_research_meli/meli_trends_l3 → Materialize selected* with the run config
`reprocess_history: true`, together with `trends`; or from a terminal:

```bash
docker compose exec dagster-code dagster asset materialize -m meli_trends_pipeline.definitions --select "stg_revenue_research_meli/meli_trends_l3,trends" --config-json '{"ops": {"stg_revenue_research_meli__meli_trends_l3": {"config": {"reprocess_history": true}}}}'
```

Run it manually from the UI (*Jobs → meli_trends_pipeline_job → Materialize all*) or from a
terminal:

```bash
docker compose exec dagster-webserver dagster job launch --job meli_trends_pipeline_job --workspace /opt/dagster/dagster_home/workspace.yaml
```

> In Git Bash on Windows, prefix that command with `MSYS_NO_PATHCONV=1` so the container path
> is not rewritten. PowerShell and CMD do not need it.

## 7. Brand and character matching

The L3 step decides, for every keyword, which brand and which character it mentions. A wrong
match inflates "Branded" share and pollutes the franchise and owner charts, so the matcher is
built to **prefer missing a match over inventing one**. The code is in
`meli_trends_pipeline/matching/` and has no Dagster dependency.

### How a keyword is matched

Keywords and reference names go through the same normalization: lowercase, accents removed
(but `ñ` kept, so "cañón" never becomes the brand "canon"), punctuation removed. Then:

| Method | Example | Guard against false positives |
|---|---|---|
| `exact` | "zapatillas **nike**" | Whole words only: "luca" never matches inside "peluca", "rico" never inside "eléctrico" |
| `compact` | "**spider-man**" → Spiderman, "**hotwheels**" → Hot Wheels | Never starts or ends with a stopword ("el gato" ≠ Elgato), never only product words ("pro max" ≠ Promax); a split spelling ("go pro") needs the joined one ("gopro") in the same day's data |
| `variant` | "peluche **minion**" → Minions | Characters only ("pumas" is a club, not Puma); for one-word names the listed form must also appear that day ("eternal" ≠ Eternals) |
| `fuzzy` | "peluche **stich**" → Stitch, "rayo **macqueen**" → Rayo McQueen | Characters only, one letter, first and last letters kept, never a real word ("switch" ≠ Stitch), and the correct spelling must be at least twice as frequent in the day's data |
| brand plural (`variant`) | "**legos** usados" → Lego, "short **nikes**" → Nike | The brand must appear that day and the plural must not be a word of its own ("googles" are swimming goggles, "toppers" cake toppers, "pumas" the club) |

### Brand rules

`meli_trends_pipeline/matching/wordlists/brand_rules.txt` adds curated ways of naming a brand,
one per line: `alias | Brand | optional categories`.

| Kind | Examples |
|---|---|
| Product lines | "**iphone** 15" → Apple, "**ps5** usado" → Playstation, "**galaxy s24** ultra" → Samsung (`galaxy #`: `#` is a model code, so "proyector galaxy" is not Samsung), "**chromecast**" → Google, "**kindle**" → Amazon, "**ryzen** 5" → AMD, "**meta quest** 3" → Meta |
| Brands missing from `brands.xlsx` | Similac, Enfamil, Aptamil, Pampers, Maybelline, Bravecto, Segway, Gymshark… |
| Everyday words that are a brand **inside their category** | "raqueta **wilson**" (Deportes y Fitness) → Wilson, but not "separadores wilson jones"; "amplificador **marshall**", "**boss** katana" (Instrumentos Musicales); "leche **nido**" (Bebés); "camioneta **ram**" (Autos) but not "memoria ram"; "**switch**" is Nintendo only in Consolas y Videojuegos |
| Display names | `hp` → HP, `dji` → DJI; any other all-lowercase brand is shown in title case ("new era" → New Era) |

A rule replaces the master-list entry with the same alias. When a keyword names a master-list
brand and a product line, the brand comes first ("notebook dell core i7" → Dell, second brand
Intel).

On top of that:

- **Ambiguous names.** A reference name that is also an everyday word, first name, place or
  generic phrase ("power", "polo", "saxo", "roller", "lisa", "power bank") is ambiguous. An
  ambiguous **brand** is never matched. An ambiguous **character** only matches when the keyword
  also names its franchise or owner: "anna **frozen**" → Anna, but "muñeca anna" → nothing. The
  comments column of `characters.xlsx` (e.g. "Ariel producto para lavar") marks one-word
  characters as ambiguous too.
- **Units.** A brand that is also a unit is ignored after a number: "impresora **hp**" → HP, "motor
  2 **hp**" → nothing.
- **Overlaps.** The longest match wins. A match nested inside an unrelated match of the other
  kind is dropped ("jessica simpson perfume" is the brand, not the character Simpson), unless the
  brand owns the franchise ("lego friends" → brand Lego and character Lego Friends).

Each row records how it was matched: `brand_match_method_str`, `brand_match_score_int` and
`brand_matched_text_str` (and the same for characters), so any match can be audited.

### Measured on real data

**Brand rules (2026-10-30).** On the 83,418 rows of the 2026-10-23, 10-27 and 10-30 snapshots,
rows with a brand went from 14,287 (17.1%) to 18,463 (22.1%), "Branded" from 19.4% to 24.3%, and
no previous brand match was lost. Every rule was reviewed on samples of its matches. Compared
with the business `trends.csv` extract of 2026-10-30, the brands that extract still has and the
pipeline does not are almost all false positives there ("pro", "plus", "azul", "fantasia", "lp",
"rca", "it", "arena" for cat litter, "ram" for memory). Most searches are generic ("fideos",
"casa para gato"), so most rows legitimately have no brand.

On the 27,631 trend rows of the 2026-10-22 snapshot, comparing the previous Airflow matcher
(substring search plus `token_set_ratio` ≥ 85/90) with the new one on the same keywords, and
reviewing a random sample of 60 matches of each kind:

| | Previous matcher | New matcher |
|---|---|---|
| Rows flagged "Branded" | 30.1% | 19.4% |
| False positives in 60 brand matches | 18 (e.g. "ram", "a", "pro", "plus", "saxo", "gaucho") | 0 (1 unclear) |
| False positives in 60 character matches | 26 (e.g. "eléctrico" → Rico, "inalámbrico" → Nala, "peluca" → Luca) | 0 |

Known remaining limits: a trusted character that is also a product line ("razer **wolverine**",
"ping pong **loki**") still matches, and recall is lower on purpose (for example "power a" and
other brands written as everyday words are not tagged).

### Tuning

The word lists are plain text in `meli_trends_pipeline/matching/wordlists/` (one normalized
term per line):

| File | Effect |
|---|---|
| `brand_rules.txt` | Product lines, missing brands, category-restricted brands and display names (see *Brand rules*) |
| `ambiguous_aliases.txt` | Names that are everyday words: never a brand; a character only with franchise context |
| `trusted_brands.txt`, `trusted_characters.txt` | Override every ambiguity rule for that kind ("apple", "stitch") |
| `generic_terms.txt`, `stopwords.txt`, `units.txt` | Product vocabulary, function words and units (category names are added automatically) |
| `fuzzy_protected_words.txt` | Real words that are never typo-corrected into a character name nor read as a brand plural |

Add misspellings the business cares about as extra rows in `characters.xlsx` (it already has
"Spaiderman", "barby", "hotweels"…). After editing a list or an Excel file, rebuild with
`docker compose up -d --build` and re-match the history (section 6). `MATCHING_FUZZY_ENABLED=false`
turns typo correction off.

## 8. Data model

### PostgreSQL (`snowflake_dev`)

| Schema.table | Written by | Content |
|---|---|---|
| `standardization_revenue_research_meli.brands` | Dagster | `brand_str`, `branded_int` |
| `standardization_revenue_research_meli.characters` | Dagster | `number_id_int`, `group_company_owner_rights_str`, `twdc_int`, `franchise_n1_str`… `franchise_n3_str`, `content_str`, `character_str`, `detail_str`, `comment_str` |
| `standardization_revenue_research_meli.mercado_libre_subcat` | Dagster | Subcategory codes per country, homologated names, `id_selected_int` |
| `stg_revenue_research_meli.meli_trends_l3` | Dagster | One row per keyword × subcategory × day, typed, all dates kept, plus the matching audit trail |
| `mdm_revenue_research_meli.trends` | dbt | **Final table for Superset**: the staging table in the layout of the business `trends` extract, incremental by `date_dte` |

`mdm_revenue_research_meli.trends` has exactly the 34 columns of the `trends.csv` extract, in the
same order (lowercase, as usual in PostgreSQL):

| Column | Meaning |
|---|---|
| `keyword_str`, `url_str` | Keyword and Mercado Libre search URL returned by the API |
| `date_dte`, `country_str`, `category_str`, `subcategory_str` | Snapshot date (pipeline time zone); country, category and subcategory from `mercado_libre_subcat.xlsx` (homologated names) |
| `_internal_filename_str`, `loading_dtm`, `file_row_id_int` | Raw L1 file, load time and 0-based row number in that file |
| `brand_str`, `character_str`, `second_brand_str` | Brand found (master list plus brand rules), character found, another brand in the same keyword |
| `group_company_owner_rights_str`, `twdc_int`, `franchise_n1_str`… `franchise_n3_str`, `content_str` | Owner and franchise hierarchy of the character |
| `keyword_in_spanish_str` | The keyword (Brazilian keywords are not translated) |
| `week_dte` | Monday of the snapshot week |
| `normalized_keyword_es_str`, `keyword_es_without_stopwords_str`, `character_without_stopwords_str` | Lowercase keyword without accents or punctuation, without stopwords, and the character name without stopwords |
| `lemmatized_keyword_str` | Keyword lemmatized with spaCy (`es_core_news_sm`; `pt_core_news_sm` for Brasil): "camisetas neon para fiestas" → "camiseta neon para fiesta" |
| `nouns_keyword_str` | Lemmas of the nouns, without the brand/character words: "mochila de stitch" → "mochila" |
| `has_franchise_n2_str`, `has_franchise_n3_str`, `has_character_str`, `has_franchise_n1_str`, `has_brand_str` | `YES` / `NO` flags |
| `branded_str` | `Branded` when a brand or a character was found, otherwise `Unbranded` |
| `year_calendar_int`, `month_calendar_int`, `day_calendar_int` | Calendar parts of `date_dte` |

The audit columns `brand_match_method_str`, `brand_match_score_int`, `brand_matched_text_str`
(and the same for characters) stay in the staging table, so any match can still be traced.

### MinIO (`meli-datalake`)

```text
L1_delta/revenue_research_meli/trends/mercado_libre_trends_ddmmyyyy.csv
L2_databases/revenue_research_meli/trends/date_dte=YYYY-MM-DD/meli_trends.parquet
L3_standardization/revenue_research_meli/trends/date_dte=YYYY-MM-DD/meli_trends.parquet
```

## 9. Superset dashboards

Superset starts with the connection **MeLi Trends (PostgreSQL)**, the dataset
`mdm_revenue_research_meli.trends` and the dashboard **Revenue Research - Mercado Libre Trends**
(<http://localhost:8088/superset/dashboard/meli-trends/>) already created. It reproduces the
Revenue Research report with 55 charts in 7 tabs:

| Tab | Charts |
|---|---|
| Read Me | General conditions and definitions |
| Summary | Branded/Unbranded, top 10 categories (total and branded), franchise searches, top 10 brands, franchises and characters, top 25 unbranded trends (lemmatized), products word cloud, category tables and weekly evolution |
| Market Landscape | Main companies over time, company share, companies by country and by category, branded categories, characters word cloud, top 5 brands associated with TWDC |
| Franchise | TWDC franchises: evolution, by country, by category, level 1 × level 2, level 2 share, by country and by content |
| Categories | Branded searches by country, company share, companies by country, franchises level 1 and level 2, top 10 branded trends, top 20 characters |
| Subcategories | Top 10 and evolution, top 5 per country, branded/unbranded products word clouds, TWDC subcategories, subcategories by franchise, totals |
| Products and Trends | Branded/Unbranded, branded franchises, top 100 products, product × character, top 10 trends, words searched within franchises level 2 |

The filter bar on top has *Fecha*, *Timeframe* (weekly or monthly evolution charts), *País*,
*Categoría*, *Subcategoría*, *Grupo Empresa Owner Derechos*, *Franquicia*, *Contenido*,
*Personaje*, *Marca* and *Branded*. The metric *Búsquedas* counts trend rows (keyword ×
subcategory × day); *Producto* is the first noun of `nouns_keyword_str`.

### Dashboards are never lost

- **Persistent metadata.** Users, datasets, charts and dashboards are stored in the PostgreSQL
  service `superset-db`, on the named volume `meli_trends_pipeline_superset_db_data`. They survive
  `docker compose down`/`up`, restarts of Docker or the computer and image rebuilds
  (`restart: unless-stopped` brings everything back when Docker starts). Only
  `docker compose down -v` or deleting that volume removes them.
- **Dashboards as code.** The dashboard is versioned in `superset/dashboard/` (generated by
  `superset/build_dashboard.py`). On every start `docker/superset/provision.py` re-creates it if
  it is missing, so even a new volume or a new machine gets it back. An existing dashboard is
  left untouched, so changes made in the UI are kept.
- To apply a new version of the bundle over an existing dashboard (it replaces its charts and
  dataset):

  ```bash
  docker compose exec superset python /app/docker/meli-provision.py --overwrite
  ```

- To version dashboards edited in the UI, export them (*Dashboards → select → Export*) and keep
  the ZIP, or port the change to `superset/build_dashboard.py` and run
  `python superset/build_dashboard.py`.

Reference screenshots of the original report are in [`superset/`](superset/).

## 10. Operations

| Task | Command |
|---|---|
| Status of every container | `docker compose ps` |
| Logs of one service | `docker compose logs -f dagster-code` (or open Dozzle) |
| Apply code, word-list or Excel changes | `docker compose up -d --build` |
| Run the test suite (inside the image) | `docker compose exec dagster-code python -m pytest` |
| Re-match the whole history after changing word lists or Excel files | see section 6 |
| Rebuild the final table from all staging history | see below |
| Stop everything (data is kept) | `docker compose down` |
| Delete everything, data included | `docker compose down -v` |

Full refresh of the dbt model (for example after changing its SQL):

```bash
docker compose exec dagster-code dbt build --full-refresh --project-dir dbt --profiles-dir dbt/profiles
```

The reference Excel files are baked into the Dagster image: after replacing a file in
`data/input/`, run `docker compose up -d --build` and materialize the pipeline again.

**Coming from the Airflow version (`meli_trends_etl`).** The Compose project is now named
`meli_trends_pipeline` and uses new volumes. Remove the old containers (`-v` would also delete
their volumes):

```bash
docker compose -p meli_trends_etl down
```

## 11. Troubleshooting

| Symptom | Fix |
|---|---|
| `Bind for 127.0.0.1:XXXX failed: port is already allocated` or `address already in use` | Another program uses that port (Grafana, for example, listens on 3000); change it in `.env` (e.g. `DAGSTER_PORT=3100`) and run `docker compose up -d` |
| `pull access denied for meli-trends-pipeline/...` | Those images are built locally (`pull_policy: build`) and never pulled; update to the current `docker-compose.yml`, or run `docker compose build` once |
| The run fails at `trends_l1_raw` with "ML_CLIENT_ID is not configured" or HTTP 401/403 | Fix `ML_CLIENT_ID` / `ML_CLIENT_SECRET` in `.env`, `docker compose up -d`, then *Materialize all* in Dagster |
| `trends_l1_raw` fails with many HTTP 429 | Lower `MELI_MAX_WORKERS` (e.g. `2`) |
| `dagster-code` stays unhealthy | `docker compose logs dagster-code`; the code location prints the import error |
| Superset login fails after changing the admin password in `.env` | The admin user is created once; change the password in Superset (*Settings → Info*), or reset its metadata with `docker compose down` and `docker volume rm meli_trends_pipeline_superset_db_data` (dashboards are re-created from `superset/dashboard/`, UI-only changes are lost) |
| The dashboard is missing or shows errors after an upgrade | `docker compose logs superset \| grep meli-provision`; re-apply the bundle with `docker compose exec superset python /app/docker/meli-provision.py --overwrite` |
| The browser shows "empty response" at `localhost:5434`, or a client reports the database `snowflake_dev` does not exist | PostgreSQL is not a web page and its host port is 5434, not 5432; see [Connecting to PostgreSQL](#connecting-to-postgresql) |
| PostgreSQL rejects the password after editing `.env` | Credentials apply only when the volume is created; restore the old value or reset with `docker compose down -v` |
| A shell script fails with `\r: command not found` after cloning on Windows | The repository forces LF line endings (`.gitattributes`); re-clone, or run `git add --renormalize .` and check out again |
| Dozzle shows no containers (rootless Docker) | Point its volume to your socket, e.g. `$XDG_RUNTIME_DIR/docker.sock` |

## 12. Project structure

```text
meli_trends_pipeline/
├── docker-compose.yml               # whole platform
├── .env.example                     # every setting, with defaults
├── docker/
│   ├── dagster/                     # Dagster image, instance config, locked dependencies
│   └── superset/                    # Superset image, config, bootstrap and dashboard provisioning
├── meli_trends_pipeline/            # Dagster code location
│   ├── definitions.py               # assets, job, schedule, sensor, resources
│   ├── automation.py                # job, daily schedule, first-run sensor
│   ├── assets/                      # reference data, L1/L2/L3 trends, dbt
│   ├── matching/                    # normalization, matcher, enrichment, word lists
│   ├── resources.py                 # PostgreSQL, MinIO, Mercado Libre API
│   ├── settings.py                  # environment settings and names
│   └── warehouse.py                 # DDL and bulk-load helpers
├── dbt/                             # dbt project (source, incremental model, data tests)
├── data/input/                      # brands.xlsx, characters.xlsx, mercado_libre_subcat.xlsx
├── superset/                        # dashboard bundle (dashboard/), its generator, screenshots
└── tests/                           # pytest suite (matching, enrichment, Dagster definitions)
```

## License

This project is licensed under the MIT License; see the [LICENSE](LICENSE) file for details.
