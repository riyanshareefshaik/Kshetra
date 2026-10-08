import { lazy, Suspense, useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { authEnabled, signOut } from "./auth.js";
import { LANGS, t } from "./i18n.js";
import { useApp } from "./state.jsx";
import MapPage from "./pages/MapPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import { Loading } from "./components/ui.jsx";
import { browserRecognition, listenOnce, speak } from "./components/speech.js";

const page = (load) => lazy(load);
const PAGES = [
  { path: "/", key: "nav.map", element: <MapPage />, words: ["map", "field", "మ్యాప్", "పొలం", "नक्शा", "खेत"] },
  { path: "/today", key: "nav.today", Comp: page(() => import("./pages/TodayPage.jsx")), words: ["today", "weather", "rain", "irrigation", "pest", "ఈరోజు", "వాతావరణం", "వర్షం", "నీరు", "పురుగు", "आज", "मौसम", "बारिश", "सिंचाई", "कीट"] },
  { path: "/timeline", key: "nav.timeline", Comp: page(() => import("./pages/TimelinePage.jsx")), words: ["history", "timeline", "season", "చరిత్ర", "కాలం", "इतिहास"] },
  { path: "/why", key: "nav.why", Comp: page(() => import("./pages/WhyPage.jsx")), words: ["why", "reason", "twin", "similar", "ఎందుకు", "కారణం", "పోలిక", "क्यों", "कारण", "समान"] },
  { path: "/what-if", key: "nav.whatIf", Comp: page(() => import("./pages/WhatIfPage.jsx")), words: ["what if", "simulate", "ఒకవేళ", "अगर"] },
  { path: "/planner", key: "nav.planner", Comp: page(() => import("./pages/PlannerPage.jsx")), words: ["plan", "next season", "ప్రణాళిక", "योजना"] },
  { path: "/fertilizer", key: "nav.fertilizer", Comp: page(() => import("./pages/FertilizerPage.jsx")), words: ["fertilizer", "fertiliser", "urea", "soil", "ఎరువు", "యూరియా", "మట్టి", "खाद", "यूरिया", "मिट्टी"] },
  { path: "/market", key: "nav.market", Comp: page(() => import("./pages/MarketPage.jsx")), words: ["market", "price", "sell", "mandi", "మార్కెట్", "ధర", "అమ్మ", "मंडी", "भाव", "बेच"] },
  { path: "/ask", key: "nav.ask", Comp: page(() => import("./pages/AskPage.jsx")), words: ["ask", "question", "అడుగు", "ప్రశ్న", "पूछ", "सवाल"] },
  { path: "/diary", key: "nav.diary", Comp: page(() => import("./pages/DiaryPage.jsx")), words: ["diary", "note", "డైరీ", "నోట్", "डायरी"] },
  { path: "/report", key: "nav.report", Comp: page(() => import("./pages/ReportPage.jsx")), words: ["report", "insurance", "claim", "pdf", "నివేదిక", "బీమా", "रिपोर्ट", "बीमा"] },
  { path: "/schemes", key: "nav.schemes", Comp: page(() => import("./pages/SchemesPage.jsx")), words: ["scheme", "subsidy", "government", "పథకం", "సబ్సిడీ", "ప్రభుత్వ", "योजना", "सरकार", "सब्सिडी"] },
  { path: "/group", key: "nav.group", Comp: page(() => import("./pages/GroupPage.jsx")), words: ["group", "fpo", "సమూహం", "సంఘం", "समूह"] },
];
const InsightsPage = page(() => import("./pages/InsightsPage.jsx"));

function VoiceNav() {
  const { lang } = useApp();
  const navigate = useNavigate();
  const { search } = useLocation();
  const [busy, setBusy] = useState(false);
  if (!browserRecognition()) return null;
  async function go() {
    setBusy(true);
    try {
      const heard = (await listenOnce(lang)).toLowerCase();
      // Words like "plan" also appear inside "planner"; prefer the longest match.
      const hit = PAGES.map((p) => ({ p, w: p.words.filter((w) => heard.includes(w)).sort((a, b) => b.length - a.length)[0] }))
        .filter((x) => x.w).sort((a, b) => b.w.length - a.w.length)[0];
      if (hit) {
        speak(t("voice.going", lang, { page: t(hit.p.key, lang) }), lang).catch(() => {});
        navigate({ pathname: hit.p.path, search });
      } else {
        speak(t("voice.unknown", lang, { help: t("voice.help", lang) }), lang).catch(() => {});
      }
    } catch {
      /* nothing heard */
    } finally {
      setBusy(false);
    }
  }
  return (
    <button onClick={go} title={t("voice.help", lang)} aria-label={t("voice.help", lang)}
            className={`rounded border px-2 py-1 text-sm ${busy ? "border-[var(--status-critical)] text-[var(--status-critical)]" : "border-black/15"}`}>
      🎤 {busy ? t("listening", lang) : ""}
    </button>
  );
}

function InstallButton() {
  const { lang } = useApp();
  const [prompt, setPrompt] = useState(null);
  useEffect(() => {
    const onPrompt = (e) => { e.preventDefault(); setPrompt(e); };
    window.addEventListener("beforeinstallprompt", onPrompt);
    return () => window.removeEventListener("beforeinstallprompt", onPrompt);
  }, []);
  if (!prompt) return null;
  return (
    <button className="rounded border border-[var(--brand)] px-2 py-1 text-sm text-[var(--brand)]"
            onClick={async () => { prompt.prompt(); await prompt.userChoice; setPrompt(null); }}>
      ⬇ {t("install", lang)}
    </button>
  );
}

export default function App() {
  const { fields, fieldId, selectField, lang, setLang, error, online, session, signedIn } = useApp();
  const { search } = useLocation();
  if (authEnabled && session === undefined) return <div className="p-6"><Loading /></div>;
  if (!signedIn) return <LoginPage />;
  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-black/10 bg-white">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-2">
          <span className="text-lg font-semibold text-[var(--brand)]">Kshetra</span>
          <select aria-label={t("chooseField", lang)} className="max-w-[14rem] rounded border border-black/15 px-2 py-1 text-sm"
                  value={fieldId || ""} onChange={(e) => selectField(e.target.value || null)}>
            <option value="">{t("chooseField", lang)}</option>
            {fields.map((f) => <option key={f.id} value={f.id}>{f.name || `Field ${f.id.slice(0, 4)}`}</option>)}
          </select>
          <div className="ml-auto flex items-center gap-2">
            <InstallButton />
            <VoiceNav />
            <select aria-label="Language" className="rounded border border-black/15 px-2 py-1 text-sm"
                    value={lang} onChange={(e) => setLang(e.target.value)}>
              {Object.entries(LANGS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            {authEnabled && (
              <button className="rounded border border-black/15 px-2 py-1 text-sm" onClick={() => signOut()}>{t("signOut", lang)}</button>
            )}
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-2 text-sm">
          {PAGES.map((p) => (
            <NavLink key={p.path} to={{ pathname: p.path, search }} end
                     className={({ isActive }) => `whitespace-nowrap rounded px-2.5 py-1 ${isActive ? "bg-[var(--brand)] text-white" : "hover:bg-stone-100"}`}>
              {t(p.key, lang)}
            </NavLink>
          ))}
        </nav>
      </header>
      {!online && <div className="bg-amber-50 px-4 py-1.5 text-sm text-amber-900">{t("offline", lang)}</div>}
      {error && online && <div className="bg-red-50 px-4 py-2 text-sm text-red-900">{t(error, lang)}</div>}
      <main className="min-h-0 flex-1 overflow-y-auto">
        <Suspense fallback={<div className="p-4"><Loading /></div>}>
          <Routes>
            {PAGES.map((p) => <Route key={p.path} path={p.path} element={p.element ?? <p.Comp />} />)}
            {/* Seed-company dashboard (F14): reachable by link, not part of the farmer menu. */}
            <Route path="/insights" element={<InsightsPage />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}
