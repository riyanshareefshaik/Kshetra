import { lazy, Suspense, useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { Download, Ellipsis, LogOut, Mic, Sprout, WifiOff, X } from "lucide-react";
import { authEnabled, signOut } from "./auth.js";
import { LANGS, t } from "./i18n.js";
import { ALL_PAGES, NAV, TABS } from "./nav.js";
import { useApp } from "./state.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import { Loading } from "./components/ui.jsx";
import { browserRecognition, listenOnce, speak } from "./components/speech.js";

const PAGE_COMPONENTS = {
  "/": lazy(() => import("./pages/TodayPage.jsx")),
  "/map": lazy(() => import("./pages/MapPage.jsx")),
  "/timeline": lazy(() => import("./pages/TimelinePage.jsx")),
  "/why": lazy(() => import("./pages/WhyPage.jsx")),
  "/what-if": lazy(() => import("./pages/WhatIfPage.jsx")),
  "/planner": lazy(() => import("./pages/PlannerPage.jsx")),
  "/fertilizer": lazy(() => import("./pages/FertilizerPage.jsx")),
  "/market": lazy(() => import("./pages/MarketPage.jsx")),
  "/schemes": lazy(() => import("./pages/SchemesPage.jsx")),
  "/report": lazy(() => import("./pages/ReportPage.jsx")),
  "/ask": lazy(() => import("./pages/AskPage.jsx")),
  "/diary": lazy(() => import("./pages/DiaryPage.jsx")),
  "/group": lazy(() => import("./pages/GroupPage.jsx")),
};
const InsightsPage = lazy(() => import("./pages/InsightsPage.jsx"));

function useVoiceNav() {
  const { lang } = useApp();
  const navigate = useNavigate();
  const { search } = useLocation();
  const [busy, setBusy] = useState(false);
  async function go() {
    setBusy(true);
    try {
      const heard = (await listenOnce(lang)).toLowerCase();
      // Words like "plan" also appear inside "planner": prefer the longest match.
      const hit = ALL_PAGES.map((p) => ({ p, w: p.words.filter((w) => heard.includes(w)).sort((a, b) => b.length - a.length)[0] }))
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
  return { available: Boolean(browserRecognition()), busy, go };
}

function useInstallPrompt() {
  const [prompt, setPrompt] = useState(null);
  useEffect(() => {
    const onPrompt = (e) => { e.preventDefault(); setPrompt(e); };
    window.addEventListener("beforeinstallprompt", onPrompt);
    return () => window.removeEventListener("beforeinstallprompt", onPrompt);
  }, []);
  return prompt && (async () => { prompt.prompt(); await prompt.userChoice; setPrompt(null); });
}

function Brand({ light = false }) {
  return (
    <span className={`font-display flex items-center gap-1.5 text-xl font-bold ${light ? "text-white" : "text-[var(--brand)]"}`}>
      <span className={`grid h-8 w-8 place-items-center rounded-xl ${light ? "bg-white/15" : "bg-[var(--leaf-50)]"}`}>
        <Sprout size={20} strokeWidth={2.2} />
      </span>
      Kshetra
    </span>
  );
}

function Controls({ light }) {
  const { fields, fieldId, selectField, lang, setLang } = useApp();
  const voice = useVoiceNav();
  const install = useInstallPrompt();
  const base = light ? "border-white/25 bg-white/10 text-white" : "border-black/10 bg-white";
  return (
    <>
      <select aria-label={t("chooseField", lang)} className={`min-w-0 max-w-[11rem] rounded-xl border px-2.5 py-1.5 text-sm ${base}`}
              value={fieldId || ""} onChange={(e) => selectField(e.target.value || null)}>
        <option value="" className="text-black">{t("chooseField", lang)}</option>
        {fields.map((f) => <option key={f.id} value={f.id} className="text-black">{f.name || `Field ${f.id.slice(0, 4)}`}</option>)}
      </select>
      <div className="ml-auto flex items-center gap-1.5">
        {install && (
          <button onClick={install} className={`hidden items-center gap-1 rounded-xl border px-2.5 py-1.5 text-sm sm:flex ${base}`}>
            <Download size={16} /> {t("install", lang)}
          </button>
        )}
        {voice.available && (
          <button onClick={voice.go} title={t("voice.help", lang)} aria-label={t("voice.help", lang)}
                  className={`grid h-9 w-9 place-items-center rounded-xl border ${voice.busy ? "animate-pulse border-[var(--gold)] bg-[var(--gold)] text-white" : base}`}>
            <Mic size={18} />
          </button>
        )}
        <select aria-label="Language" className={`rounded-xl border px-2 py-1.5 text-sm ${base}`} value={lang} onChange={(e) => setLang(e.target.value)}>
          {Object.entries(LANGS).map(([k, v]) => <option key={k} value={k} className="text-black">{v}</option>)}
        </select>
        {authEnabled && (
          <button onClick={() => signOut()} title={t("signOut", lang)} aria-label={t("signOut", lang)}
                  className={`grid h-9 w-9 place-items-center rounded-xl border ${base}`}><LogOut size={17} /></button>
        )}
      </div>
    </>
  );
}

function Sidebar() {
  const { lang } = useApp();
  const { search } = useLocation();
  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-black/5 bg-white/80 backdrop-blur lg:flex">
      <div className="px-5 py-4"><Brand /></div>
      <nav className="flex-1 space-y-4 overflow-y-auto px-3 pb-6">
        {NAV.map((g) => (
          <div key={g.group}>
            <div className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">{t(g.group, lang)}</div>
            {g.items.map((p) => (
              <NavLink key={p.path} to={{ pathname: p.path, search }} end
                       className={({ isActive }) => `flex items-center gap-2.5 rounded-xl px-2.5 py-2 text-sm transition-colors ${isActive ? "bg-[var(--leaf-50)] font-semibold text-[var(--brand)]" : "text-[var(--text-secondary)] hover:bg-black/[0.03]"}`}>
                <p.icon size={18} strokeWidth={2} /> {t(p.key, lang)}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  );
}

function TabBar({ onMore }) {
  const { lang } = useApp();
  const { search, pathname } = useLocation();
  const tabs = TABS.map((p) => ALL_PAGES.find((x) => x.path === p));
  const inMore = !TABS.includes(pathname);
  return (
    <nav className="fixed inset-x-0 bottom-0 z-[1000] grid grid-cols-5 border-t border-black/10 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden">
      {tabs.map((p) => (
        <NavLink key={p.path} to={{ pathname: p.path, search }} end
                 className={({ isActive }) => `flex flex-col items-center gap-0.5 py-2 text-[11px] ${isActive ? "font-semibold text-[var(--brand)]" : "text-[var(--text-secondary)]"}`}>
          {({ isActive }) => (<>
            <span className={`grid h-7 w-12 place-items-center rounded-full transition-colors ${isActive ? "bg-[var(--leaf-100)]" : ""}`}><p.icon size={19} /></span>
            <span className="max-w-full truncate px-1">{t(p.key, lang)}</span>
          </>)}
        </NavLink>
      ))}
      <button onClick={onMore} className={`flex flex-col items-center gap-0.5 py-2 text-[11px] ${inMore ? "font-semibold text-[var(--brand)]" : "text-[var(--text-secondary)]"}`}>
        <span className={`grid h-7 w-12 place-items-center rounded-full ${inMore ? "bg-[var(--leaf-100)]" : ""}`}><Ellipsis size={19} /></span>
        {t("nav.more", lang)}
      </button>
    </nav>
  );
}

function MoreSheet({ open, onClose }) {
  const { lang } = useApp();
  const { search } = useLocation();
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[1100] lg:hidden" role="dialog" aria-modal="true">
      <button className="absolute inset-0 bg-black/30" aria-label="Close" onClick={onClose} />
      <div className="k-rise absolute inset-x-0 bottom-0 max-h-[80vh] overflow-y-auto rounded-t-3xl bg-[var(--page)] p-4 pb-[calc(1rem+env(safe-area-inset-bottom))]">
        <div className="mb-2 flex items-center justify-between"><Brand /><button onClick={onClose} aria-label="Close" className="grid h-9 w-9 place-items-center rounded-xl bg-white"><X size={18} /></button></div>
        {NAV.map((g) => (
          <div key={g.group} className="mt-3">
            <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">{t(g.group, lang)}</div>
            <div className="grid grid-cols-3 gap-2">
              {g.items.map((p) => (
                <NavLink key={p.path} to={{ pathname: p.path, search }} end onClick={onClose}
                         className={({ isActive }) => `k-card flex flex-col items-center gap-1 px-1 py-3 text-center text-xs ${isActive ? "ring-2 ring-[var(--leaf)]" : ""}`}>
                  <span className="grid h-9 w-9 place-items-center rounded-xl bg-[var(--leaf-50)] text-[var(--brand)]"><p.icon size={19} /></span>
                  {t(p.key, lang)}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function App() {
  const { lang, error, online, session, signedIn } = useApp();
  const [more, setMore] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => setMore(false), [pathname]);
  if (authEnabled && session === undefined) return <div className="p-6"><Loading /></div>;
  if (!signedIn) return <LoginPage />;
  return (
    <div className="flex h-full">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="k-header text-white lg:bg-none lg:text-inherit">
          <div className="flex items-center gap-2 px-4 py-2.5 lg:border-b lg:border-black/5 lg:bg-white/70 lg:backdrop-blur">
            <span className="lg:hidden"><Brand light /></span>
            <div className="hidden min-w-0 flex-1 items-center gap-2 lg:flex"><Controls /></div>
            <div className="flex min-w-0 flex-1 items-center gap-2 lg:hidden"><Controls light /></div>
          </div>
        </header>
        {!online && <div className="flex items-center gap-2 bg-amber-50 px-4 py-1.5 text-sm text-amber-900"><WifiOff size={15} />{t("offline", lang)}</div>}
        {error && online && <div className="bg-red-50 px-4 py-2 text-sm text-red-900">{t(error, lang)}</div>}
        <main className="k-safe-bottom min-h-0 flex-1 overflow-y-auto">
          <Suspense fallback={<div className="p-4"><Loading /></div>}>
            <Routes>
              {Object.entries(PAGE_COMPONENTS).map(([path, Comp]) => <Route key={path} path={path} element={<Comp />} />)}
              <Route path="/today" element={(() => { const C = PAGE_COMPONENTS["/"]; return <C />; })()} />
              {/* Seed-company dashboard (F14): reachable by link, not part of the farmer menu. */}
              <Route path="/insights" element={<InsightsPage />} />
            </Routes>
          </Suspense>
        </main>
      </div>
      <TabBar onMore={() => setMore(true)} />
      <MoreSheet open={more} onClose={() => setMore(false)} />
    </div>
  );
}
