import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { Card, ErrorBox, NeedField, Page } from "../components/ui.jsx";
import { browserRecognition, listenOnce, speak, startRecording } from "../components/speech.js";
import { t } from "../i18n.js";
import { useApp } from "../state.jsx";

const EXAMPLES = {
  en: ["Why was my last kharif yield low?", "What did similar fields do differently?", "If I sow paddy on 10 July with full irrigation, what profit can I expect?"],
  te: ["నా గత ఖరీఫ్ దిగుబడి ఎందుకు తక్కువగా ఉంది?", "నా పొలంలో ఏ పంటలు వేశాను?", "జూలై 10న వరి వేస్తే లాభం ఎంత?"],
  hi: ["मेरी पिछली खरीफ़ उपज कम क्यों थी?", "मेरे खेत में कौन सी फसलें उगाई गईं?", "10 जुलाई को धान बोऊँ तो कितना मुनाफ़ा होगा?"],
};

export default function AskPage() {
  return <NeedField><Ask /></NeedField>;
}

function Ask() {
  const { fieldId, lang } = useApp();
  const [question, setQuestion] = useState("");
  const [chat, setChat] = useState([]);
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState(null);
  const recording = useRef(null);

  useEffect(() => {
    api.askHistory(fieldId).then((h) => setChat(h.reverse().map((x) => ({ ...x, sources: x.sources || [] })))).catch(() => {});
  }, [fieldId]);

  async function send(q) {
    if (!q.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.ask(fieldId, q, lang);
      setChat((c) => [...c, { question: q, ...r }]);
      setQuestion("");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function mic() {
    setError(null);
    if (browserRecognition()) {
      setListening(true);
      try {
        const heard = await listenOnce(lang);
        setQuestion(heard);
        await send(heard);
      } catch (e) {
        setError(e);
      } finally {
        setListening(false);
      }
      return;
    }
    // No browser recogniser: record and let the server transcribe (Bhashini / Whisper).
    if (!recording.current) {
      try {
        recording.current = await startRecording();
        setListening(true);
      } catch (e) {
        setError(e);
      }
      return;
    }
    const blob = await recording.current.stop();
    recording.current = null;
    setListening(false);
    setBusy(true);
    try {
      const r = await api.askVoice(fieldId, blob, lang);
      setChat((c) => [...c, { question: r.heard?.text || "(voice)", ...r }]);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page title={t("ask", lang)}>
      <Card>
        <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); send(question); }}>
          <input className="min-w-0 flex-1 rounded border border-black/15 px-3 py-2" value={question} lang={lang}
                 onChange={(e) => setQuestion(e.target.value)} placeholder={EXAMPLES[lang][0]} />
          <button type="button" onClick={mic} aria-pressed={listening}
                  className={`rounded border px-3 py-2 ${listening ? "border-[var(--status-critical)] text-[var(--status-critical)]" : "border-black/15"}`}>
            🎤 {listening ? t("listening", lang) : t("speak", lang)}
          </button>
          <button disabled={busy} className="rounded bg-[var(--brand)] px-4 py-2 text-white disabled:opacity-50">{t("send", lang)}</button>
        </form>
        <div className="mt-2 flex flex-wrap gap-2">
          {EXAMPLES[lang].map((q) => (
            <button key={q} onClick={() => send(q)} className="rounded-full border border-black/10 bg-[var(--page)] px-3 py-1 text-xs">{q}</button>
          ))}
        </div>
        <p className="mt-2 text-xs text-[var(--text-muted)]">Answers come only from your field's data, with the numbers they used. If the data cannot answer, Kshetra says so.</p>
      </Card>
      <ErrorBox error={error} />
      {busy && <p className="text-sm text-[var(--text-secondary)]">Thinking…</p>}
      <div className="space-y-3">
        {[...chat].reverse().map((m, i) => (
          <Card key={m.id || i}>
            <p className="text-sm font-medium">{m.question}</p>
            <p className={`mt-2 whitespace-pre-wrap ${m.answered === false ? "text-[var(--text-secondary)]" : ""}`}>{m.answer}</p>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
              <button onClick={() => speak(m.answer, m.language || lang).catch(setError)} className="rounded border border-black/10 px-2 py-0.5">🔊 Listen</button>
              {m.llm_provider || m.provider ? <span className="text-[var(--text-muted)]">via {m.llm_provider || m.provider}</span> : null}
            </div>
            {m.sources?.length > 0 && (
              <details className="mt-2 text-xs">
                <summary className="cursor-pointer text-[var(--text-secondary)]">{t("sources", lang)} ({m.sources.length})</summary>
                {m.sources.map((s, j) => (
                  <div key={j} className="mt-1 rounded bg-[var(--page)] p-2">
                    <div className="font-mono">{s.tool}({Object.entries(s.args || {}).map(([k, v]) => `${k}=${v}`).join(", ")})</div>
                    <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap text-[11px] text-[var(--text-secondary)]">{JSON.stringify(s.data, null, 1)}</pre>
                  </div>
                ))}
              </details>
            )}
          </Card>
        ))}
      </div>
    </Page>
  );
}
