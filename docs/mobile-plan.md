# Mobile client plan

PetDressed targets iOS and Android with React Native (Expo), reusing the
existing FastAPI backend unchanged. This document records the plan and the
groundwork already landed.

## Why the backend needs no changes

The API is already client-agnostic: 23 JSON routes under `/api/v1`, bearer-token
auth via Supabase-issued JWTs, and direct-to-storage uploads through presigned
POST forms. Nothing in it assumes a browser. The mobile work is therefore
entirely client-side.

## Repository shape

The move from a flat layout to `apps/*` and `packages/*` has now landed, as
its own change once CI was in place rather than as a prelude to feature work.
`vite.config.ts`, the Wrangler binding in `worker/index.ts`, and the render
tests all hard-coded the old layout, so it was never the week-one freebie an
earlier draft assumed. `.openai/hosting.json` stays at the repository root,
where the hosting platform expects it.

Note also that `worker/` is **not** an async task worker. It is the Cloudflare
Worker entry point that serves the frontend. Background processing is Celery,
in `backend/app/tasks.py`.

The interim structure avoids the migration while still sharing code:

```
packages/shared/   # Platform-agnostic. No React, Next, or React Native imports.
  types.ts         # API contract types mirroring backend/app/schemas.py
  api-client.ts    # fetch-based client with an injectable token provider
  outfit-slots.ts  # Which garment covers which part of a figure
apps/web/          # Next.js client, its Worker entry, its tests
apps/mobile/       # Expo client (not yet created)
backend/           # FastAPI + Celery
```

`packages/shared/` is importable from React Native as-is. When a mobile app is added, it
consumes the same two modules; only the token provider differs — Supabase's
browser client on web, secure storage on device.

### Why the shared types matter

Before extraction, the web client redeclared every API type by hand and had
drifted from the backend in both directions:

- `MetadataResult` omitted `degraded`, `inference_backend`, and
  `inference_warning`, all of which the API returns and the UI reads.
- `SegmentationResult` declared those same three fields, which that endpoint
  has never returned, and omitted `review_status`, which it does.

Neither drift was caught, because nothing type-checked the project. Both are
fixed, and `npm run type-check` now runs in CI.

## Stack

| Concern | Choice | Rationale |
|---|---|---|
| Runtime | Expo (managed) | Native modules without Xcode/Android Studio for day-to-day work |
| Navigation | Expo Router | File-based, mirrors the App Router mental model |
| Server state | TanStack Query | Caching and offline persistence for wardrobe reads |
| UI state | Zustand | Minimal, no provider tree |
| Styling | NativeWind | Shares Tailwind tokens with web |
| Storage | Expo SQLite + SecureStore | Wardrobe cache; tokens never in AsyncStorage |
| Camera | expo-camera, expo-image-picker | Capture and library, with permission flows |

## Phases

Each phase ends in something shippable to testers.

**Phase 0 — Foundation (landed).** Pipeline repairs, CI, shared API client and
types, mobile-first brutalist redesign of the web client.

**Phase 1 — Read-only wardrobe.** Expo scaffold, Supabase auth against the
existing project, wardrobe list and garment detail, SQLite cache for offline
browsing. No writes.

**Phase 2 — Capture and upload.** Camera and library picker, client-side
compression, presigned upload with progress, status polling, segmentation and
metadata review. This is the highest-risk phase: it is the only one with
meaningful platform divergence.

**Phase 3 — Planning.** Plan generation, week and day views, lock, regenerate,
swap. Plans sync through the backend, so web and mobile stay consistent.

**Phase 4 — Release.** Notifications, sharing, accessibility pass, analytics,
store submission.

## Risks

- **Upload reliability on mobile networks** is the dominant risk. Mitigation:
  retry with backoff, a persisted queue of pending uploads, and resumable
  status polling keyed on `garment_id` — the API already supports resumption
  via `GET /api/v1/garments/in-progress`.
- **Segmentation correction on a small touch target.** The web editor assumes a
  pointer. Expect to redesign it for touch rather than port it.
- **Verification.** React Native cannot be built or exercised in the container
  used for automated work; mobile phases need a machine with a simulator, and
  CI needs EAS credentials before any mobile job is meaningful.
