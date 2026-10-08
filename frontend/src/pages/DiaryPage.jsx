import { Fragment, useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { Card, ErrorBox, NeedField, Page } from "../components/ui.jsx";
import { browserRecognition, listenOnce, startRecording } from "../components/speech.js";
import { t } from "../i18n.js";
import { useApp } from "../state.jsx";

const ACT_ICON = { sowing: "🌱", fertilizer: "🧪", irrigation: "💧", pesticide: "🧴", weeding: "🌿", harvest: "🌾", sale: "₹", observation: "📝" };

export default function DiaryPage() {
  return <NeedField><Diary /></NeedField>;
}

function Diary() {
  const { fieldId, lang } = useApp();
  const [entries, setEntries] = useState([]);
  const [text, setText] = useState("");
  const [day, setDay] = useState(new Date().toISOString().slice(0, 10));
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [packet, setPacket] = useState(null);
  const [error, setError] = useState(null);
  const rec = useRef(null);

  const load = () => api.diary(fieldId).then(setEntries).catch(setError);
  useEffect(() => { load(); }, [fieldId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function save(audio) {
    setBusy(true);
    setError(null);
    try {
      await api.addDiary(fieldId, { text: audio ? null : text, audio, language: lang, entryDate: day });
      setText("");
      await load();
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
      try { setText(await listenOnce(lang)); } catch (e) { setError(e); } finally { setListening(false); }
      return;
    }
    if (!rec.current) {
      try { rec.current = await startRecording(); setListening(true); } catch (e) { setError(e); }
      return;
    }
    const blob = await rec.current.stop();
    rec.current = null;
    setListening(false);
    await save(blob);
  }

  async function onPhoto(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.seedPacket(file, fieldId, lang);
      setPacket(r.seed_packet);
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }

  return (
    <Page title={t("diary", lang)}>
      <Card title="New note">
        <div className="space-y-2 text-sm">
          <textarea rows={3} lang={lang} className="w-full rounded border border-black/15 px-3 py-2" value={text}
                    onChange={(e) => setText(e.target.value)}
                    placeholder={{ te: "ఉదా: ఈరోజు 2 బస్తాల యూరియా వేశాను", hi: "जैसे: आज 2 बोरी यूरिया डाला", en: "e.g. Applied 2 bags of urea today" }[lang]} />
          <div className="flex flex-wrap items-center gap-2">
            <input type="date" className="rounded border border-black/15 px-2 py-1" value={day} onChange={(e) => setDay(e.target.value)} />
            <button type="button" onClick={mic} className={`rounded border px-3 py-1.5 ${listening ? "border-[var(--status-critical)] text-[var(--status-critical)]" : "border-black/15"}`}>
              🎤 {listening ? t("listening", lang) : t("speak", lang)}
            </button>
            <button disabled={busy || !text.trim()} onClick={() => save(null)} className="rounded bg-[var(--brand)] px-3 py-1.5 text-white disabled:opacity-50">{t("save", lang)}</button>
            <label className="ml-auto cursor-pointer rounded border border-black/15 px-3 py-1.5">📷 Seed packet photo
              <input type="file" accept="image/*" capture="environment" className="hidden" onChange={onPhoto} />
            </label>
          </div>
          <p className="text-xs text-[var(--text-muted)]">Kshetra pulls out the activity, product, quantity and cost. Notes help it explain your yields and answer questions.</p>
        </div>
      </Card>
      <ErrorBox error={error} />
      {packet && (
        <Card title="Read from the seed packet">
          {Object.keys(packet).length === 0 ? <p className="text-sm">Could not read the label; try a sharper, well-lit photo.</p> : (
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 text-sm">
              {Object.entries(packet).map(([k, v]) => (
                <Fragment key={k}><dt className="text-[var(--text-secondary)]">{k.replaceAll("_", " ")}</dt><dd>{String(v)}</dd></Fragment>
              ))}
            </dl>
          )}
        </Card>
      )}
      <Card title="Diary">
        {entries.length === 0 ? <p className="text-sm text-[var(--text-secondary)]">No notes yet.</p> : (
          <ul className="divide-y divide-black/5">
            {entries.map((e) => (
              <li key={e.id} className="py-2 text-sm">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span aria-hidden>{ACT_ICON[e.activity_type] || "📝"}</span>
                  <span className="tabular text-[var(--text-secondary)]">{e.entry_date}</span>
                  <span className="capitalize">{e.activity_type}</span>
                </div>
                <p lang={e.language} className="mt-0.5">{e.raw_text}</p>
                {e.text_en && e.text_en !== e.raw_text && <p className="text-xs text-[var(--text-muted)]">{e.text_en}</p>}
                {Object.keys(e.structured || {}).length > 1 && (
                  <div className="mt-1 flex flex-wrap gap-1 text-xs">
                    {Object.entries(e.structured).filter(([k]) => k !== "activity_type").map(([k, v]) => (
                      <span key={k} className="rounded bg-[var(--page)] px-1.5 py-0.5">{k.replaceAll("_", " ")}: {String(v)}</span>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </Page>
  );
}
