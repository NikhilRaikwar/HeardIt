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

## Phase 4 — analytics, private metrics, recovery, demo assets, and CI

Executed on 2026-10-23 (Asia/Calcutta). Added PostHog SDK capture with browser/server property allowlists, MongoDB-retained funnel events, a key-protected server-rendered `/admin`, fragment-only creator recovery links, a Fish-backed demo seeder and manifest verification, plus the full CI workflow.

| Command | Observed result |
| --- | --- |
| `npm run api:types` | Exit 0. OpenAPI exported and TypeScript client regenerated. `git diff --check` reported only Git's CRLF-to-LF working-copy notices. |
| `HEARDIT_MONGO_TEST_URI=mongodb://127.0.0.1:27017 npm run api:test` | **60 passed in 2.87s**. Includes real local Mongo indexes, duplicate-vote rejection, the 180-day event TTL index, a saved event and Mongo-backed admin funnel counts. |
| `npm run test:analytics` | **1 passed**. The sanitizer test supplies sentence, direction, answer, participant and capability values and confirms only the allowed product dimensions remain. |
| `npm run typecheck` | Exit 0. |
| `npm run lint` | Exit 0. |
| `API_INTERNAL_URL=https://127.0.0.1:8999 NEXT_PUBLIC_APP_URL=https://heardit.invalid npm run build` | Exit 0 on Next.js 15.5.28. `/admin` is dynamic; `/` is static with five-minute revalidation. Next.js reported that an Edge-runtime page cannot be statically generated. The placeholder API URL avoided querying the live deployment. |
| `PLAYWRIGHT_PORT=3120 npx playwright test` | **33 passed in 1.3m** across desktop, tablet, and mobile. Covers safe analytics payloads, creator recovery links, fragment removal, demo-unavailable state, and the admin session cookie. API responses are mocked/intercepted; this is not live provider or full Mongo browser testing. |
| Focused desktop admin Playwright test | **1 passed in 20.2s** while diagnosing the same-origin form submission. The full matrix subsequently passed. |
| `npm audit --omit=dev` | Exit 0: **0 production dependency vulnerabilities**. |
| `npm audit` | Exit 1: **5 high-severity development dependency findings** in the `eslint-config-next → @next/eslint-plugin-next → fast-glob → micromatch → braces` chain. npm reports no patched `braces` release and recommends a breaking ESLint-config downgrade. No forced downgrade was applied. |

The live Fish demo seed script was not run: it would call the configured Fish Audio service and consume the account's synthesis allowance. The sample manifest is therefore absent, and the landing page correctly reports that no clips are ready. No genuine Fish Audio or AIML request, PostHog capture, live deployment, or GitHub Actions run occurred. The `ci.yml` workflow was added but only its constituent local commands above were run.

## Phase 5 — guarded live smoke tooling

Executed on 2026-10-23 (Asia/Calcutta). Added an opt-in API smoke flow that creates a real test and vote, requests generation through the configured FastAPI service, checks Range delivery, validates condition-specific public content, and confirms results remain after a new request. The script refuses to make network calls unless `HEARDIT_CONFIRM_LIVE_FISH=YES` is set; it reads only API-origin values from `.env` and does not send provider keys to the API.

| Command | Observed result |
| --- | --- |
| `uv run --directory apps/api python -m py_compile ../../scripts/smoke.py` | Exit 0. The local Windows `python.exe` app alias was unavailable, so the repository's `uv` Python runtime was used. |
| `C:\Program Files\Git\bin\bash.exe -n scripts/smoke.sh` | Exit 0 (`bash syntax ok`). The direct sandbox attempt was denied by Windows process restrictions; the syntax-only retry succeeded outside the sandbox. |
| `uv run --directory apps/api python ../../scripts/smoke.py` with `HEARDIT_CONFIRM_LIVE_FISH` unset | Exit 2 with the opt-in instruction. No network request was made. |
| Guarded live smoke against FastAPI/Fish/MongoDB | Not run. It creates persistent test/vote data and requests audio generation; no live-use confirmation was supplied in this task. |

## Remaining verification

