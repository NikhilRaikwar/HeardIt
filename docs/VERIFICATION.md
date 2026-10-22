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

## Not yet verified

Hardening phases, real provider calls on this branch, live deployment, and GitHub CI have not run yet. Baseline live URLs above are configuration inputs, not a claim that the hardened branch is deployed.

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
