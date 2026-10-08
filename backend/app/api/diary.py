"""F11 voice farm diary and seed packet OCR."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from psycopg.types.json import Jsonb

from app.api.ask import _audio_format
from app.api.deps import db, field_or_404
from app.services import diary_parser, memory, ocr, voice

router = APIRouter(prefix="/api", tags=["diary"])
Lang = Literal["te", "hi", "en"]
MAX_UPLOAD = 15 * 1024 * 1024


def _season_for(conn, field_id: str, day: date) -> str | None:
    row = conn.execute(
        """SELECT id::text FROM seasons WHERE field_id = %s
             AND %s BETWEEN sowing_date - 30 AND coalesce(harvest_date, sowing_date + 240) + 20
           ORDER BY abs(%s - sowing_date) LIMIT 1""",
        (field_id, day, day),
    ).fetchone()
    return row["id"] if row else None


@router.post("/fields/{field_id}/diary", status_code=201)
async def add_entry(field_id: str, text: str | None = Form(None), language: Lang = Form("te"),
                    entry_date: date | None = Form(None), audio: UploadFile | None = File(None),
                    conn=Depends(db)):
    f = field_or_404(conn, field_id)
    heard = None
    if audio is not None:
        data = await audio.read()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "audio too large")
        try:
            heard = voice.transcribe(data, language, audio_format=_audio_format(audio.filename))
        except voice.VoiceError as exc:
            raise HTTPException(503, f"speech recognition unavailable: {exc}") from exc
        text = heard["text"]
    if not text or not text.strip():
        raise HTTPException(422, "send text or audio")
    day = entry_date or date.today()  # noqa: DTZ011
    text_en = voice.translate_to_english(text, language)
    parsed = diary_parser.parse_note(text)
    if text_en and text_en != text:
        # The English translation fills gaps; what was found in the farmer's own words wins.
        if parsed.get("activity_type") == "observation":
            parsed.pop("activity_type")
        parsed = {**diary_parser.parse_note(text_en), **parsed}
    row = conn.execute(
        """INSERT INTO diary_entries (field_id, season_id, entry_date, raw_text, text_en, language, activity_type, structured)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id::text, entry_date, activity_type, structured""",
        (field_id, _season_for(conn, field_id, day), day, text.strip(), text_en, language,
         parsed.get("activity_type"), Jsonb(parsed)),
    ).fetchone()
    memory.remember(conn, field_id=field_id, owner_id=f["owner_id"], kind="diary", source_id=row["id"],
                    content=text_en or text, language=language, metadata={"activity_type": parsed.get("activity_type")})
    if parsed.get("activity_type") in ("sowing", "harvest", "irrigation", "fertilizer", "pesticide"):
        kind = "pesticide" if parsed["activity_type"] == "pesticide" else parsed["activity_type"]
        conn.execute("""INSERT INTO events (field_id, season_id, event_type, start_date, origin, evidence)
                        VALUES (%s, %s, %s, %s, 'diary', %s)""",
                     (field_id, _season_for(conn, field_id, day), kind, day, Jsonb(parsed)))
    conn.commit()
    return {**row, "raw_text": text.strip(), "text_en": text_en, "heard": heard}


@router.get("/fields/{field_id}/diary")
def list_entries(field_id: str, conn=Depends(db)):
    field_or_404(conn, field_id)
    return conn.execute(
        """SELECT id::text, season_id::text, entry_date, raw_text, text_en, language, activity_type, structured,
                  seed_packet, created_at
           FROM diary_entries WHERE field_id = %s ORDER BY entry_date DESC, created_at DESC""",
        (field_id,),
    ).fetchall()


@router.post("/seed-packet")
async def read_seed_packet(image: UploadFile = File(...), field_id: str | None = Form(None),
                           language: Lang = Form("en"), conn=Depends(db)):
    data = await image.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "image too large")
    try:
        text = ocr.read_image(data)
    except Exception as exc:
        raise HTTPException(422, f"could not read the image: {exc}") from exc
    packet = ocr.parse_seed_packet(text)
    result = {"seed_packet": packet, "text": text}
    if field_id:
        field_or_404(conn, field_id)
        day = date.today()  # noqa: DTZ011
        summary = "Seed packet: " + ", ".join(f"{k} {v}" for k, v in packet.items()) if packet else "Seed packet photo"
        row = conn.execute(
            """INSERT INTO diary_entries (field_id, season_id, entry_date, raw_text, language, activity_type,
                                          structured, seed_packet)
               VALUES (%s, %s, %s, %s, %s, 'sowing', %s, %s) RETURNING id::text""",
            (field_id, _season_for(conn, field_id, day), day, summary, language, Jsonb({}), Jsonb(packet)),
        ).fetchone()
        conn.commit()
        result["diary_entry_id"] = row["id"]
    return result
