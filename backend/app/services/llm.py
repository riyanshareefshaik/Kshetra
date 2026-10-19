"""Ask your field (F10): LLM answers grounded only in tool calls on Kshetra's database.

Providers, tried in LLM_PROVIDER_ORDER (all free):
  * groq   - Groq free tier, OpenAI-compatible API; default model openai/gpt-oss-120b (Apache 2.0 weights)
  * gemini - Google Gemini API free tier; default alias gemini-flash-latest
  * ollama - local, offline; default qwen2.5:7b (Apache 2.0)

Grounding rules enforced in code, not only in the prompt:
  * the field id is bound server-side; the model cannot read other fields;
  * if the model answers without using any tool result, the answer is
    replaced by "I don't know" in the farmer's language;
  * every tool result is returned to the app as a source.
Each Q&A is saved to qa_log and semantic memory (Layer 4).
"""
import json
import logging
import uuid

import httpx
from psycopg.types.json import Jsonb

from app.config import get_settings
from app.services import memory
from app.services.llm_tools import TOOLS, call_tool

log = logging.getLogger(__name__)
MAX_TOOL_ROUNDS = 5

LANG_NAMES = {"te": "Telugu", "hi": "Hindi", "en": "English"}
DONT_KNOW = {
    "en": "I don't know. Your field's data does not answer this question.",
    "te": "నాకు తెలియదు. మీ పొలం డేటాలో ఈ ప్రశ్నకు సమాధానం లేదు.",
    "hi": "मुझे नहीं पता। आपके खेत के डेटा से इस प्रश्न का उत्तर नहीं मिलता।",
}

SYSTEM_PROMPT = """You are Kshetra, an assistant for one farmer's field in India.
Rules:
1. Answer ONLY from the results of the tools. Never use outside knowledge, never guess numbers.
2. Always call at least one tool before answering.
3. Quote the numbers you use with their units (t/ha, mm, days, Rs) and say which tool result they came from.
4. Yields are ranges; never give a single exact yield. Reasons are "likely reasons", never certain causes.
5. If the tools do not contain the answer, reply exactly: "{dont_know}"
6. Reply in {language}, in short simple sentences a farmer understands.
"""


class ProviderError(RuntimeError):
    pass


# ----------------------------------------------------------------- providers
# Internal message format is OpenAI-style: {"role", "content", "tool_calls"?, "tool_call_id"?, "name"?}

def _openai_tools():
    return [{"type": "function", "function": t} for t in TOOLS]


def _openai_messages(messages: list[dict]) -> list[dict]:
    """Drop the internal 'name' on tool messages (only Gemini needs it)."""
    return [{k: v for k, v in m.items() if not (m["role"] == "tool" and k == "name")} for m in messages]


def groq_chat(client: httpx.Client, messages: list[dict]) -> dict:
    s = get_settings()
    if not s.groq_api_key:
        raise ProviderError("GROQ_API_KEY not set")
    r = client.post("https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {s.groq_api_key}"},
                    json={"model": s.groq_model, "messages": _openai_messages(messages), "tools": _openai_tools(),
                          "tool_choice": "auto", "temperature": 0.1}, timeout=60)
    if r.status_code != 200:
        raise ProviderError(f"groq {r.status_code}: {r.text[:200]}")
    msg = r.json()["choices"][0]["message"]
    calls = [{"id": c["id"], "name": c["function"]["name"],
              "args": json.loads(c["function"].get("arguments") or "{}")} for c in msg.get("tool_calls") or []]
    return {"content": msg.get("content") or "", "tool_calls": calls}


def ollama_chat(client: httpx.Client, messages: list[dict]) -> dict:
    s = get_settings()
    r = client.post(f"{s.ollama_url}/api/chat",
                    json={"model": s.ollama_model, "messages": _openai_messages(messages), "tools": _openai_tools(),
                          "stream": False, "options": {"temperature": 0.1}}, timeout=180)
    if r.status_code != 200:
        raise ProviderError(f"ollama {r.status_code}: {r.text[:200]}")
    msg = r.json()["message"]
    calls = [{"id": f"call_{i}", "name": c["function"]["name"], "args": c["function"].get("arguments") or {}}
             for i, c in enumerate(msg.get("tool_calls") or [])]
    return {"content": msg.get("content") or "", "tool_calls": calls}


