import { NavLink, Route, Routes } from "react-router-dom";
import MapPage from "./pages/MapPage.jsx";
import Placeholder from "./pages/Placeholder.jsx";

const PAGES = [
  { path: "/", label: "Map", element: <MapPage /> },
  { path: "/timeline", label: "Timeline", feature: "F2–F4: season timeline, crop and stress" },
  { path: "/why", label: "Why & Twins", feature: "F6–F7: likely reasons and similar fields" },
  { path: "/what-if", label: "What-If", feature: "F8: what-if simulator" },
  { path: "/planner", label: "Planner", feature: "F9: next season planner" },
  { path: "/ask", label: "Ask Your Field", feature: "F10: questions in Telugu, Hindi, English" },
  { path: "/diary", label: "Diary", feature: "F11: voice farm diary and seed packet OCR" },
  { path: "/report", label: "Report", feature: "F12: field health report PDF" },
];

export default function App() {
  return (
    <div className="flex h-full flex-col bg-stone-50 text-stone-900">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-stone-200 bg-white px-4 py-2">
        <span className="text-lg font-semibold text-green-800">Kshetra</span>
        <nav className="flex flex-wrap gap-1 text-sm">
          {PAGES.map((p) => (
            <NavLink
              key={p.path}
              to={p.path}
              end
              className={({ isActive }) =>
                `rounded px-2 py-1 ${isActive ? "bg-green-700 text-white" : "hover:bg-stone-100"}`
              }
            >
              {p.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="min-h-0 flex-1">
        <Routes>
          {PAGES.map((p) => (
            <Route
              key={p.path}
              path={p.path}
              element={p.element ?? <Placeholder title={p.label} feature={p.feature} />}
            />
          ))}
        </Routes>
      </main>
    </div>
  );
}
