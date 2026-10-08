import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, saveBlob } from "../api.js";
import { Card, ErrorBox, LevelIcon, NeedField, Page } from "../components/ui.jsx";
import { cropName, fmtDate, t } from "../i18n.js";
import { useApp } from "../state.jsx";

export default function ReportPage() {
  return <NeedField><Report /></NeedField>;
}

function Report() {
  const { fieldId, field, lang, user, setUser } = useApp();
  const [claims, setClaims] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const slug = (field?.name || "field").replace(/\W+/g, "-").toLowerCase();

  useEffect(() => {
    api.claims(fieldId).then(setClaims).catch(setError);
  }, [fieldId]);

  async function download(fetcher, name) {
    setBusy(true);
    setError(null);
    try {
      saveBlob(await fetcher(), name);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function toggle(on) {
    try {
      setUser({ ...user, ...(await api.setConsent(on)) });
    } catch (e) {
      setError(e);
    }
  }

  return (
    <Page title={t("rep.title", lang)}>
      <ErrorBox error={error} />
      <Card title={t("rep.field", lang)}>
        <p className="text-sm text-[var(--text-secondary)]">{t("rep.desc", lang)}</p>
        <button disabled={busy} onClick={() => download(() => api.report(fieldId), `kshetra-${slug}-report.pdf`)}
                className="mt-3 rounded bg-[var(--brand)] px-4 py-2 text-white disabled:opacity-50">
          {busy ? t("loading", lang) : t("rep.download", lang)}
        </button>
      </Card>

      <Card title={t("rep.claims", lang)}>
        <p className="text-sm text-[var(--text-secondary)]">{t("rep.claimsDesc", lang, { h: claims?.helpline || "14447" })}</p>
        {claims && (claims.claims.length === 0 ? (
          <p className="mt-2 text-sm">{t("rep.noClaims", lang)}</p>
        ) : (
          <ul className="mt-3 divide-y divide-black/5">
            {claims.claims.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm">
                <LevelIcon level={c.open ? "critical" : "info"} />
                <span className="font-medium">{t(`claim.${c.kind}`, lang)}</span>
                <span className="tabular text-[var(--text-secondary)]">{fmtDate(c.start_date, lang)}</span>
                {c.crop && <span>{cropName(c.crop, lang)}</span>}
                <span className={c.open ? "text-[var(--status-critical)]" : "text-[var(--text-muted)]"}>
                  {c.open ? t("rep.hoursLeft", lang, { n: c.hours_left }) : t("rep.passed", lang)}
                </span>
                <button disabled={busy} className="ml-auto rounded border border-black/15 px-2 py-1"
                        onClick={() => download(() => api.claimPdf(fieldId, c.id), `pmfby-evidence-${c.start_date}.pdf`)}>
                  {t("rep.evidence", lang)}
                </button>
              </li>
            ))}
          </ul>
        ))}
        {claims && (
          <details className="mt-3 text-sm">
            <summary className="cursor-pointer text-[var(--text-secondary)]">{t("rep.documents", lang)}</summary>
            <ul className="mt-1 list-disc pl-5" lang="en">{claims.documents.map((d) => <li key={d}>{d}</li>)}</ul>
          </details>
        )}
      </Card>

      <Card title={t("rep.sharing", lang)}>
        {user ? (
          <label className="flex items-start gap-3 text-sm">
            <input type="checkbox" className="mt-1 h-4 w-4 accent-[var(--brand)]" checked={user.data_sharing_consent}
                   onChange={(e) => toggle(e.target.checked)} />
            <span>
              <b>{t("rep.share", lang)}</b>
              <span className="block text-[var(--text-secondary)]">{t("rep.shareDesc", lang)}</span>
              {user.consent_updated_at && <span className="block text-xs text-[var(--text-muted)]">{fmtDate(user.consent_updated_at, lang)}</span>}
            </span>
          </label>
        ) : <p className="text-sm">{t("loading", lang)}</p>}
      </Card>
      <p className="text-xs text-[var(--text-muted)]">{t("rep.seedLink", lang)} <Link className="underline" to="/insights">{t("rep.seeWhat", lang)}</Link>.</p>
    </Page>
  );
}
