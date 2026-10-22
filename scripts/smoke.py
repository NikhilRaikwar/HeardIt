#!/usr/bin/env python3
"""Opt-in API smoke test for a genuine Fish-backed HeardIt experiment.

Every generated test and vote is persisted. Set HEARDIT_CONFIRM_LIVE_FISH=YES
before running because audio generation can consume provider allowance.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SENTENCE = "I thought you said you'd be here by now."
DIRECTION = "[curious, gently inquisitive]"
INTENDED = "Curious"
ALTERNATIVES = ["Annoyed", "Hurt", "Playful"]
TIMEOUT_SECONDS = 130


class SmokeFailure(Exception):
    pass


def load_local_env() -> None:
    """Load only the API origin override, never provider credentials."""
    env_file = ROOT / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("#") or "=" not in candidate:
            continue
        key, value = candidate.split("=", 1)
        key = key.strip()
        if key in {"HEARDIT_API_URL", "API_INTERNAL_URL"}:
            os.environ.setdefault(key, value.strip().strip("\"'"))


def pass_step(name: str) -> None:
    print(f"[PASS] {name}")


def fail_step(name: str, reason: str) -> None:
    print(f"[FAIL] {name}: {reason}", file=sys.stderr)
    raise SmokeFailure(reason)


def api_request(
    origin: str,
    path: str,
    *,
    label: str,
    method: str = "GET",
    body: dict | None = None,
    headers: dict[str, str] | None = None,
    expected: tuple[int, ...] = (200,),
) -> tuple[int, dict | bytes, dict[str, str]]:
    request_headers = dict(headers or {})
    payload = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(urljoin(origin.rstrip("/") + "/", path.lstrip("/")), data=payload, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
            content = response.read()
            response_headers = dict(response.headers.items())
    except HTTPError as error:
        status = error.code
        content = error.read()
        response_headers = dict(error.headers.items()) if error.headers else {}
    except (TimeoutError, URLError, OSError) as error:
        fail_step(label, f"request failed ({type(error).__name__})")

    if status not in expected:
        # Avoid displaying response bodies: provider or capability data must
        # never end up in terminal logs or CI artifacts.
        code = ""
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and isinstance(parsed.get("code"), str):
                code = f" ({parsed['code']})"
        except (json.JSONDecodeError, TypeError):
            pass
        fail_step(label, f"unexpected HTTP {status}{code}")

    try:
        value: dict | bytes = json.loads(content) if "json" in response_headers.get("Content-Type", "") else content
    except json.JSONDecodeError:
        fail_step(label, "response was not valid JSON")
    return status, value, response_headers


def require_mapping(value: dict | bytes, step: str) -> dict:
    if not isinstance(value, dict):
        fail_step(step, "response shape was invalid")
    return value


def main() -> int:
    if os.environ.get("HEARDIT_CONFIRM_LIVE_FISH") != "YES":
        print("Set HEARDIT_CONFIRM_LIVE_FISH=YES to authorize a persistent test, an audio-generation request, and one saved vote. A cached clip may be reused.", file=sys.stderr)
        return 2

    load_local_env()
    origin = (os.environ.get("HEARDIT_API_URL") or os.environ.get("API_INTERNAL_URL") or "http://127.0.0.1:8000").strip().rstrip("/")
    parsed_origin = urlparse(origin)
    if parsed_origin.scheme not in {"http", "https"} or not parsed_origin.netloc:
        print("Set HEARDIT_API_URL to a valid FastAPI origin.", file=sys.stderr)
        return 2
    if parsed_origin.scheme != "https" and parsed_origin.hostname not in {"localhost", "127.0.0.1", "::1"}:
        print("Use HTTPS for non-local FastAPI smoke targets.", file=sys.stderr)
        return 2

    try:
        _, value, _ = api_request(origin, "/health", label="health")
        health = require_mapping(value, "health")
        if health.get("status") != "ok" or health.get("database") != "mongodb":
            fail_step("health / MongoDB", "FastAPI did not report a healthy MongoDB connection")
        pass_step("health / MongoDB")
        if health.get("fish_configured") is not True:
            fail_step("Fish configuration", "the API reports no Fish Audio key")
        pass_step("Fish key configured on API")

        _, value, _ = api_request(
            origin,
            "/api/v1/audio/generate",
            label="Fish generation",
            method="POST",
            body={"sentence": SENTENCE, "direction": DIRECTION},
        )
        generated = require_mapping(value, "Fish generation")
        audio_id = generated.get("audio_id")
        audio_url = generated.get("url")
        if not isinstance(audio_id, str) or not audio_id or not isinstance(audio_url, str):
            fail_step("Fish generation", "API did not return a saved audio reference")
        if generated.get("cached") is True:
            pass_step("Fish-generated audio cache hit and saved audio reference")
        else:
            pass_step("Fish generation request returned a saved audio reference")

        _, audio, audio_headers = api_request(
            origin,
            audio_url,
            label="MP3 asset read",
            headers={"Range": "bytes=0-31"},
            expected=(206,),
        )
        if not isinstance(audio, bytes) or not audio or not audio_headers.get("Content-Range", "").startswith("bytes 0-"):
            fail_step("MP3 asset read", "stored audio did not return a valid byte range")
        if not audio_headers.get("Content-Type", "").startswith("audio/mpeg"):
            fail_step("MP3 asset read", "stored audio did not use audio/mpeg")
        pass_step("saved MP3 is readable with HTTP Range")

        test_body = {
            "sentence": SENTENCE,
            "intended_label": INTENDED,
            "distractors": ALTERNATIVES,
            "direction": DIRECTION,
            "audio_id": audio_id,
        }
        _, value, _ = api_request(
            origin,
            "/api/v1/tests",
            label="publish",
            method="POST",
            headers={"Idempotency-Key": secrets.token_urlsafe(24)},
            body=test_body,
            expected=(201,),
        )
        published = require_mapping(value, "publish")
        test_id = published.get("id")
        management_token = published.get("management_token")
        if not isinstance(test_id, str) or not isinstance(management_token, str) or not management_token:
            fail_step("publish", "API did not return private creator access")
        pass_step("test published after synthesis")

        management_headers = {"X-Management-Token": management_token}
        _, value, _ = api_request(origin, f"/api/v1/tests/{test_id}/results", label="initial results", headers=management_headers)
        before = require_mapping(value, "initial results")
        initial_total = before.get("total")
        if not isinstance(initial_total, int):
            fail_step("initial results", "results did not include a response count")

        participant_id = secrets.token_urlsafe(32)
        _, value, _ = api_request(
            origin,
            f"/api/v1/tests/{test_id}/assignment",
            label="assignment",
            method="POST",
            body={"participant_id": participant_id},
        )
        assigned = require_mapping(value, "assignment")
        assignment_token = assigned.get("assignment_token")
        if assigned.get("condition") not in {"audio", "text"} or not isinstance(assignment_token, str) or not assignment_token:
            fail_step("assignment", "API did not return a signed listener assignment")
        pass_step("listener assigned to a persisted condition")

        _, value, _ = api_request(
            origin,
            f"/api/v1/tests/{test_id}/public?{urlencode({'participant_id': participant_id})}",
            label="public test",
            headers={"X-Assignment-Token": assignment_token},
        )
        public_test = require_mapping(value, "public test")
        options = public_test.get("options")
        if public_test.get("condition") != assigned["condition"] or not isinstance(options, list) or len(options) != 4:
            fail_step("public test", "listener response did not preserve its condition and four choices")
        if (assigned["condition"] == "audio" and ("sentence" in public_test or not public_test.get("audio_url"))) or (
            assigned["condition"] == "text" and ("audio_url" in public_test or public_test.get("sentence") != SENTENCE)
        ):
            fail_step("blind condition payload", "public test exposed content outside its assigned condition")
        first_option = options[0] if isinstance(options[0], dict) else {}
        option_id = first_option.get("id")
        if not isinstance(option_id, str) or not option_id:
            fail_step("public test", "first randomized choice did not include an option ID")
        pass_step(f"blind-safe public test ({assigned['condition']} condition)")

        _, value, _ = api_request(
            origin,
            f"/api/v1/tests/{test_id}/votes",
            label="vote",
            method="POST",
            body={"participant_id": participant_id, "assignment_token": assignment_token, "selected_option_id": option_id},
            expected=(201,),
        )
        vote = require_mapping(value, "vote")
        if vote.get("submitted") is not True:
            fail_step("vote", "API did not confirm the saved vote")
        pass_step("listener vote saved")

        _, value, _ = api_request(origin, f"/api/v1/tests/{test_id}/results", label="results after vote", headers=management_headers)
        after = require_mapping(value, "results after vote")
        after_total = after.get("total")
        if not isinstance(after_total, int) or after_total < initial_total + 1:
            fail_step("results after vote", "saved response did not increase the persisted result count")
        pass_step("private results include the saved vote")

        _, value, _ = api_request(origin, f"/api/v1/tests/{test_id}/results", label="refreshed results", headers=management_headers)
        refreshed = require_mapping(value, "refreshed results")
        if not isinstance(refreshed.get("total"), int) or refreshed["total"] < after_total:
            fail_step("results refresh", "saved response was not present after a fresh results request")
        pass_step("results persist across a fresh request")
        print("Smoke flow completed. The test and vote remain saved in MongoDB.")
        return 0
    except SmokeFailure:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
