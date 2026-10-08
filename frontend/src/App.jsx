import { lazy, Suspense } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { LANGS, t } from "./i18n.js";
import { useApp } from "./state.jsx";
import MapPage from "./pages/MapPage.jsx";
import { Loading } from "./components/ui.jsx";

const TimelinePage = lazy(() => import("./pages/TimelinePage.jsx"));
const WhyPage = lazy(() => import("./pages/WhyPage.jsx"));
const WhatIfPage = lazy(() => import("./pages/WhatIfPage.jsx"));
const PlannerPage = lazy(() => import("./pages/PlannerPage.jsx"));
const AskPage = lazy(() => import("./pages/AskPage.jsx"));
const DiaryPage = lazy(() => import("./pages/DiaryPage.jsx"));
const ReportPage = lazy(() => import("./pages/ReportPage.jsx"));
const InsightsPage = lazy(() => import("./pages/InsightsPage.jsx"));

const PAGES = [
  { path: "/", key: "map", element: <MapPage /> },
  { path: "/timeline", key: "timeline", element: <TimelinePage /> },
  { path: "/why", key: "why", element: <WhyPage /> },
  { path: "/what-if", key: "whatIf", element: <WhatIfPage /> },
  { path: "/planner", key: "planner", element: <PlannerPage /> },
  { path: "/ask", key: "ask", element: <AskPage /> },
  { path: "/diary", key: "diary", element: <DiaryPage /> },
  { path: "/report", key: "report", element: <ReportPage /> },
];
// Seed-company dashboard (F14): reachable by link, not part of the farmer menu.
const ROUTES = [...PAGES, { path: "/insights", key: "insights", element: <InsightsPage /> }];

export default function App() {
  const { fields, fieldId, selectField, lang, setLang, error } = useApp();
  const { search } = useLocation();
  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-black/10 bg-white">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2">
          <span className="text-lg font-semibold text-[var(--brand)]">Kshetra</span>
          <select aria-label={t("chooseField", lang)} className="max-w-[16rem] rounded border border-black/15 px-2 py-1 text-sm"
                  value={fieldId || ""} onChange={(e) => selectField(e.target.value || null)}>
            <option value="">{t("chooseField", lang)}</option>
            {fields.map((f) => (
              <option key={f.id} value={f.id}>{f.name || `Field ${f.id.slice(0, 4)}`}</option>
            ))}
          </select>
          <select aria-label="Language" className="ml-auto rounded border border-black/15 px-2 py-1 text-sm"
                  value={lang} onChange={(e) => setLang(e.target.value)}>
            {Object.entries(LANGS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
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
      {error && <div className="bg-red-50 px-4 py-2 text-sm text-red-900">{error}</div>}
      <main className="min-h-0 flex-1 overflow-y-auto">
        <Suspense fallback={<div className="p-4"><Loading /></div>}>
          <Routes>
            {ROUTES.map((p) => <Route key={p.path} path={p.path} element={p.element} />)}
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}