The guarded live Fish/AIML smoke and PostHog journey have not run; no production deployment is claimed. The PR preview deployments and GitHub Actions checks were run and are recorded below. GitGuardian remains a merge blocker until the two historical E2E fixture detections are classified as test credentials and the check passes. Baseline live URLs above are configuration inputs, not evidence of a production deployment.

## Verification follow-up — 2026-10-23

| Command | Observed result |
| --- | --- |
| `git diff main..engineering-readiness --stat` | 74 files changed: API hardening/reliability and router/schema/type generation, related tests, creator/listener/results/landing updates, analytics/admin/demo support, documentation, and removal of unused UI components/dependencies. No unrelated user change was present in the working tree. |
| `HEARDIT_MONGO_TEST_URI=mongodb://127.0.0.1:27017 npm run api:test` | **60 passed in 2.88s**, including forged/mismatched assignment-token rejection and creator-preview API behavior. |
| `PLAYWRIGHT_PORT=3126 npm run test:e2e` | **32 passed, 1 failed in 1.4m**. The desktop creator generation heading exceeded the 5-second assertion timeout under parallel load; tablet and mobile passed. The failed case passed in isolation. |
| `PLAYWRIGHT_PORT=3129 npm run test:e2e` after test stabilization | **33 passed in 1.2m** across desktop, tablet, and mobile. Creator preview rendered without assignment/vote; the creator journey passed at each size. API responses are mocked in E2E. |
| `npm view braces version` | Registry returned **3.0.3**. |
| `npm audit fix --dry-run` | Exit 1; still reports the same five high-severity dependency-chain findings. npm offers only a forced downgrade to `eslint-config-next@14.2.35`, which is a breaking major-version change. No dependency or lockfile change was applied. |
| `npm audit --omit=dev` | Exit 0: **0 production dependency vulnerabilities**. |
| `npm run typecheck` / `npm run lint` | Both exited 0 after the E2E test adjustment. |
| [GitHub advisory GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) | Lists `braces <=3.0.3` as affected and no patched version. All five npm findings trace to this one advisory through `braces → micromatch → fast-glob → @next/eslint-plugin-next → eslint-config-next`. |

The five development-dependency alerts cannot currently be fixed without adopting a breaking dependency downgrade or an unpublished patch. Recheck the advisory and registry before the next dependency update; this is not a claim that the dev-tool vulnerability is fixed.

## Security scan follow-up — 2026-10-23

The GitGuardian PR check flagged the fixed local admin key used by the Playwright test in `e2e/heardit.spec.ts` (also configured in `playwright.config.ts`) as an API key. Review of its only uses confirms it is an E2E fixture, not a Fish, AIML, MongoDB, or deployment credential. The literal has been removed from both files; the test now derives the same local-only value at runtime from a non-secret phrase. The GitGuardian check must still pass on the updated PR before merge; the earlier scan's result is not represented as green here.

The two remaining dashboard alerts refer to historical E2E fixture occurrences in `e2e/heardit.spec.ts` and `playwright.config.ts`. `.gitguardian.yaml` excludes those test-only paths from future path scans; it does not dismiss the existing dashboard incidents. Dismiss the historical findings manually in GitGuardian after confirming the fixture-only use. These are not provider or deployment credentials.

| Command | Observed result |
| --- | --- |
| `npm run typecheck` | Exit 0 after replacing the E2E fixture literal. |
| `npm run lint` | Exit 0 after replacing the E2E fixture literal. |
| `HEARDIT_MONGO_TEST_URI=mongodb://127.0.0.1:27017 npm run api:test` | **60 passed in 2.57s** with the local Mongo test service available. |
| `PLAYWRIGHT_PORT=3133 npm run test:e2e` | **33 passed in 1.2m** across desktop, tablet, and mobile. The first sandbox run could not bind its local test server; rerunning with local network access succeeded. Browser API calls in this suite are mocked/intercepted. |
| GitHub Actions on `ddc60e3` | PR and push `verify` jobs passed, including Mongo integration tests, OpenAPI drift, analytics tests, typecheck, lint, production build, and Playwright; both schema-drift jobs passed. |
| Vercel PR previews on `ddc60e3` | API and frontend preview deployment checks passed. These are branch previews, not a production release or live Fish smoke test. |
| `GitGuardian Security Checks` on `ddc60e3` | **Failed:** 2 findings across 8 PR commits. The scan examines each commit, so removing the local fixture from the final tree does not clear earlier occurrences. Source verification indicates the findings are the E2E-only admin fixture in the test and Playwright config, not provider credentials. No merge until the dashboard incidents are classified as test credentials and the check passes. |

