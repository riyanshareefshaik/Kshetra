import { useState } from "react";
import { sendMagicLink } from "../auth.js";
import { LANGS, t } from "../i18n.js";
import { useApp } from "../state.jsx";
import { ErrorBox } from "../components/ui.jsx";

export default function LoginPage() {
  const { lang, setLang } = useApp();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await sendMagicLink(email.trim());
      setSent(true);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-full max-w-sm flex-col justify-center gap-4 px-4 py-10">
      <div className="flex items-center justify-between">
        <span className="text-2xl font-semibold text-[var(--brand)]">Kshetra</span>
        <select aria-label="Language" className="rounded border border-black/15 px-2 py-1 text-sm" value={lang}
                onChange={(e) => setLang(e.target.value)}>
          {Object.entries(LANGS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>
      <h1 className="text-lg font-semibold">{t("login.title", lang)}</h1>
      {sent ? <p className="rounded bg-green-50 p-3 text-green-900">{t("login.check", lang)}</p> : (
        <form onSubmit={submit} className="space-y-3">
          <label className="block text-sm">{t("login.email", lang)}
            <input type="email" required autoComplete="email" className="mt-1 w-full rounded border border-black/15 px-3 py-2"
                   value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <button disabled={busy} className="w-full rounded bg-[var(--brand)] px-4 py-2 text-white disabled:opacity-50">{t("login.send", lang)}</button>
        </form>
      )}
      <ErrorBox error={error} />
    </div>
  );
}
