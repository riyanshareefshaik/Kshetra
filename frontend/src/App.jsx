import { lazy, Suspense, useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { Download, Ellipsis, LogOut, Mic, Monitor, Moon, Sprout, Sun, WifiOff, X } from "lucide-react";
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

function Brand({ compact = false }) {
  return (
    <span className="flex items-center gap-2 text-[17px] font-bold tracking-tight text-[var(--text-primary)]">
      <span className="k-logo grid h-8 w-8 place-items-center rounded-[10px]"><Sprout size={18} strokeWidth={2.4} /></span>
      <span className={compact ? "hidden sm:inline" : ""}>Kshetra</span>
    </span>
  );
}

const THEMES = [["system", Monitor], ["light", Sun], ["dark", Moon]];

function ThemeButton({ className }) {
  const { theme, setTheme, lang } = useApp();
  const i = Math.max(0, THEMES.findIndex(([k]) => k === theme));
  const [, Icon] = THEMES[i];
  const next = THEMES[(i + 1) % THEMES.length][0];
  const label = `${t("theme", lang)}: ${t(`theme.${theme}`, lang)}`;
  return (
    <button onClick={() => setTheme(next)} title={label} aria-label={label}
            className={`h-9 w-9 place-items-center rounded-xl border ${className}`}><Icon size={17} /></button>
  );
}

function Controls() {
  const { fields, fieldId, selectField, lang, setLang } = useApp();
  const voice = useVoiceNav();
  const install = useInstallPrompt();
  const base = "border-[var(--line)] bg-[var(--surface-1)] text-[var(--text-primary)] shadow-[var(--shadow)] hover:bg-[var(--surface-2)]";
  return (
    <>
      <select aria-label={t("chooseField", lang)} className={`min-w-0 max-w-[11rem] rounded-xl border px-2.5 py-1.5 text-sm ${base}`}
              value={fieldId || ""} onChange={(e) => selectField(e.target.value || null)}>
        <option value="" className="bg-[var(--surface-1)] text-[var(--text-primary)]">{t("chooseField", lang)}</option>
        {fields.map((f) => <option key={f.id} value={f.id} className="bg-[var(--surface-1)] text-[var(--text-primary)]">{f.name || `Field ${f.id.slice(0, 4)}`}</option>)}
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
        <ThemeButton className={`hidden sm:grid ${base}`} />
        <select aria-label="Language" className={`rounded-xl border px-2 py-1.5 text-sm ${base}`} value={lang} onChange={(e) => setLang(e.target.value)}>
          {Object.entries(LANGS).map(([k, v]) => <option key={k} value={k} className="bg-[var(--surface-1)] text-[var(--text-primary)]">{v}</option>)}
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
    <aside className="hidden w-64 shrink-0 flex-col border-r border-[var(--line)] lg:flex">
      <div className="px-5 pb-5 pt-5"><Brand /></div>
      <nav className="flex-1 space-y-4 overflow-y-auto px-3 pb-6">
        {NAV.map((g) => (
          <div key={g.group}>
            <div className="px-3 pb-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--text-muted)]">{t(g.group, lang)}</div>
            {g.items.map((p) => (
              <NavLink key={p.path} to={{ pathname: p.path, search }} end
                       className={({ isActive }) => `group flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition-all ${isActive ? "bg-[var(--surface-1)] font-semibold text-[var(--text-primary)] shadow-[var(--shadow)] ring-1 ring-[var(--line)]" : "text-[var(--text-secondary)] hover:bg-[var(--hover)] hover:text-[var(--text-primary)]"}`}>
                {({ isActive }) => (<>
                  <p.icon size={18} strokeWidth={isActive ? 2.3 : 1.9} className={isActive ? "text-[var(--brand-ink)]" : ""} /> {t(p.key, lang)}
                </>)}
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
    <nav className="k-tabbar fixed inset-x-3 bottom-[calc(0.75rem+env(safe-area-inset-bottom))] z-[1000] grid grid-cols-5 rounded-[1.75rem] p-1.5 lg:hidden">
      {tabs.map((p) => (
        <NavLink key={p.path} to={{ pathname: p.path, search }} end
                 className={({ isActive }) => `flex flex-col items-center gap-0.5 rounded-[1.35rem] py-1.5 text-[10.5px] transition-colors ${isActive ? "bg-[var(--leaf-50)] font-semibold text-[var(--brand-ink)]" : "text-[var(--text-secondary)]"}`}>
          {({ isActive }) => (<>
            <span className="grid h-7 place-items-center"><p.icon size={20} strokeWidth={isActive ? 2.4 : 1.9} /></span>
            <span className="max-w-full truncate px-1">{t(p.key, lang)}</span>
          </>)}
        </NavLink>
      ))}
      <button onClick={onMore} className={`flex flex-col items-center gap-0.5 rounded-[1.35rem] py-1.5 text-[10.5px] ${inMore ? "bg-[var(--leaf-50)] font-semibold text-[var(--brand-ink)]" : "text-[var(--text-secondary)]"}`}>
        <span className="grid h-7 place-items-center"><Ellipsis size={20} strokeWidth={inMore ? 2.4 : 1.9} /></span>
        {t("nav.more", lang)}
      </button>
    </nav>
  );
}

function ThemePicker() {
  const { theme, setTheme, lang } = useApp();
  return (
    <div className="mt-4">
      <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">{t("theme", lang)}</div>
      <div className="k-card grid grid-cols-3 gap-1 p-1" role="radiogroup" aria-label={t("theme", lang)}>
        {THEMES.map(([k, Icon]) => (
          <button key={k} role="radio" aria-checked={theme === k} onClick={() => setTheme(k)}
                  className={`flex items-center justify-center gap-1.5 rounded-xl px-2 py-2 text-xs ${theme === k ? "bg-[var(--brand)] font-semibold text-white" : "text-[var(--text-secondary)]"}`}>
            <Icon size={15} />{t(`theme.${k}`, lang)}
          </button>
        ))}
      </div>
    </div>
  );
}

function MoreSheet({ open, onClose }) {
  const { lang } = useApp();
  const { search } = useLocation();
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[1100] lg:hidden" role="dialog" aria-modal="true">
      <button className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" aria-label="Close" onClick={onClose} />
      <div className="k-rise absolute inset-x-0 bottom-0 max-h-[85vh] overflow-y-auto rounded-t-[2rem] border-t border-[var(--line)] bg-[var(--page)] p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] shadow-[var(--shadow-lg)]">
        <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-[var(--line-strong)]" />
        <div className="mb-2 flex items-center justify-between"><Brand /><button onClick={onClose} aria-label="Close" className="grid h-9 w-9 place-items-center rounded-xl bg-[var(--surface-1)]"><X size={18} /></button></div>
        {NAV.map((g) => (
          <div key={g.group} className="mt-3">
            <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">{t(g.group, lang)}</div>
            <div className="grid grid-cols-3 gap-2">
              {g.items.map((p) => (
                <NavLink key={p.path} to={{ pathname: p.path, search }} end onClick={onClose}
                         className={({ isActive }) => `k-card flex flex-col items-center gap-1 px-1 py-3 text-center text-xs ${isActive ? "ring-2 ring-[var(--leaf)]" : ""}`}>
                  <span className="grid h-9 w-9 place-items-center rounded-xl bg-[var(--leaf-50)] text-[var(--brand-ink)]"><p.icon size={19} /></span>
                  {t(p.key, lang)}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
        <ThemePicker />
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
        <header className="k-topbar sticky top-0 z-[900]">
          <div className="mx-auto flex max-w-6xl items-center gap-2 px-4 py-2.5 sm:px-6">
            <span className="lg:hidden"><Brand compact /></span>
            <div className="flex min-w-0 flex-1 items-center gap-2"><Controls /></div>
          </div>
        </header>
        {!online && <div className="mx-4 mt-3 flex items-center gap-2 rounded-xl bg-[var(--gold-50)] px-4 py-2 text-sm text-[var(--gold-ink)]"><WifiOff size={15} />{t("offline", lang)}</div>}
        {error && online && <div className="mx-4 mt-3 rounded-xl bg-[var(--red-50)] px-4 py-2 text-sm text-[var(--red-ink)]">{t(error, lang)}</div>}
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
