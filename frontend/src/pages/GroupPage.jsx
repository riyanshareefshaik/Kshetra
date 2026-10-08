import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Card, ErrorBox, Loading, Page, StatTile } from "../components/ui.jsx";
import { cropName, t } from "../i18n.js";
import { useApp } from "../state.jsx";

export default function GroupPage() {
  const { lang } = useApp();
  const [groups, setGroups] = useState(null);
  const [gid, setGid] = useState(null);
  const [dash, setDash] = useState(null);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState(null);

  const load = () => api.groups().then((g) => { setGroups(g); setGid((cur) => cur && g.some((x) => x.id === cur) ? cur : g[0]?.id || null); }).catch(setError);
  useEffect(() => { load(); }, []);
  useEffect(() => {
    setDash(null);
    if (gid) api.groupDashboard(gid).then(setDash).catch(setError);
  }, [gid, groups]);

  const act = (fn) => async (e) => {
    e?.preventDefault?.();
    setError(null);
    try { await fn(); await load(); } catch (err) { setError(err); }
  };
  const g = groups?.find((x) => x.id === gid);

  return (
    <Page title={t("gr.title", lang)} wide>
      <ErrorBox error={error} />
      <div className="grid gap-4 md:grid-cols-2">
        <Card title={t("gr.create", lang)}>
          <form onSubmit={act(async () => { const x = await api.createGroup({ name }); setName(""); setGid(x.id); })} className="flex gap-2 text-sm">
            <input required minLength={2} className="min-w-0 flex-1 rounded border border-black/15 px-2 py-1" placeholder={t("gr.name", lang)}
                   value={name} onChange={(e) => setName(e.target.value)} />
            <button className="rounded bg-[var(--brand)] px-3 py-1 text-white">{t("save", lang)}</button>
          </form>
        </Card>
        <Card title={t("gr.join", lang)}>
          <form onSubmit={act(async () => { const x = await api.joinGroup(code); setCode(""); setGid(x.id); })} className="flex gap-2 text-sm">
            <input required className="min-w-0 flex-1 rounded border border-black/15 px-2 py-1 uppercase" placeholder={t("gr.code", lang)}
                   value={code} onChange={(e) => setCode(e.target.value)} />
            <button className="rounded bg-[var(--brand)] px-3 py-1 text-white">{t("gr.join", lang)}</button>
          </form>
        </Card>
      </div>

      {!groups ? <Loading /> : groups.length === 0 ? <Card><p className="text-sm">{t("gr.none", lang)}</p></Card> : (
        <>
          <div className="flex flex-wrap gap-1">
            {groups.map((x) => (
              <button key={x.id} onClick={() => setGid(x.id)}
                      className={`rounded border px-2.5 py-1 text-sm ${x.id === gid ? "border-[var(--brand)] bg-[var(--brand)] text-white" : "border-black/15 bg-white"}`}>{x.name}</button>
            ))}
          </div>
          {g && (
            <Card title={g.name} actions={
              <button className="rounded border border-red-300 px-2 py-1 text-xs text-red-800" onClick={act(() => api.leaveGroup(g.id))}>{t("gr.leave", lang)}</button>
            }>
              {g.join_code && <p className="mb-2 text-sm">{t("gr.codeShare", lang, { c: g.join_code })}</p>}
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" className="h-4 w-4 accent-[var(--brand)]" checked={g.share_with_group}
                       onChange={(e) => act(() => api.shareGroup(g.id, e.target.checked))()} />
                {t("gr.share", lang)}
              </label>
              {!dash ? <Loading /> : (
                <div className="mt-4 space-y-4">
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    <StatTile label={t("gr.members", lang, { n: dash.members, s: dash.members_sharing })} value={dash.members} />
                    <StatTile label={t("gr.fields", lang)} value={dash.fields.length} />
                    <StatTile label={t("gr.area", lang)} value={`${dash.area_ha} ha`} />
                    <StatTile label={t("gr.stress", lang)} value={dash.fields_with_stress_30d} />
                  </div>
                  {Object.keys(dash.crop_area_now_ha).length > 0 && (
                    <p className="text-sm">{t("gr.cropsNow", lang)}: {Object.entries(dash.crop_area_now_ha).map(([c, a]) => `${cropName(c, lang)} ${a}`).join(" · ")}</p>
                  )}
                  {dash.fields.length > 0 && (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead className="text-left text-xs text-[var(--text-secondary)]">
                          <tr><th className="py-1 pr-3">{t("map.name", lang)}</th><th className="pr-3">{t("gr.farmer", lang)}</th><th className="pr-3">{t("map.area", lang)}</th><th className="pr-3">{t("crop", lang)}</th><th>{t("tl.stress", lang)}</th></tr>
                        </thead>
                        <tbody className="tabular">
                          {dash.fields.map((f) => (
                            <tr key={f.id} className="border-t border-black/5">
                              <td className="py-1.5 pr-3">{f.name || "—"}</td><td className="pr-3">{f.farmer}</td><td className="pr-3">{f.area_ha.toFixed(2)} ha</td>
                              <td className="pr-3">{f.crop_now ? cropName(f.crop_now, lang) : "—"}</td><td>{f.stress_30d}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {dash.yields.length > 0 && (
                    <div><h3 className="mb-1 text-sm font-medium">{t("gr.yields", lang)}</h3>
                      <ul className="text-sm">{dash.yields.map((y, i) => <li key={i}>{t(y.season, lang)} {y.year} · {cropName(y.crop, lang)}: {y.avg_yield_t_ha} {t("tHa", lang)} ({y.n})</li>)}</ul>
                    </div>
                  )}
                </div>
              )}
            </Card>
          )}
        </>
      )}
    </Page>
  );
}
