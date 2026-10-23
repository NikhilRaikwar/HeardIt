#!/usr/bin/env python3
"""Generate four real Fish Audio demo MP3s for the static landing page."""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SENTENCE = "I thought you said you'd be here by now."
MODEL = "s2.1-pro-free"
FISH_URL = "https://api.fish.audio/v1/tts"
MAX_AUDIO_BYTES = 4 * 1024 * 1024
SAMPLES = [
    ("curious", "Curious", "[curious, gently inquisitive]"),
    ("annoyed", "Annoyed", "[annoyed, impatient, slightly frustrated]"),
    ("hurt", "Hurt", "[hurt, disappointed, quiet and vulnerable]"),
    ("playful", "Playful", "[playful, teasing, light-hearted]"),
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


def generate_clip(api_key, direction, voice_id):
    speech = " ".join(f"{direction} {SENTENCE}".split())
    body = {"text": speech, "format": "mp3"}
    if voice_id:
        body["reference_id"] = voice_id
    request = Request(
        FISH_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "model": MODEL,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"audio/mpeg", "audio/mp3", "application/octet-stream"}:
                raise RuntimeError("Fish Audio returned a non-audio response.")
            audio = response.read(MAX_AUDIO_BYTES + 1)
    except HTTPError as error:
        # Do not include upstream bodies or request headers: they may contain sensitive data.
        raise RuntimeError(f"Fish Audio request failed with HTTP {error.code}.") from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError("Fish Audio could not be reached before the request timed out.") from error

    is_mp3 = len(audio) >= 100 and (audio[:3] == b"ID3" or (audio[0] == 255 and audio[1] & 224 == 224))
    if len(audio) > MAX_AUDIO_BYTES or not is_mp3:
        raise RuntimeError("Fish Audio response was missing or was not a valid MP3 within the 4 MB limit.")
    return audio


def main():
    load_local_env()
    api_key = os.environ.get("FISH_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Set FISH_API_KEY in the environment or repository .env, then run this command again.")
    configured_model = os.environ.get("FISH_TTS_MODEL", MODEL).strip()
    if configured_model != MODEL:
        raise SystemExit(f"This demo generator requires FISH_TTS_MODEL={MODEL}.")

    target = ROOT / "public" / "demo"
    target.mkdir(parents=True, exist_ok=True)
    voice_id = os.environ.get("FISH_DEFAULT_VOICE_ID", "").strip() or None
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    generated = []

    with tempfile.TemporaryDirectory(prefix="heardit-demo-", dir=target) as temporary_directory:
        temporary = Path(temporary_directory)
        for sample_id, label, direction in SAMPLES:
            try:
                audio = generate_clip(api_key, direction, voice_id)
            except RuntimeError as error:
                raise SystemExit(f"Could not generate the {label} sample: {error}") from error
            (temporary / f"{sample_id}.mp3").write_bytes(audio)
            generated.append({
                "id": sample_id,
                "label": label,
                "text": SENTENCE,
                "model": MODEL,
                "generated_at": generated_at,
            })
            print(f"Generated real Fish Audio clip: {label}")

        for sample_id, *_ in SAMPLES:
            (temporary / f"{sample_id}.mp3").replace(target / f"{sample_id}.mp3")
        manifest_temporary = temporary / "manifest.json"
        manifest_temporary.write_text(json.dumps(generated, indent=2) + "\n", encoding="utf-8")
        manifest_temporary.replace(target / "manifest.json")

    print("Wrote four MP3 files and public/demo/manifest.json. Review the clips before committing them.")


if __name__ == "__main__":
    main()
