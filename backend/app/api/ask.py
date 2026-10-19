"""F10 Ask your field: text or voice questions in Telugu, Hindi, English."""
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.auth import current_user
from app.api.deps import db, field_or_404
from app.services import llm, voice

router = APIRouter(prefix="/api", tags=["ask"])
Lang = Literal["te", "hi", "en"]


class Question(BaseModel):
    question: str = Field(..., min_length=2, max_length=1000)
    language: Lang = "en"


@router.post("/fields/{field_id}/ask")
def ask(field_id: str, body: Question, conn=Depends(db), user=Depends(current_user)):
    f = field_or_404(conn, field_id, user)
    return llm.ask(conn, field_id, body.question, body.language, user_id=f["owner_id"])


@router.post("/fields/{field_id}/ask/voice")
async def ask_voice(field_id: str, audio: UploadFile = File(...), language: Lang = Form("te"), conn=Depends(db), user=Depends(current_user)):
    f = field_or_404(conn, field_id, user)
    data = await audio.read()
    try:
        heard = voice.transcribe(data, language, audio_format=_audio_format(audio.filename))
    except voice.VoiceError as exc:
        raise HTTPException(503, f"speech recognition unavailable: {exc}") from exc
    result = llm.ask(conn, field_id, heard["text"], language, user_id=f["owner_id"])
    result["heard"] = heard
    return result


@router.get("/fields/{field_id}/ask/history")
def history(field_id: str, limit: int = 20, conn=Depends(db), user=Depends(current_user)):
    field_or_404(conn, field_id, user)
    return conn.execute(
        """SELECT id::text, language, question, answer, answered, sources, llm_provider, created_at
           FROM qa_log WHERE field_id = %s ORDER BY created_at DESC LIMIT %s""",
        (field_id, limit),
    ).fetchall()


def _audio_format(name: str | None) -> str:
    ext = (name or "").rsplit(".", 1)[-1].lower()
    return ext if ext in ("wav", "mp3", "flac", "ogg", "webm") else "wav"
