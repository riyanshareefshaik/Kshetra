import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "./api.js";

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
  const [error, setError] = useState(null);
  const fieldId = params.get("field") || stored("kshetra.field", null);

  const reloadFields = useCallback(async () => {
    try {
      setFields(await api.fields());
      setError(null);
    } catch (e) {
      setError("Can't connect to Kshetra right now. Check your internet connection and try again.");
    }
  }, []);

  useEffect(() => {
    reloadFields();
    api.demoUser().then(setUser).catch(() => {});
  }, [reloadFields]);

  const selectField = useCallback(
    (id) => {
      store("kshetra.field", id);
      const next = new URLSearchParams(params);
      if (id) next.set("field", id);
      else next.delete("field");
      setParams(next, { replace: true });
    },
    [params, setParams]
  );

  const setLang = useCallback((l) => {
    store("kshetra.lang", l);
    setLangState(l);
  }, []);

  const field = fields.find((f) => f.id === fieldId) || null;
  const value = useMemo(
    () => ({ fields, field, fieldId: field ? fieldId : null, selectField, reloadFields, lang, setLang, user, setUser, error }),
    [fields, field, fieldId, selectField, reloadFields, lang, setLang, user, error]
  );
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  return useContext(AppContext);
}
