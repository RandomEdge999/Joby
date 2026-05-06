<p align="center">
  <img src="./logo.svg" alt="Joby" width="420" />
</p>

<p align="center">
  A private, local-first job search workspace that pulls openings from company career pages, ranks them against your profile, and keeps the search on your machine.
</p>

<p align="center">
  <img alt="Python 3.12+" src="https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white" />
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white" />
  <img alt="Next.js" src="https://img.shields.io/badge/Next.js-000000?logo=next.js&logoColor=white" />
  <img alt="SQLite" src="https://img.shields.io/badge/SQLite-local-003B57?logo=sqlite&logoColor=white" />
  <img alt="Platforms" src="https://img.shields.io/badge/Platforms-Windows%20%7C%20macOS%20%7C%20Linux-1F6FEB" />
  <img alt="Tests" src="https://img.shields.io/badge/Tests-90%20passing-2DA44E" />
</p>

Joby is built for people who want direct listings, better signal, and a search workflow they actually control. Instead of living inside a marketplace feed, you pull roles from company systems, review ranked results, save what matters, and track progress in one place.

There is no hosted backend to sign up for, no forced cloud account, and no auto-apply behavior. Joby is for finding the right jobs, not firing off applications blindly.

## Why Joby

Most job boards are optimized for volume. Joby is optimized for focus. It starts from the employer's own listing, keeps your data local, and gives you a private workspace for filtering, reviewing, and tracking opportunities.

## What it does

- Pulls roles directly from Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Recruitee, and supported Workday tenants.
- Lets you add more companies from the Sources screen instead of editing config files by hand.
- Supports broader coverage through JobSpy for LinkedIn, Indeed, Glassdoor, ZipRecruiter, and Google Jobs.
- Ranks jobs deterministically by default, with an optional local model endpoint such as LM Studio for deeper profile screening.
- Lets you tune fit, opportunity, and urgency weights in Settings and immediately reranks existing jobs with updated explanations.
- Lets you export or restore a full workspace backup, including local data and custom source overlays.
- Keeps jobs, saved roles, notes, contacts, and application tracking in one local workspace.
- Runs on Windows, macOS, and Linux through a single `joby` CLI.

## Quick start

### Requirements

| Tool | Version | Required | Notes |
| --- | --- | --- | --- |
| Python | 3.12+ | yes | Required for the API and CLI |
| Node.js | 20+ | no | Required for the web app |
| LM Studio | any | no | Optional local model endpoint |

### Install

**macOS / Linux / WSL**

```bash
git clone https://github.com/RandomEdge999/Joby.git
cd Joby
bash install.sh
```

**Windows (PowerShell)**

```powershell
git clone https://github.com/RandomEdge999/Joby.git
cd Joby
.\install.ps1
```

### Run

```bash
joby
```

Open `http://localhost:3000` for the web app. The API runs on `http://localhost:8000`.

For Git Bash, the repo root also includes shell shortcuts:

```bash
./start.sh    # start or reuse the local API + web app
./stop.sh     # stop listeners on the default dev ports (3000 and 8000)
```

### Run with Docker

```bash
docker compose up --build
```

Docker starts the API on `http://localhost:8000` and the web app on
`http://localhost:3000`. LM Studio is optional; when using Docker, the default
container URL points at `host.docker.internal` so the API can reach a model
server running on the host machine.

## Daily use

1. Set your profile in Settings, including ranking weights if you want to bias toward fit, opportunity, or urgency.
2. Open Jobs, enter a role or keyword, choose sources, and run a search.
3. Refine the local results with filters for company, location type, visa signal, salary, recency, and contacts.
4. Open a role to review ranking, eligibility, trust, contacts, notes, and application state; then save it, skip it, or apply manually through the original posting.
5. Open Sources when coverage looks thin to inspect source health, cache freshness, and recent source errors.
6. Use Settings to export a workspace backup before moving machines or restoring a previous local state.

## Source coverage

### Direct company systems

- Greenhouse
- Lever
- Ashby
- SmartRecruiters
- Workable
- Recruitee
- Workday

### Broader coverage via JobSpy

- LinkedIn
- Indeed
- Glassdoor
- ZipRecruiter
- Google Jobs

### Deliberate scope

- No Handshake support
- No sources that require your personal login
- No auto-apply flows or browser automation that submits applications for you

## Commands

```text
joby                 start the API and web app together
joby up              same as above; add --api-only to skip the web app
joby api             start only the API
joby web             start only the web app
joby install         install dependencies, seed data, and prepare the app
joby scrape          trigger one scrape run against the running API
joby doctor          print environment diagnostics
joby version         print the installed version
```

If setup looks wrong or the app will not start, run `joby doctor`. It reports
required versus optional checks for Python, Node/npm, config dir, database
path/schema, JobSpy, LM Studio, and API/web reachability, and each warning or
failure includes the next command to run.

Global flags such as `--api-port`, `--web-port`, and `--host` work before or after the subcommand.

## Configuration

Most setups work without changes. These are the main overrides:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./data/joby.db` | Database location |
| `CONFIG_DIR` | `./config` | Source files and local config |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Allowed browser origins |
| `LM_STUDIO_BASE_URL` | `http://localhost:1234/v1` | OpenAI-compatible model endpoint |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Web app to API base URL |
| `JOBY_API_PORT` | `8000` | Environment default for the CLI; override with `--api-port` |
| `JOBY_WEB_PORT` | `3000` | Environment default for the CLI; override with `--web-port` |
| `USCIS_H1B_CSV_URL` | FY2024 Employer Data Hub CSV | Optional override for H-1B source data |

## Development

Keep development changes aligned with the product contract in this README:
local-first data ownership, direct listing coverage, clear ranking signals,
and no auto-apply behavior.

Run the backend test suite:

```bash
cd apps/api
pytest -q
```

Build the web app:

```bash
cd apps/web
npm run lint
npm run build
```

`npm run lint` currently runs the TypeScript release gate. The project avoids a
separate ESLint setup until there is a real rule set worth maintaining.

Run the local end-to-end smoke suite against a seeded local database:

```bash
cd apps/web
npm run e2e:install
npm run e2e:smoke
```

The smoke suite starts its own API and web servers, seeds a deterministic local
SQLite database, filters seeded jobs on the Jobs page, opens the detail drawer,
and verifies that saving a job shows up on the Applications board.

Repository layout:

```text
.env.example        Local environment template
logo.svg            Primary brand asset used in docs and the web UI
logo.png            Raster brand asset used for browser metadata
install.sh          macOS / Linux / WSL bootstrap
install.ps1         Windows bootstrap
apps/api            FastAPI service, CLI, scrapers, ranking, migrations
apps/web            Next.js user interface
config              Curated sources and user-added sources
scripts             Install, seed, and maintenance helpers
```

## Contributing

Issues and pull requests are welcome. Keep changes focused, describe user-facing behavior clearly, and avoid bundling unrelated refactors into the same PR.

