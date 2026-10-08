import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api.js";
import { C, axisProps } from "../components/tokens.jsx";
import { Card, ErrorBox, Loading, NeedField, Page } from "../components/ui.jsx";
import { marketAdvice } from "../components/words.js";
import { cropName, fmtDate, t } from "../i18n.js";
import { useApp } from "../state.jsx";

const CROPS = ["paddy", "maize", "cotton", "pulses", "chilli", "sugarcane"];

export default function MarketPage() {
  return <NeedField><Market /></NeedField>;
}

function Market() {
  const { fieldId, lang } = useApp();
  const [crop, setCrop] = useState("paddy");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setData(null);
    api.market(fieldId, crop).then((d) => { setData(d); setError(null); }).catch(setError);
  }, [fieldId, crop]);

  return (
    <Page title={t("mk.title", lang)} wide>
      <select className="rounded border border-black/15 px-2 py-1 text-sm" value={crop} onChange={(e) => setCrop(e.target.value)}>
        {CROPS.map((c) => <option key={c} value={c}>{cropName(c, lang)}</option>)}
      </select>
      <ErrorBox error={error} />
      {!data ? (!error && <Loading />) : (
        <>
          <Card title={t("mk.advice", lang)}>
            <ul className="list-disc space-y-1 pl-5 text-sm">{data.advice.map((a, i) => <li key={i}>{marketAdvice(a, lang)}</li>)}</ul>
            {data.reference?.rs_per_qtl && (
              <p className="mt-2 text-xs text-[var(--text-muted)]">{t("mk.reference", lang, { p: data.reference.rs_per_qtl.toLocaleString("en-IN"), src: data.reference.source })}</p>
            )}
          </Card>
          {data.trend.length > 1 && (
            <Card title={t("mk.trend", lang)}>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={data.trend} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
                  <CartesianGrid stroke={C.grid} vertical={false} />
                  <XAxis dataKey="week" tickFormatter={(d) => fmtDate(d, lang, { month: "short", year: "2-digit" })} minTickGap={30} {...axisProps} />
                  <YAxis domain={["auto", "auto"]} {...axisProps} />
                  <Line dataKey="price" stroke={C.series1} strokeWidth={2} dot={false} isAnimationActive={false} />
                  <Tooltip labelFormatter={(d) => fmtDate(d, lang)} formatter={(v) => [`₹${v.toLocaleString("en-IN")}`, t("mk.price", lang)]} />
                </LineChart>
              </ResponsiveContainer>
            </Card>
          )}
          {data.markets.length > 0 && (
            <Card title={t("mk.mandis", lang)}>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-[var(--text-secondary)]">
                    <tr><th className="py-1 pr-3">{t("mk.market", lang)}</th><th className="pr-3">{t("map.district", lang)}</th>
                      <th className="pr-3 text-right">{t("mk.price", lang)}</th><th className="pr-3 text-right">{t("mk.distance", lang)}</th><th>{t("mk.date", lang)}</th></tr>
                  </thead>
                  <tbody className="tabular">
                    {data.markets.map((m) => (
                      <tr key={`${m.market}-${m.district}`} className="border-t border-black/5">
                        <td className="py-1.5 pr-3">{m.market}</td><td className="pr-3">{m.district}</td>
                        <td className="pr-3 text-right">₹{Math.round(m.modal_price).toLocaleString("en-IN")}</td>
                        <td className="pr-3 text-right">{m.distance_km != null ? `${m.distance_km} km` : "—"}</td>
                        <td>{fmtDate(m.arrival_date, lang, { day: "numeric", month: "short" })}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
    </Page>
  );
}
