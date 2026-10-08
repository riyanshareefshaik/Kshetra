"""Speech in and out (F10, F11) for Telugu, Hindi and English.

Speech-to-text, first that works:
  1. Bhashini (Government of India, free; BHASHINI_USER_ID + BHASHINI_KEY from bhashini.gov.in)
  2. faster-whisper (MIT, runs locally; optional, requirements-ai.txt)
The browser's Web Speech API is used before either when available (frontend).

Text-to-speech: the browser's speechSynthesis first (frontend); gTTS (MIT)
as a server fallback. gTTS uses an unofficial Google Translate endpoint, so it
can stop working at any time; nothing depends on it.
"""
import base64
import io
import logging
import tempfile
from functools import lru_cache

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

BHASHINI_CONFIG_URL = "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline"
BHASHINI_INFER_URL = "https://dhruva-api.bhashini.gov.in/services/inference/pipeline"
BHASHINI_PIPELINE_ID = "64392f96daac500b55c543cd"   # MeitY pipeline


class VoiceError(RuntimeError):
    pass


def _bhashini_config(client: httpx.Client, task: dict) -> tuple[str, dict, str]:
    s = get_settings()
    if not (s.bhashini_key and s.bhashini_user_id):
        raise VoiceError("BHASHINI_KEY / BHASHINI_USER_ID not set")
    r = client.post(BHASHINI_CONFIG_URL, timeout=30,
                    headers={"userID": s.bhashini_user_id, "ulcaApiKey": s.bhashini_key},
                    json={"pipelineTasks": [task], "pipelineRequestConfig": {"pipelineId": BHASHINI_PIPELINE_ID}})
    if r.status_code != 200:
        raise VoiceError(f"bhashini config {r.status_code}")
    cfg = r.json()
    endpoint = cfg.get("pipelineInferenceAPIEndPoint", {})
    key = endpoint.get("inferenceApiKey", {})
    service_id = cfg["pipelineResponseConfig"][0]["config"][0]["serviceId"]
    return endpoint.get("callbackUrl") or BHASHINI_INFER_URL, {key.get("name", "Authorization"): key["value"]}, service_id


def bhashini_asr(client: httpx.Client, audio: bytes, language: str, audio_format: str = "wav") -> str:
    task = {"taskType": "asr", "config": {"language": {"sourceLanguage": language}}}
    url, headers, service_id = _bhashini_config(client, task)
    task["config"].update({"serviceId": service_id, "audioFormat": audio_format, "samplingRate": 16000})
    r = client.post(url, headers=headers, timeout=60, json={
        "pipelineTasks": [task], "inputData": {"audio": [{"audioContent": base64.b64encode(audio).decode()}]}})
    if r.status_code != 200:
        raise VoiceError(f"bhashini asr {r.status_code}")
    return r.json()["pipelineResponse"][0]["output"][0]["source"].strip()


def bhashini_translate(client: httpx.Client, text: str, source: str, target: str = "en") -> str:
    task = {"taskType": "translation", "config": {"language": {"sourceLanguage": source, "targetLanguage": target}}}
    url, headers, service_id = _bhashini_config(client, task)
    task["config"]["serviceId"] = service_id
    r = client.post(url, headers=headers, timeout=30,
                    json={"pipelineTasks": [task], "inputData": {"input": [{"source": text}]}})
    if r.status_code != 200:
        raise VoiceError(f"bhashini translation {r.status_code}")
    return r.json()["pipelineResponse"][0]["output"][0]["target"].strip()


@lru_cache(maxsize=1)
def _whisper():
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise VoiceError("faster-whisper not installed (pip install -r requirements-ai.txt)") from exc
    return WhisperModel(get_settings().whisper_model, device="cpu", compute_type="int8")


def whisper_asr(audio: bytes, language: str) -> str:
    with tempfile.NamedTemporaryFile(suffix=".audio") as f:
        f.write(audio)
        f.flush()
        segments, _ = _whisper().transcribe(f.name, language=language, vad_filter=True)
        return " ".join(seg.text.strip() for seg in segments).strip()


def transcribe(audio: bytes, language: str, audio_format: str = "wav", client: httpx.Client | None = None) -> dict:
    errors = []
    with (client or httpx.Client()) as c:
        try:
            return {"text": bhashini_asr(c, audio, language, audio_format), "engine": "bhashini"}
        except (VoiceError, httpx.HTTPError, KeyError, IndexError) as exc:
            errors.append(f"bhashini: {exc}")
    try:
        return {"text": whisper_asr(audio, language), "engine": "whisper"}
    except Exception as exc:  # noqa: BLE001 - report every engine's failure together
        errors.append(f"whisper: {exc}")
    raise VoiceError("; ".join(errors))


def translate_to_english(text: str, language: str) -> str | None:
    if language == "en":
        return text
    try:
        with httpx.Client() as c:
            return bhashini_translate(c, text, language)
    except (VoiceError, httpx.HTTPError, KeyError, IndexError) as exc:
        log.info("translation unavailable: %s", exc)
        return None


def speak(text: str, language: str) -> bytes:
    from gtts import gTTS

    buf = io.BytesIO()
    gTTS(text=text, lang=language if language in ("te", "hi", "en") else "en").write_to_fp(buf)
    return buf.getvalue()
