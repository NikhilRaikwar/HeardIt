# HeardIt verification

Evidence recorded on 2026-10-23 (Asia/Calcutta). Commands run locally on Windows; no CI or deployment result is implied.

## Baseline

Starting commit: `0e415a0`. Branch renamed from `harden/10-of-10` to `engineering-readiness` without discarding work. Existing uncommitted results-loader centering is preserved.

| Command | Observed result |
| --- | --- |
| `npm ci` | First attempt failed on a locked lightningcss native binary. Stopped this repository's old dev server; retry exited 0. npm reported 5 high severity audit findings; no forced upgrades applied. |
| `npm run api:test` | Sandbox uv cache access failed; retry with cache access: **11 passed in 1.91s**. |
| `npm run typecheck` | First attempt during installation lacked tsc; retry after install exited 0. |
| `npm run lint` | Exit 0; 0 errors, 2 warnings in unused floating-panel and iphone components. |
| `npm run api:types` | Sandbox uv cache access failed; retry exited 0, OpenAPI exported and TypeScript generated. No schema diff. |
| `npm run build` | Failed with local HTTP API URL. Retry with HTTPS API then failed with local HTTP app URL. With `API_INTERNAL_URL=https://api-six-iota-fp3oos7pc0.vercel.app` and `NEXT_PUBLIC_APP_URL=https://heardit-six.vercel.app`: exit 0, production pages compiled. |
| `npm run test:e2e` | First sandbox run stalled and was stopped. Browser-enabled retry: **14 passed, 1 failed (1.4m)**. Failure: desktop creator journey remained at `/create` after publish rather than `/created/published-test`; tablet/mobile version passed. API responses are mocked in this suite. |
| `docker compose up -d mongo` | First attempt: Docker engine unavailable. Started Docker Desktop, retried, pulled mongo:8 and started fishaudio-mongo-1. |
| Local API startup | `MONGODB_URI=mongodb://127.0.0.1:27017 MONGODB_DATABASE=heardit_baseline uv run --directory apps/api uvicorn app.main:app --host 127.0.0.1 --port 8100`: startup complete, mongodb_ready. |
| `GET http://127.0.0.1:8100/health` | HTTP 200, `{"status":"ok","database":"mongodb","fish_configured":true}`. This verifies Mongo connectivity, not a Fish synthesis request. |

Raw command logs and Playwright failure traces are local ignored artifacts under `temp/verification` and `test-results`. They are not credentials or published evidence of provider requests.

## Baseline status before hardening

At this point, hardening phases, real provider calls, live deployment, and GitHub CI had not run. Baseline live URLs above are configuration inputs, not a claim that this branch is deployed.

## Phase 1 — experiment integrity and abuse protection

Executed on 2026-10-23 (Asia/Calcutta), after implementing signed assignment tokens, proxy-aware IP handling, Mongo-backed public-write limits, optional Turnstile verification, and creator preview.

| Command | Observed result |
| --- | --- |
| `npm run api:test -- tests/test_experiment_integrity.py tests/test_heardit.py` | **19 passed in 1.41s**. Covers legitimate assignment/vote, forged and switched conditions, token expiry and binding, duplicate vote, write limits and caps, forwarded-header trust behavior, optional CAPTCHA, and creator preview API behavior. |
| `npm run typecheck` | Exit 0. |
| `npm run lint` | Exit 0; 0 errors, 2 existing warnings in `floating-panel.tsx` and `iphone.tsx`. |
| `npm run test:e2e -- --grep "creator opens a labelled|audio listener receives|text condition receives"` | Not completed: Playwright could not start its configured web server because port 3101 was occupied. A retry on port 3113 did not finish starting Next.js within 60 seconds and was interrupted. Browser coverage for these changes remains unverified. |
| `npm run api:test` | **42 passed, 11 failed in 8.91s** while Phase 2 reliability work is in progress. All 11 failures are in `tests/test_reliability.py`: the generation route is not yet using the service dependency; idempotent publish, audio Range responses, and lazy index initialization are incomplete. |

No external Fish Audio or AIML synthesis/suggestion request was made during Phase 1. Mongo connectivity from the baseline check remains local only; this branch has not been deployed.

