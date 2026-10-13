import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "./api.js";
import { authEnabled, supabase } from "./auth.js";
import { setChartTheme } from "./components/tokens.jsx";

const darkQuery = typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

// "system" follows the phone or computer setting; "light" / "dark" are the farmer's own choice.
function useTheme() {
  const [theme, setThemeState] = useState(() => stored("kshetra.theme", "system"));
  const [systemDark, setSystemDark] = useState(() => Boolean(darkQuery?.matches));
  useEffect(() => {
    if (!darkQuery) return undefined;
    const on = (e) => setSystemDark(e.matches);
    darkQuery.addEventListener("change", on);
    return () => darkQuery.removeEventListener("change", on);
  }, []);
  const resolved = theme === "system" ? (systemDark ? "dark" : "light") : theme;
  setChartTheme(resolved);   // before children render, so charts pick up the right colours
  useEffect(() => {
    document.documentElement.dataset.theme = resolved;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", resolved === "dark" ? "#0b0b0c" : "#f5f6f3");
  }, [resolved]);
  const setTheme = useCallback((v) => { store("kshetra.theme", v); setThemeState(v); }, []);
  return { theme, resolvedTheme: resolved, setTheme };
}

const AppContext = createContext(null);

function stored(key, fallback) {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function store(key, value) {
  try {
    if (value == null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* private mode: preferences just don't persist */
  }
}

export function AppProvider({ children }) {
  const [params, setParams] = useSearchParams();
  const [fields, setFields] = useState([]);
  const [lang, setLangState] = useState(() => stored("kshetra.lang", "te"));
  const [user, setUser] = useState(null);
  const [session, setSession] = useState(authEnabled ? undefined : null);   // undefined = still checking
  const [error, setError] = useState(null);
  const [online, setOnline] = useState(() => navigator.onLine);
  const { theme, resolvedTheme, setTheme } = useTheme();
  const fieldId = params.get("field") || stored("kshetra.field", null);
  const signedIn = !authEnabled || Boolean(session);

  useEffect(() => {
    if (!supabase) return undefined;
    supabase.auth.getSession().then(({ data }) => setSession(data.session ?? null));
    const { data } = supabase.auth.onAuthStateChange((_e, s) => setSession(s ?? null));
    return () => data.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => { window.removeEventListener("online", on); window.removeEventListener("offline", off); };
  }, []);

  const reloadFields = useCallback(async () => {
    try {
      setFields(await api.fields());
      setError(null);
    } catch (e) {
      setError(e.status === 401 ? null : "connectError");
    }
  }, []);

  useEffect(() => {
    if (!signedIn) return;
    reloadFields();
    api.me().then((u) => {
      setUser(u);
      if (u?.preferred_language && !stored("kshetra.lang", null)) setLangState(u.preferred_language);
    }).catch(() => {});
  }, [signedIn, reloadFields]);

  const selectField = useCallback((id) => {
    store("kshetra.field", id);
    const next = new URLSearchParams(params);
    if (id) next.set("field", id);
    else next.delete("field");
    setParams(next, { replace: true });
  }, [params, setParams]);

  useEffect(() => { document.documentElement.lang = lang; }, [lang]);

  const setLang = useCallback((l) => {
    store("kshetra.lang", l);
    setLangState(l);
    api.updateMe({ preferred_language: l }).catch(() => {});
  }, []);

  const field = fields.find((f) => f.id === fieldId) || null;
  const value = useMemo(() => ({
    fields, field, fieldId: field ? fieldId : null, selectField, reloadFields, lang, setLang, user, setUser,
    error, online, session, signedIn, theme, resolvedTheme, setTheme,
  }), [fields, field, fieldId, selectField, reloadFields, lang, setLang, user, error, online, session, signedIn,
       theme, resolvedTheme, setTheme]);
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  return useContext(AppContext);
}

