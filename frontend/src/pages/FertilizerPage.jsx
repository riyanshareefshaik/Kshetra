import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Card, ErrorBox, Loading, NeedField, Page, rs } from "../components/ui.jsx";
import { fertNote } from "../components/words.js";
import { cropName, fmtDate, t } from "../i18n.js";
import { useApp } from "../state.jsx";

const NUM_FIELDS = [["n_kg_ha", "fz.n"], ["p_kg_ha", "fz.p"], ["k_kg_ha", "fz.k"], ["ph", "fz.ph"], ["zn_ppm", "fz.zn"]];

export default function FertilizerPage() {
  return <NeedField><Fertilizer /></NeedField>;
}

function Fertilizer() {
  const { fieldId, lang } = useApp();
  const [varieties, setVarieties] = useState([]);
  const [choice, setChoice] = useState("paddy|kharif");
  const [tests, setTests] = useState(null);
  const [form, setForm] = useState({});
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [crop, season] = choice.split("|");
  const options = [...new Map(varieties.map((v) => [`${v.crop}|${v.season}`, v])).values()];

  const loadTests = () => api.soilTests(fieldId).then(setTests).catch(setError);
  useEffect(() => { api.varieties().then(setVarieties).catch(setError); }, []);
  useEffect(() => { loadTests(); }, [fieldId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    setResult(null);
    api.fertilizer(fieldId, crop, season).then((r) => { setResult(r); setError(null); }).catch(setError);
  }, [fieldId, crop, season, tests]);

  async function saveTest(e) {
    e.preventDefault();
    const body = Object.fromEntries(Object.entries(form).filter(([, v]) => v !== "" && v != null).map(([k, v]) => [k, Number(v)]));
    if (!Object.keys(body).length) return;
    setBusy(true);
    try { await api.addSoilTest(fieldId, body); setForm({}); await loadTests(); } catch (err) { setError(err); } finally { setBusy(false); }
  }

  async function onCard(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    try { await api.readSoilCard(fieldId, file); await loadTests(); } catch (err) { setError(err); } finally { setBusy(false); e.target.value = ""; }
  }

  const latest = tests?.[0];
  return (
    <Page title={t("fz.title", lang)}>
      <ErrorBox error={error} />
      <Card title={t("fz.soil", lang)}>
        <p className="mb-2 text-sm text-[var(--text-secondary)]">{latest ? t("fz.latest", lang, { date: fmtDate(latest.test_date, lang) }) : t("fz.noSoil", lang)}</p>
        <label className="inline-block cursor-pointer rounded border border-black/15 px-3 py-1.5 text-sm">📷 {t("fz.card", lang)}
          <input type="file" accept="image/*" capture="environment" className="hidden" onChange={onCard} />
        </label>
        <form onSubmit={saveTest} className="mt-3 text-sm">
          <div className="mb-1 text-xs text-[var(--text-muted)]">{t("fz.orType", lang)}</div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            {NUM_FIELDS.map(([k, label]) => (
              <label key={k} className="text-xs">{t(label, lang)}
                <input type="number" step="any" min="0" className="mt-1 w-full rounded border border-black/15 px-2 py-1 text-sm"
                       value={form[k] ?? ""} placeholder={latest?.[k] ?? ""} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
              </label>
            ))}
          </div>
          <button disabled={busy} className="mt-2 rounded bg-[var(--brand)] px-3 py-1.5 text-white disabled:opacity-50">{t("fz.saveTest", lang)}</button>
        </form>
      </Card>

      <Card title={t("fz.forCrop", lang)} actions={
        <select className="rounded border border-black/15 px-2 py-1 text-sm" value={choice} onChange={(e) => setChoice(e.target.value)}>
          {options.map((v) => <option key={`${v.crop}|${v.season}`} value={`${v.crop}|${v.season}`}>{cropName(v.crop, lang)} · {t(v.season, lang)}</option>)}
        </select>
      }>
        {!result ? <Loading /> : (
          <div className="space-y-3 text-sm">
            <p>{t("fz.dose", lang, { n: result.dose.n_kg_ha, p: result.dose.p2o5_kg_ha, k: result.dose.k2o_kg_ha })}</p>
            {result.ratings.n && <p className="text-[var(--text-secondary)]">{t("fz.ratings", lang, { n: t(result.ratings.n, lang), p: t(result.ratings.p || "medium", lang), k: t(result.ratings.k || "medium", lang) })}</p>}
            <table className="w-full">
              <thead className="text-left text-xs text-[var(--text-secondary)]"><tr><th className="py-1">{t("fz.product", lang)}</th><th>kg/ha</th><th>{t("fz.bags", lang)}</th><th className="text-right">{t("fz.cost", lang)}</th></tr></thead>
              <tbody className="tabular">
                {result.products.map((p) => (
                  <tr key={p.product} className="border-t border-black/5">
                    <td className="py-1.5 font-medium">{p.product}</td><td>{p.kg_per_ha}</td>
                    <td>{p.bags} × {p.bag_kg} kg <span className="text-xs text-[var(--text-muted)]">({p.kg_for_field} kg)</span></td>
                    <td className="text-right">{rs(p.cost_rs)}</td>
                  </tr>
                ))}
                <tr className="border-t border-black/10 font-semibold"><td className="py-1.5">{t("fz.total", lang)}</td><td /><td /><td className="text-right">{rs(result.total_cost_rs)}</td></tr>
              </tbody>
            </table>
            <div><div className="text-xs font-medium text-[var(--text-secondary)]">{t("fz.when", lang)}</div><p>{t(`sched.${result.crop}`, lang)}</p></div>
            {result.notes.length > 0 && <ul className="list-disc space-y-1 pl-5">{result.notes.map((n) => <li key={n.code}>{fertNote(n, lang)}</li>)}</ul>}
            <p className="text-xs text-[var(--text-muted)]">{t("fz.disclaimer", lang)} {result.products.map((p) => `${p.product}: ${p.price_note}`).join(" · ")}</p>
          </div>
        )}
      </Card>
    </Page>
  );
}
