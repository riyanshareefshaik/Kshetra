import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api.js";
import { C, GapBar, axisProps } from "../components/tokens.jsx";
import { Card, ErrorBox, Loading, Page, StatTile } from "../components/ui.jsx";
import { t } from "../i18n.js";
import { useApp } from "../state.jsx";

const CROPS = ["", "paddy", "maize", "cotton", "pulses", "chilli", "sugarcane"];

export default function InsightsPage() {
  const { lang } = useApp();
  const [filters, setFilters] = useState({ state: "", district: "", crop: "" });
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v));
    const id = setTimeout(() => api.insights(params).then((d) => { setData(d); setError(null); }).catch(setError), 250);
    return () => clearTimeout(id);
  }, [filters]);

  const groups = data?.groups || [];
  const latestYear = groups.length ? Math.max(...groups.map((g) => g.year)) : null;
  const chart = groups.filter((g) => g.year === latestYear)
    .map((g) => ({ name: `${g.crop} · ${g.variety || "any"}`, yield: Number(g.avg_yield_mid_t_ha), n: g.n_fields }))
    .sort((a, b) => b.yield - a.yield).slice(0, 10);

  return (
    <Page title={`${t("insights", lang)} · seed companies`} wide>
      <p className="text-sm text-[var(--text-secondary)]">{data?.privacy || "Aggregated, anonymous data from farmers who chose to share."} Groups smaller than {data?.min_group_size ?? 5} fields are hidden.</p>
      <div className="flex flex-wrap gap-2 text-sm">
        <input className="rounded border border-black/15 px-2 py-1" placeholder="State" value={filters.state} onChange={(e) => setFilters({ ...filters, state: e.target.value })} />
        <input className="rounded border border-black/15 px-2 py-1" placeholder="District" value={filters.district} onChange={(e) => setFilters({ ...filters, district: e.target.value })} />
        <select className="rounded border border-black/15 px-2 py-1" value={filters.crop} onChange={(e) => setFilters({ ...filters, crop: e.target.value })}>
          {CROPS.map((c) => <option key={c} value={c}>{c || "all crops"}</option>)}
        </select>
      </div>
      <ErrorBox error={error} />
      {!data ? <Loading /> : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <StatTile label="Farmers sharing" value={data.farmers_sharing} />
            <StatTile label="Groups shown" value={groups.length} sub="district · season · crop · variety" />
          </div>
          {chart.length > 0 && (
            <Card title={`Average yield by crop and variety, ${latestYear}`}>
              <ResponsiveContainer width="100%" height={Math.max(120, chart.length * 34)}>
                <BarChart data={chart} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 40 }}>
                  <CartesianGrid stroke={C.grid} horizontal={false} />
                  <XAxis type="number" {...axisProps} unit=" t/ha" />
                  <YAxis type="category" dataKey="name" width={140} stroke={C.axis} tick={{ fill: C.secondary, fontSize: 11 }} />
                  <Bar dataKey="yield" fill={C.series1} radius={[0, 4, 4, 0]} maxBarSize={20} isAnimationActive={false} />
                  <Tooltip cursor={{ fill: C.band }} formatter={(v, _n, p) => [`${v.toFixed(2)} t/ha (${p.payload.n} fields)`, "Average yield"]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          )}
          <Card title="All groups">
            {groups.length === 0 ? <p className="text-sm text-[var(--text-secondary)]">No group has 5 or more sharing fields yet.</p> : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-[var(--text-secondary)]">
                    <tr><th className="py-1 pr-3">Year</th><th className="pr-3">District</th><th className="pr-3">Season</th><th className="pr-3">Crop · variety</th>
                      <th className="pr-3 text-right">Fields</th><th className="pr-3 text-right">Avg yield</th><th className="pr-3 text-right">P25–P75</th><th className="text-right">Days</th></tr>
                  </thead>
                  <tbody className="tabular">
                    {groups.map((g, i) => (
                      <tr key={i} className="border-t border-black/5">
                        <td className="py-1 pr-3">{g.year}</td><td className="pr-3">{g.district}</td><td className="pr-3 capitalize">{g.season}</td>
                        <td className="pr-3">{g.crop} · {g.variety || "any"}</td><td className="pr-3 text-right">{g.n_fields}</td>
                        <td className="pr-3 text-right">{g.avg_yield_mid_t_ha ?? "—"}</td>
                        <td className="pr-3 text-right">{g.yield_p25_t_ha != null ? `${g.yield_p25_t_ha}–${g.yield_p75_t_ha}` : "—"}</td>
                        <td className="text-right">{g.avg_season_days ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </Page>
  );
}
