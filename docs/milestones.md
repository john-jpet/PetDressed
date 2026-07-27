# PetDressed delivery log

## Milestone 1 — Upload foundation

Implemented Supabase JWT authentication, user-scoped garment drafts, direct
presigned MinIO uploads, asynchronous validation, status polling, PostgreSQL
migrations, Docker Compose services, and the responsive upload experience.

Tests cover request validation, image signatures and dimensions, frontend
rendering, production compilation, linting, and Compose configuration.

## Milestones 2–3 — Segmentation and review

Implemented normalized image decoding, transparent crops, mask and overlay
artifacts, proportional padding, revision-safe Celery work, temporary review
URLs, positive and negative prompts, bounding-box retries, brush corrections,
acceptance, and a responsive correction interface.

The segmenter is behind a stable interface. The checked-in CPU baseline makes
local development and synthetic tests deterministic. A separate CUDA worker
image supports SAM 2 when its checkpoint is configured. This is an intentional
development-mode deviation: no segmentation-quality claim is made for the CPU
baseline, and SAM 2 accuracy remains unverified until representative labelled
images and a checkpoint are available.

Tests cover synthetic garment isolation, transparent output, prompt bounds,
manual mask edits, downscaling, API behavior, frontend compilation, and linting.

## Milestones 4–5 — Metadata review and wardrobe

Implemented separate generated and confirmed metadata, deterministic 512-D
visual descriptors, CIELAB palette extraction, category alternatives and
confidence, prediction audit records, editable attributes, planner eligibility,
the searchable/filterable wardrobe, availability changes, and exact cosine
similarity retrieval.

The local CPU metadata backend is deliberately conservative and marks its
category suggestions as low confidence. Fashion-CLIP remains the production
model boundary, but no classification-accuracy claim is made until its
checkpoint and a representative labelled dataset are supplied.

Tests cover colour conversion, alpha-aware palette extraction, normalized
embeddings, deterministic inference, category hints, backend behavior, frontend
rendering, compilation, and linting.

## Milestones 6–7 — Compatibility and CP-SAT planning

Implemented versioned colour, formality, pattern, and preference components;
meaningful pair-variable linearization; structural top/bottom versus one-piece
modes; required footwear; optional layers; category-specific rotation;
candidate pruning; locks and exclusions; deterministic solving; staged
relaxation; score breakdowns; and structured infeasibility.

Tests use deterministic minimum, one-piece, conflicting-lock, replacement,
missing-category, hard-weather, and pair-preference wardrobes.

## Milestones 8–9 — Weather and planner experience

Implemented the Open-Meteo provider behind a replaceable protocol using the
current official daily and hourly fields, active-hours planning temperature,
weather suitability, provider-failure fallback, forecast snapshots, persistent
plans, day locking, item replacement, day regeneration, feedback capture, and
the responsive seven-day planner.

Tests cover forecast normalization, warmth thresholds, rain suitability,
planner constraints, backend checks, frontend rendering, production compilation,
and Compose configuration.

## Milestone 10 — Product hardening and deployment readiness

Completed request IDs, structured API timing logs, Prometheus-compatible
metrics, security headers, health checks, user-scoped deletion and asynchronous
artifact cleanup, non-root API and worker containers, configurable host ports,
an evaluation harness, and a live synthetic end-to-end smoke test against the
Compose stack. Saved repetition, formality, accessory, weather-strictness, and
active-hour preferences now influence planning. The review flow also supports
automatic retry and discarding a draft to use a different source photo.

The responsive frontend has production metadata and a generated PetDressed
social-preview asset. Production configuration is environment-driven and
provider-neutral: the frontend can be hosted separately, while the API, worker,
PostgreSQL/pgvector, Redis, and S3-compatible storage can move to managed
services without application changes.

Verification: 32 backend tests, Ruff, frontend ESLint, production frontend
build, rendered HTML test, Compose validation, migration to revision `0006`,
non-root container identity checks, and a live upload-to-metadata pipeline smoke
test. The smoke fixture and all generated artifacts were deleted afterward.

Remaining deployment inputs are intentionally external: a Supabase project,
public API/frontend origins, and production PostgreSQL, Redis, and
S3-compatible service credentials. The deterministic CPU CV backends remain
the local-development defaults; representative labelled data and production
model checkpoints are still required before making quality claims.
