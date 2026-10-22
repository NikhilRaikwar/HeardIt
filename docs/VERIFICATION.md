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
