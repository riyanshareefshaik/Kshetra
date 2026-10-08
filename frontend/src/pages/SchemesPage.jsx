import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Card, ErrorBox, ListenButton, Loading, Page } from "../components/ui.jsx";
import { t } from "../i18n.js";
import { useApp } from "../state.jsx";

export default function SchemesPage() {
  const { lang } = useApp();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { api.schemes().then(setData).catch(setError); }, []);

  return (
    <Page title={t("sc.title", lang)}>
      <ErrorBox error={error} />
      <p className="text-sm text-[var(--text-secondary)]">{t("sc.note", lang)}</p>
      {!data ? (!error && <Loading />) : data.schemes.map((s) => (
        <Card key={s.id} title={s.name} actions={<span className="rounded bg-[var(--page)] px-2 py-0.5 text-xs">{t(s.level === "state" ? "sc.state" : "sc.central", lang)}</span>}>
          <dl className="space-y-1.5 text-sm" lang="en">
            <div><dt className="inline font-medium">{t("sc.why", lang)}: </dt><dd className="inline">{s.why}</dd></div>
            <div><dt className="inline font-medium">{t("sc.benefit", lang)}: </dt><dd className="inline">{s.benefit}</dd></div>
            <div><dt className="inline font-medium">{t("sc.who", lang)}: </dt><dd className="inline">{s.who}</dd></div>
            <div><dt className="inline font-medium">{t("sc.how", lang)}: </dt><dd className="inline">{s.how}</dd></div>
          </dl>
          <div className="mt-2 flex items-center gap-3 text-sm">
            <a className="text-[var(--series-1)] underline" href={s.link} target="_blank" rel="noreferrer">{t("sc.open", lang)} ↗</a>
            <ListenButton text={`${s.name}. ${s.benefit}`} />
          </div>
        </Card>
      ))}
    </Page>
  );
}
