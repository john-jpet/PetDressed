# PetDressed

PetDressed is a private digital wardrobe and explainable, weather-aware outfit planner.

The V1 vertical slice includes Supabase email/password authentication, direct
private uploads, asynchronous segmentation and metadata review, a filterable
wardrobe, Open-Meteo forecasts, explainable CP-SAT outfit planning, locks,
swaps, regeneration, preferences, feedback, and user-scoped cleanup.

## Local development

Copy `.env.example` to both `.env` and `.env.local`. Add a Supabase project URL
and anonymous key; the API uses the project URL to verify Supabase-issued JWTs.
Then run the infrastructure:

The example values are placeholders: account creation cannot work until
`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, and
`SUPABASE_URL` point to the same real Supabase project. Never put a Supabase
service-role key in either frontend variable.

```sh
docker compose up --build
```

Run the frontend separately:

```sh
npm install
npm run dev
```

API documentation is available at `http://localhost:58000/docs`.
The API, PostgreSQL, Redis, MinIO, and the MinIO console are published on host
ports `58000`, `55432`, `56379`, `59000`, and `59001` respectively to avoid
common local service collisions. These can be changed with `API_PORT`,
`POSTGRES_PORT`, `REDIS_PORT`, `MINIO_PORT`, and `MINIO_CONSOLE_PORT`.

Implementation decisions and milestone verification notes are tracked in
[`docs/milestones.md`](docs/milestones.md). The plan for the React Native
client, and the shared code it will consume, is in
[`docs/mobile-plan.md`](docs/mobile-plan.md).

## Shared client code

`packages/shared/` holds the API contract types, a platform-agnostic API
client, and the outfit slot rules, mirroring `backend/app/schemas.py`. It
imports nothing from React, Next.js, or React Native so the mobile client can
consume it unchanged. Web code reaches it through the `@shared/*` path alias.
When you change an API schema, change `packages/shared/types.ts` in the same
commit.

The repository is laid out as `apps/*` for deployable clients and `packages/*`
for code shared between them:

```
apps/web/          Next.js client, its Cloudflare Worker entry, and its tests
packages/shared/   Platform-agnostic contract, API client, and outfit rules
backend/           FastAPI application and Celery worker
```

## Verification

```sh
cd backend
python -m pytest -q
python -m ruff check app tests scripts migrations
cd ..
npm run lint
npm run type-check
npm test
docker compose config --quiet
```

These same checks run in CI on every pull request
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)). Note that neither the
build nor ESLint type-checks the project, so `npm run type-check` is the only
step that catches type errors.

With the stack running, the synthetic pipeline smoke test is:

```sh
docker compose exec -T api python scripts/smoke_pipeline.py
```

It creates a synthetic garment, waits through the asynchronous CV pipeline,
checks the generated artifacts and 512-dimensional descriptor, and schedules
cleanup. It is a behavior test, not an accuracy benchmark.

## Production topology

The frontend is a static/edge-compatible vinext application and should receive
`NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SUPABASE_URL`, and
`NEXT_PUBLIC_SUPABASE_ANON_KEY` at build time. Run the API and worker from
`backend/Dockerfile`; use `backend/Dockerfile.cuda` only for a CUDA worker.

For production, supply managed PostgreSQL with pgvector, Redis, and
S3-compatible object storage through the variables in `.env.example`. Use
TLS endpoints, unique secrets, a private database/cache network, persistent
object storage, and set `CORS_ORIGINS` to the exact frontend origin. Migrations
run on API startup. Keep the worker asynchronous and independently scalable.

No provider-specific deployment files are required. A live deployment needs
the chosen production service endpoints and a Supabase project; none are
committed to this repository.
