import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Card, CropBadge, ErrorBox, EventTag, Loading, NeedField, Page, RangeBar, SeasonSelect, StatTile } from "../components/ui.jsx";
import { reasonText, twinDiff } from "../components/words.js";
import { C } from "../components/tokens.jsx";
import { fmtDate, t } from "../i18n.js";
import { useApp } from "../state.jsx";

export default function WhyPage() {
  return <NeedField><Why /></NeedField>;
}

function Why() {
  const { fieldId, lang } = useApp();
  const [seasons, setSeasons] = useState(null);
  const [sid, setSid] = useState(null);
  const [why, setWhy] = useState(null);
  const [twins, setTwins] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.seasons(fieldId).then((s) => {
      setSeasons(s);
      const done = s.filter((x) => !x.in_progress);
      setSid((done[done.length - 1] || s[s.length - 1])?.id || null);
    }).catch(setError);
  }, [fieldId]);

  useEffect(() => {
    if (!sid) return;
    setWhy(null);
    setTwins(null);
    Promise.all([api.why(sid), api.twins(sid)]).then(([w, tw]) => { setWhy(w); setTwins(tw); }).catch(setError);
  }, [sid]);

  if (!seasons) return <Page><ErrorBox error={error} /><Loading /></Page>;
  if (!seasons.length) return <Page><Card>{t("tl.noSeasons", lang)}</Card></Page>;
  const season = seasons.find((s) => s.id === sid);
  const maxY = Math.max(1, why?.yield_t_ha?.high || 0, ...(twins?.twins || []).map((x) => x.yield_high_t_ha || 0));
  const stressEvents = why?.events.filter((e) => ["dry_spell", "waterlogging", "flood", "heat_stress", "sudden_damage"].includes(e.event_type)) || [];

  return (
    <Page title={t("why.title", lang)}>
      <ErrorBox error={error} />
      <SeasonSelect seasons={seasons} value={sid} onChange={setSid} />
      {!why ? <Loading /> : (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <StatTile label={t("crop", lang)} value={<CropBadge season={season} />} />
            <StatTile label={t("yieldRange", lang)}
                      value={why.yield_t_ha.mid != null ? `${why.yield_t_ha.low.toFixed(1)}–${why.yield_t_ha.high.toFixed(1)}` : "—"}
                      sub={why.yield_t_ha.mid != null ? `${t("tHa", lang)} · ${t(why.is_forecast ? "forecast" : "estimate", lang)}` : t("why.notEnough", lang)} />
            <StatTile label={t("why.stressCount", lang)} value={stressEvents.length} sub={t("why.detected", lang)} />
          </div>

          <Card title={t("why.reasons", lang)}>
            {why.likely_reasons.length === 0 ? (
              <p className="text-sm text-[var(--text-secondary)]">{t("why.nothing", lang)}</p>
            ) : (
              <ul className="space-y-2">
                {why.likely_reasons.map((r, i) => (
                  <li key={i} className="flex gap-2 text-sm">
                    <span aria-hidden style={{ color: r.direction === "up" ? C.good : C.critical }}>{r.direction === "up" ? "▲" : "▼"}</span>
                    <span>{reasonText(r, lang)}</span>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-3 text-xs text-[var(--text-muted)]">{t("why.note", lang)}</p>
          </Card>

          {stressEvents.length > 0 && (
            <Card title={t("why.happened", lang)}>
              <ul className="space-y-1 text-sm">
                {stressEvents.map((e, i) => (
                  <li key={i} className="flex flex-wrap gap-x-3"><EventTag event={e} />
                    <span className="tabular text-[var(--text-secondary)]">{fmtDate(e.start_date, lang)}{e.end_date && e.end_date !== e.start_date ? ` → ${fmtDate(e.end_date, lang)}` : ""}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <Card title={t("why.twins", lang)}>
            {!twins ? <Loading /> : twins.twins.length === 0 ? (
              <p className="text-sm text-[var(--text-secondary)]">{t("why.noTwins", lang)}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-[var(--text-secondary)]">
                    <tr><th className="py-1 pr-3">#</th><th className="pr-3">{t("season", lang)}</th><th className="pr-3">{t("yieldRange", lang)}</th><th>{t("why.different", lang)}</th></tr>
                  </thead>
                  <tbody>
                    <tr className="border-t border-black/5 bg-[var(--page)]">
                      <td className="py-1.5 pr-3 font-medium">{t("why.yourField", lang)}</td><td className="pr-3">{twins.year}</td>
                      <td className="pr-3"><RangeBar low={why.yield_t_ha.low} mid={why.yield_t_ha.mid} high={why.yield_t_ha.high} max={maxY} /></td><td />
                    </tr>
                    {twins.twins.map((tw, i) => (
                      <tr key={tw.season_id} className="border-t border-black/5 align-top">
                        <td className="py-1.5 pr-3">{i + 1} <span className="text-xs text-[var(--text-muted)]">{tw.district}</span></td>
                        <td className="pr-3">{tw.year}</td>
                        <td className="pr-3"><RangeBar low={tw.yield_low_t_ha} mid={tw.yield_mid_t_ha} high={tw.yield_high_t_ha} max={maxY} /></td>
                        <td className="text-[var(--text-secondary)]">{tw.differences.length ? tw.differences.map((d) => twinDiff(d, lang)).join(" ") : t("why.verySimilar", lang)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="mt-2 text-xs text-[var(--text-muted)]">{t("why.twinsNote", lang)}</p>
              </div>
            )}
          </Card>
        </>
      )}
    </Page>
  );
}
