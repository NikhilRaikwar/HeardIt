# Deployment and proxy IPs

## Vercel request path

HeardIt's Next.js project uses `API_INTERNAL_URL` as the HTTPS origin for the separate FastAPI project. Its Next.js rewrite forwards `/api/v1/*` requests to that API while keeping the browser URL on the frontend domain. Vercel describes external-origin rewrites as proxying requests to the destination. [Vercel rewrites](https://vercel.com/docs/routing/rewrites)

For a direct request to a Vercel deployment, Vercel documents `X-Forwarded-For` as the public client IP and says it overwrites a caller-supplied value to prevent spoofing. Vercel also notes that an external proxy in front of a deployment changes this trust boundary; custom forwarded IPs require its Enterprise Trusted Proxy feature. [Vercel request headers](https://vercel.com/docs/headers/request-headers)

In HeardIt's two-project path (browser → Next.js on Vercel → FastAPI on Vercel), do not assume the original browser IP survives the external rewrite. The FastAPI project may see the Next.js/Vercel proxy as its caller. `HEARDIT_TRUST_PROXY=false` is the safe default and makes FastAPI ignore `X-Forwarded-For` entirely.

Set `HEARDIT_TRUST_PROXY=true` only after verifying that the request path to FastAPI replaces untrusted `X-Forwarded-For` values with a canonical client address, and that callers cannot reach the API through another ingress that accepts arbitrary forwarded headers. If the two Vercel projects do not preserve a sanitized end-user address, leave this setting false; the cap will then be shared by requests that reach FastAPI from the same network peer. CORS does not establish proxy trust.

## Check whether spoofed headers split the assignment limit

Run this PowerShell snippet against a **throwaway published test** after a quiet minute. It sends 60 assignments with one documentation-only spoofed IP and a 61st with another. With the default `HEARDIT_ASSIGNMENT_IP_MINUTE=60`, the final status should be `429`. Use the public frontend URL so the request follows the same rewrite path as a listener. The script creates assignment rows for that test but does not create votes.

```powershell
$BaseUrl = "https://heardit-six.vercel.app"
$TestId = "REPLACE_WITH_THROWAWAY_TEST_ID"
$SpoofA = "198.51.100.10"
$SpoofB = "203.0.113.20"
$LastStatus = ""

for ($i = 1; $i -le 61; $i++) {
  $participant = [guid]::NewGuid().ToString("N")
  $spoof = if ($i -le 60) { $SpoofA } else { $SpoofB }
  $body = @{ participant_id = $participant } | ConvertTo-Json -Compress
  $LastStatus = curl.exe -sS -o NUL -w "%{http_code}" `
    -X POST "$BaseUrl/api/v1/tests/$TestId/assignment" `
    -H "Content-Type: application/json" `
    -H "X-Forwarded-For: $spoof" `
    --data-raw "$body"
  Write-Output "$i $LastStatus"
}

if ($LastStatus -ne "429") {
  throw "Expected the 61st request to return 429; got $LastStatus. Keep HEARDIT_TRUST_PROXY=false and inspect the deployed request path."
}
```

If an earlier request returns `429`, the IP bucket was already used; wait 60 seconds and retry with a fresh throwaway test. If the final request does not return `429`, keep proxy trust disabled and inspect the API ingress before enabling it. This check verifies that changing the supplied header did not open a second bucket for this path; it does not prove that FastAPI received the human listener's IP.

## Vote cap behavior

`HEARDIT_VOTES_PER_IP_PER_TEST_DAILY` defaults to `20`. It counts requests in a MongoDB-backed 24-hour bucket keyed by the test ID and a SHA-256 hash of the IP selected by `client_ip()`. The raw IP is not written into that rate-limit key. Existing per-test, per-minute, and global daily caps remain in force.

These limits reduce accidental repeats and low-effort bursts. A person can rotate networks, VPNs, or devices to obtain a different IP/browser identifier and may exceed an IP-based limit. That is acceptable for this small exploratory product: the limits are abuse friction, not proof of human identity, fraud prevention, or population sampling. HeardIt's results remain observational and should be interpreted with the sample sizes shown.
