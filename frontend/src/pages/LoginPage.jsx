import { useState } from "react";
import { sendMagicLink } from "../auth.js";
import { LANGS, t } from "../i18n.js";
import { useApp } from "../state.jsx";
import { ErrorBox } from "../components/ui.jsx";
import { FieldScene } from "../components/art.jsx";
import { Mail, MailCheck, Sprout } from "lucide-react";

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
    <div className="mx-auto flex min-h-full max-w-sm flex-col justify-center px-4 py-10">
      <div className="k-card k-rise overflow-hidden">
        <div className="k-hero relative px-5 pb-2 pt-5 text-white">
          <div className="flex items-center justify-between">
            <span className="font-display flex items-center gap-2 text-2xl font-bold"><Sprout size={26} className="text-[var(--gold)]" />Kshetra</span>
            <select aria-label="Language" className="rounded-lg border border-white/30 bg-white/15 px-2 py-1 text-sm text-white" value={lang}
                    onChange={(e) => setLang(e.target.value)}>
              {Object.entries(LANGS).map(([k, v]) => <option key={k} value={k} className="text-black">{v}</option>)}
            </select>
          </div>
          <p className="mt-1 text-sm text-white/85">{t("start.sub", lang)}</p>
          <FieldScene className="mt-2 h-24 w-full" />
        </div>
        <div className="space-y-4 p-5">
          <h1 className="text-xl font-bold">{t("login.title", lang)}</h1>
          {sent ? (
            <p className="flex items-center gap-2 rounded-xl bg-[var(--leaf-50)] p-3 text-[var(--brand)]"><MailCheck size={20} />{t("login.check", lang)}</p>
          ) : (
            <form onSubmit={submit} className="space-y-3">
              <label className="block text-sm">{t("login.email", lang)}
                <input type="email" required autoComplete="email" className="mt-1 w-full rounded-xl border border-black/15 bg-white px-3 py-2.5"
                       value={email} onChange={(e) => setEmail(e.target.value)} />
              </label>
              <button disabled={busy} className="flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--brand)] px-4 py-2.5 font-semibold text-white shadow-sm disabled:opacity-50">
                <Mail size={18} />{t("login.send", lang)}
              </button>
            </form>
          )}
          <ErrorBox error={error} />
        </div>
      </div>
    </div>
  );
}
