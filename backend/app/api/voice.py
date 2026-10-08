"""Speech-to-text and text-to-speech endpoints (server fallbacks for the browser)."""
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.ask import _audio_format
from app.services import voice

router = APIRouter(prefix="/api/voice", tags=["voice"])
Lang = Literal["te", "hi", "en"]


class SpeakIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    language: Lang = "te"


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...), language: Lang = Form("te")):
    try:
        return voice.transcribe(await audio.read(), language, audio_format=_audio_format(audio.filename))
    except voice.VoiceError as exc:
        raise HTTPException(503, f"speech recognition unavailable: {exc}") from exc


@router.post("/speak")
def speak(body: SpeakIn):
    try:
        return Response(voice.speak(body.text, body.language), media_type="audio/mpeg")
    except Exception as exc:
        raise HTTPException(503, f"text-to-speech unavailable: {exc}") from exc