## Phase 2 — reliability

Executed on 2026-10-23 (Asia/Calcutta), after consolidating Fish synthesis behind `FishTTSService`, canonicalizing stored speech text, adding concurrent cache-race cleanup, publish idempotency, lazy Mongo index initialization, and GridFS byte-range streaming.

| Command | Observed result |
| --- | --- |
| `HEARDIT_MONGO_TEST_URI=mongodb://127.0.0.1:27017 npm run api:test` | **54 passed in 2.27s**, including mocked Fish success/error/timeout/cache tests and a real local Mongo integration test. The integration test simulates database unavailability at startup, then uses MongoDB, confirms unique vote and TTL indexes exist before accepting a vote, and checks `/health.indexes_ready`. It creates and drops a uniquely named temporary local database. |
| `npm run typecheck` | Exit 0 after wiring the idempotency key into the active creator journey. |
| `npm run lint` | Exit 0; 0 errors, the same 2 existing UI warnings. |
| `API_INTERNAL_URL=https://api-six-iota-fp3oos7pc0.vercel.app NEXT_PUBLIC_APP_URL=https://heardit-six.vercel.app npm run build` | Exit 0. Next.js 15.5.28 compiled and generated all 8 static pages; the same 2 warnings appeared. This builds locally with those configured URLs; it does not deploy this branch. |
| `PLAYWRIGHT_PORT=3115 npm run test:e2e` | **21 passed in 47.8s** across 1440px desktop, 768px tablet and 375px mobile projects. Includes the staged creator publish flow with the idempotency header, creator preview, blind audio/text payloads, and centered results loading state. API responses are mocked in these browser tests. |

Provider API tests use mocked HTTPX responses. No genuine Fish Audio or AIML request was made; live provider credentials were not exercised by these checks.

## Phase 3 — typed contracts, backend structure, and server rendering

Executed on 2026-10-23 (Asia/Calcutta), after moving API routes under `apps/api/app/routers/`, extracting request/response schemas, vote-count aggregation and deterministic statistics, wiring the generated OpenAPI types through the frontend client, and adding generic listener metadata and a generic Open Graph image.

| Command | Observed result |
| --- | --- |
| `npm run api:types` | Exit 0. FastAPI OpenAPI exported to `apps/api/openapi.json`; `openapi-typescript` generated `src/lib/api-schema.ts`. |
| `HEARDIT_MONGO_TEST_URI=mongodb://127.0.0.1:27017 npm run api:test` | **56 passed in 2.63s**, including the local Mongo integration test, real Mongo result aggregation, parity with the prior Python output, zero-response behavior, and aggregate-only public product stats. |
| `npm run typecheck` | Exit 0 with the typed `openapi-fetch` client and generated schema imports. |
| `npm run lint` | Exit 0 with no warnings. |
| `API_INTERNAL_URL=https://api-six-iota-fp3oos7pc0.vercel.app NEXT_PUBLIC_APP_URL=https://heardit-six.vercel.app npm run build` | Exit 0. `/` is statically rendered with a five-minute revalidation window; `/t/[id]` and its Open Graph image route are built. Next.js noted that the Edge runtime disables static generation for that route. This is a local build, not a deployment. |
| `PLAYWRIGHT_PORT=3115 npm run test:e2e` | **24 passed in 1.1m** across 1440px desktop, 768px tablet and 375px mobile. The suite verifies generic listener metadata and generated image delivery in addition to the existing creator/listener/results flows. Browser API calls are mocked. |
| Dependency import scan and UI reference scan | The listed animation, chart, form, query, schema, QR, and `mongomock` dependencies had no remaining product imports; unreferenced UI components were removed. `motion` remains because the active providers use `motion/react`. |

The landing page reads only product-wide Mongo counts and does not include individual sentences, labels, or assignments. The schema-drift workflow was added but has not run on GitHub. No real Fish Audio or AIML request was made.

## Remaining verification

Phases 4–5, real provider calls on this branch, live deployment, and execution of the GitHub Actions workflow have not run. Baseline live URLs above are configuration inputs, not a claim that this branch is deployed.