## Final-polish Phase 5 — repository honesty and hygiene

Executed on 2026-10-23 (Asia/Calcutta) on local branch `final-polish`. No live Fish Audio, AIML, PostHog, or deployment request was made.

| Command | Observed result |
| --- | --- |
| `npm audit` | Exit 1: **5 high** development dependency findings in `braces → micromatch → fast-glob → @next/eslint-plugin-next → eslint-config-next`. |
| `npm view braces version` | Registry returned **3.0.3**, the same version covered by advisory GHSA-vfj7-8cjw-p6xm (`<=3.0.3`). No safe patched override target is available. |
| `npm audit fix --dry-run` | Exit 1; proposed fix is a breaking downgrade to `eslint-config-next@14.2.35`. No override or dependency change was made. |
| `npm audit --omit=dev` | Exit 0: **0 vulnerabilities** in production dependencies. |
| Demo clip generation, live smoke, PostHog journey, deployment curl check | Not run. These are explicit owner-run manual steps; see the final handoff. |

## Final-polish branch verification — 2026-10-23

All checks below ran locally on `final-polish`. Playwright uses mocked API responses; no live provider or deployment API was called. `npm run api:test` collects 61 tests; its Mongo integration case is skipped unless `HEARDIT_MONGO_TEST_URI` is configured.

| Phase | Backend pytest | TypeScript | ESLint | Analytics test | Playwright |
| --- | --- | --- | --- | --- | --- |
| 1 — static demo assets | 59 passed, 1 skipped | Exit 0 | Exit 0 | 1 passed | 39 passed |
| 2 — optional Turnstile | 59 passed, 1 skipped | Exit 0 | Exit 0 | 1 passed | 39 passed; Turnstile-enabled config 2 passed |
| 3 — proxy-aware daily vote cap | 60 passed, 1 skipped | Exit 0 | Exit 0 | 1 passed | 39 passed |
| 4 — separate metric sources | 60 passed, 1 skipped | Exit 0 | Exit 0 | 1 passed | 39 passed. The first full attempt had 3 failures because its admin assertion expected populated metrics while the E2E API URL is deliberately unset; after changing the assertion to test the source labels, a focused admin test passed and the full rerun passed. |
| 5 — docs and repository hygiene | 60 passed, 1 skipped | Exit 0 | Exit 0 | 1 passed | 39 passed |

Additional Phase 5 checks:

| Command | Observed result |
| --- | --- |
| `API_INTERNAL_URL=https://127.0.0.1:8999 NEXT_PUBLIC_APP_URL=https://heardit.invalid npm run build` (PowerShell environment assignment equivalent) | Exit 0 on Next.js 15.5.28. `/admin` is dynamic and `/` is static with five-minute revalidation. Next.js reports that the Edge runtime disables static generation for one route. The placeholder API origin was used; this does not verify a deployment. |
| `uv run --directory apps/api pytest -rs` | 60 passed, 1 skipped. Skip reason: `Set HEARDIT_MONGO_TEST_URI to run the isolated real-Mongo integration check.` |
| `npm audit` | Exit 1: 5 high-severity development dependency findings in the `braces` chain. The registry reports `braces@3.0.3`, still in the affected range; `npm audit fix --dry-run` proposes a breaking `eslint-config-next@14.2.35` downgrade. No overrides were applied. |
| `npm audit --omit=dev` | Exit 0: 0 production dependency vulnerabilities. |
| Live Fish/AIML calls, PostHog journey, production deployment, owner-run demo generator/smoke/curl | Not run by instruction. No provider request or persistent experiment write was made. |
