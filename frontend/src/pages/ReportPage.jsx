import { useState } from "react";
import { api } from "../api.js";
import { Card, ErrorBox, NeedField, Page } from "../components/ui.jsx";
import { t } from "../i18n.js";
import { useApp } from "../state.jsx";

export default function ReportPage() {
  return <NeedField><Report /></NeedField>;
}

function Report() {
  const { fieldId, field, lang, user, setUser } = useApp();
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function download() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(api.reportUrl(fieldId));
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `kshetra-${(field?.name || "field").replace(/\W+/g, "-").toLowerCase()}-report.pdf`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function toggle(on) {
    try {
      setUser(await api.setConsent(user.id, on));
    } catch (e) {
      setError(e);
    }
  }

  return (
    <Page title={t("report", lang)}>
      <ErrorBox error={error} />
      <Card title="Field Health Report">
        <p className="text-sm text-[var(--text-secondary)]">One PDF with the field's area and soil, crop greenness from space, every detected season with yield ranges, stress events with dates and evidence (useful for PMFBY claims), likely reasons, and the data sources. It carries a SHA-256 fingerprint so a bank can check it was not edited.</p>
        <button disabled={busy} onClick={download} className="mt-3 rounded bg-[var(--brand)] px-4 py-2 text-white disabled:opacity-50">
          {busy ? t("loading", lang) : t("download", lang)}
        </button>
        {field?.is_synthetic && <p className="mt-2 text-sm text-[var(--status-critical)]">This field uses synthetic test data; the PDF says so on page 1.</p>}
      </Card>
      <Card title="Data sharing">
        {user ? (
          <label className="flex items-start gap-3 text-sm">
            <input type="checkbox" className="mt-1 h-4 w-4 accent-[var(--brand)]" checked={user.data_sharing_consent}
                   onChange={(e) => toggle(e.target.checked)} />
            <span>
              <b>{t("sharing", lang)}</b>
              <span className="block text-[var(--text-secondary)]">Off by default. When on, your seasons count towards district-level averages that seed companies can see: never your name, phone, field location or boundary, and only in groups of at least 5 fields. Turn it off any time.</span>
              {user.consent_updated_at && <span className="block text-xs text-[var(--text-muted)]">Last changed {new Date(user.consent_updated_at).toLocaleString("en-IN")}</span>}
            </span>
          </label>
        ) : <p className="text-sm">Loading your settings…</p>}
      </Card>
    </Page>
  );
}
