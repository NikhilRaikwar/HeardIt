#!/usr/bin/env python3
"""Generate the four public HeardIt demo clips and write their asset manifest."""

import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SENTENCE = "I thought you said you'd be here by now."
SAMPLES = [
    ("Curious", "[curious, gently inquisitive]"),
    ("Annoyed", "[annoyed, impatient, slightly frustrated]"),
    ("Hurt", "[hurt, disappointed, quiet and vulnerable]"),
    ("Playful", "[playful, teasing, light-hearted]"),
]


def load_local_env():
    env_file = ROOT / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("#") or "=" not in candidate:
            continue
        key, value = candidate.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def main():
    load_local_env()
    api_origin = (os.environ.get("HEARDIT_API_URL") or os.environ.get("API_INTERNAL_URL") or "http://127.0.0.1:8000").rstrip("/")
    manifest = []
    for label, direction in SAMPLES:
        body = json.dumps({"sentence": SENTENCE, "direction": direction}).encode()
        request = Request(
            f"{api_origin}/api/v1/audio/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=120) as response:
                asset = json.loads(response.read())
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise SystemExit(f"Could not generate the {label} sample: {error}") from error
        audio_id = asset.get("audio_id")
        if not isinstance(audio_id, str) or not audio_id:
            raise SystemExit(f"The API did not return a saved audio asset for {label}.")
        manifest.append({"label": label, "direction": direction, "audio_id": audio_id})
        print(f"Saved Fish Audio sample: {label}")

    target = ROOT / "public" / "demo-audio.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    print(f"Wrote verified sample manifest to {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