def _to_gemini(messages: list[dict]) -> tuple[str, list[dict]]:
    system, contents = "", []
    for m in messages:
        if m["role"] == "system":
            system = m["content"]
        elif m["role"] == "user":
            contents.append({"role": "user", "parts": [{"text": m["content"]}]})
        elif m["role"] == "assistant":
            parts = [{"text": m["content"]}] if m.get("content") else []
            parts += [{"functionCall": {"name": c["function"]["name"], "args": json.loads(c["function"]["arguments"])}}
                      for c in m.get("tool_calls") or []]
            contents.append({"role": "model", "parts": parts})
        elif m["role"] == "tool":
            contents.append({"role": "user", "parts": [{"functionResponse": {
                "name": m["name"], "response": {"result": json.loads(m["content"])}}}]})
    return system, contents


def gemini_chat(client: httpx.Client, messages: list[dict]) -> dict:
    s = get_settings()
    if not s.gemini_api_key:
        raise ProviderError("GEMINI_API_KEY not set")
    system, contents = _to_gemini(messages)
    r = client.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{s.gemini_model}:generateContent",
        headers={"x-goog-api-key": s.gemini_api_key},
        json={"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
              "tools": [{"functionDeclarations": TOOLS}], "generationConfig": {"temperature": 0.1}},
        timeout=60)
    if r.status_code != 200:
        raise ProviderError(f"gemini {r.status_code}: {r.text[:200]}")
    parts = r.json()["candidates"][0]["content"].get("parts", [])
    text = "".join(p.get("text", "") for p in parts)
    calls = [{"id": f"call_{uuid.uuid4().hex[:8]}", "name": p["functionCall"]["name"],
              "args": p["functionCall"].get("args") or {}} for p in parts if "functionCall" in p]
    return {"content": text, "tool_calls": calls}


PROVIDERS = {"groq": groq_chat, "gemini": gemini_chat, "ollama": ollama_chat}


# ----------------------------------------------------------------- ask loop

def _run(provider, client, conn, field_id: str, messages: list[dict]) -> tuple[str, list[dict]]:
    used = []
    for _ in range(MAX_TOOL_ROUNDS):
        reply = provider(client, messages)
        if not reply["tool_calls"]:
            return reply["content"].strip(), used
        messages.append({"role": "assistant", "content": reply["content"] or "",
                         "tool_calls": [{"id": c["id"], "type": "function", "function": {
                             "name": c["name"], "arguments": json.dumps(c["args"])}} for c in reply["tool_calls"]]})
        for c in reply["tool_calls"]:
            result = call_tool(conn, field_id, c["name"], c["args"])
            used.append({"tool": c["name"], "args": c["args"], "result": result})
            messages.append({"role": "tool", "tool_call_id": c["id"], "name": c["name"],
                             "content": json.dumps(result, default=str)})
    return "", used


def ask(conn, field_id: str, question: str, language: str = "en", user_id: str | None = None,
        client: httpx.Client | None = None, providers: dict | None = None) -> dict:
    language = language if language in LANG_NAMES else "en"
    order = [p.strip() for p in get_settings().llm_provider_order.split(",") if p.strip()]
    providers = providers or PROVIDERS
    own = client is None
    client = client or httpx.Client()
    errors, answer, used, provider_name = [], "", [], None
    try:
        for name in order:
            if name not in providers:
                continue
            messages = [{"role": "system", "content": SYSTEM_PROMPT.format(
                dont_know=DONT_KNOW[language], language=LANG_NAMES[language])},
                {"role": "user", "content": question}]
            try:
                answer, used = _run(providers[name], client, conn, field_id, messages)
                provider_name = name
                break
            except (ProviderError, httpx.HTTPError, KeyError, ValueError) as exc:
                errors.append(f"{name}: {exc}")
                log.warning("LLM provider %s failed: %s", name, exc)
    finally:
        if own:
            client.close()

    grounded = [u for u in used if "error" not in u["result"]]
    answered = bool(answer) and bool(grounded) and DONT_KNOW[language] not in answer
    if provider_name is None:
        answer = DONT_KNOW[language] + " (No language model is reachable right now.)"
    elif not answered:
        answer = DONT_KNOW[language]
    sources = [{"tool": u["tool"], "args": u["args"], "data": u["result"]} for u in grounded]

    qa_id = conn.execute(
        """INSERT INTO qa_log (field_id, user_id, language, question, answer, tool_calls, sources, answered, llm_provider)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id::text""",
        (field_id, user_id, language, question, answer, Jsonb(used), Jsonb(sources), answered, provider_name),
    ).fetchone()["id"]
    memory.remember(conn, field_id=field_id, owner_id=user_id, kind="qa", source_id=qa_id,
                    content=f"Q: {question}\nA: {answer}", language=language)
    conn.commit()
    return {"id": qa_id, "answer": answer, "answered": answered, "language": language,
            "sources": sources, "provider": provider_name, "errors": errors}
