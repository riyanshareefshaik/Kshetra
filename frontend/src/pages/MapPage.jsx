import { useCallback, useEffect, useState } from "react";
import { GeoJSON, MapContainer, TileLayer, useMap } from "react-leaflet";
import "@geoman-io/leaflet-geoman-free";
import { api } from "../api.js";
import { ErrorBox } from "../components/ui.jsx";
import { useApp } from "../state.jsx";
import { t } from "../i18n.js";

const CENTER = [16.5, 80.65];   // Krishna district, Andhra Pradesh
const IRRIGATION = ["rainfed", "canal", "borewell", "tank", "drip", "sprinkler", "unknown"];

function DrawControls({ onPolygon, onPin }) {
  const map = useMap();
  useEffect(() => {
    map.pm.addControls({
      position: "topleft", drawMarker: true, drawPolygon: true, drawRectangle: true, drawCircle: false,
      drawCircleMarker: false, drawPolyline: false, drawText: false, cutPolygon: false, rotateMode: false,
      dragMode: false, removalMode: false,
    });
    const onCreate = (e) => {
      const gj = e.layer.toGeoJSON();
      map.removeLayer(e.layer);
      if (gj.geometry.type === "Point") onPin(gj.geometry.coordinates[1], gj.geometry.coordinates[0]);
      else onPolygon(gj.geometry);
    };
    map.on("pm:create", onCreate);
    return () => {
      map.off("pm:create", onCreate);
      map.pm.removeControls();
    };
  }, [map, onPolygon, onPin]);
  return null;
}

function FlyTo({ field }) {
  const map = useMap();
  useEffect(() => {
    if (field?.lat) map.flyTo([field.lat, field.lon], Math.max(map.getZoom(), 16), { duration: 0.6 });
  }, [field?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

export default function MapPage() {
  const { fields, field, selectField, reloadFields, lang } = useApp();
  const [draft, setDraft] = useState(null);      // { geometry, boundary_source, note }
  const [form, setForm] = useState({ name: "", irrigation_type: "unknown", district: "", state: "Andhra Pradesh" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const onPolygon = useCallback((geometry) => setDraft({ geometry, boundary_source: "drawn" }), []);
  const onPin = useCallback(async (lat, lon) => {
    setBusy(true);
    setError(null);
    try {
      setDraft(await api.autoBoundary(lat, lon));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }, []);

  // Poll while the selected field's history is being built.
  useEffect(() => {
    if (!field || !["pending", "running"].includes(field.ingest_status)) return undefined;
    const id = setInterval(reloadFields, 5000);
    return () => clearInterval(id);
  }, [field, reloadFields]);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const created = await api.createField({
        name: form.name || null, boundary: draft.geometry, boundary_source: draft.boundary_source,
        irrigation_type: form.irrigation_type, district: form.district || null, state: form.state || null,
      });
      setDraft(null);
      await reloadFields();
      selectField(created.id);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full flex-col md:flex-row">
      <MapContainer center={CENTER} zoom={12} className="min-h-[55vh] flex-1">
        <TileLayer attribution="Imagery &copy; Esri, Maxar, Earthstar Geographics"
                   url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}" />
        {fields.map((f) => (
          <GeoJSON key={`${f.id}-${f.id === field?.id}`} data={f.boundary}
                   style={{ color: f.id === field?.id ? "#fab219" : "#ffffff", weight: 2, fillOpacity: 0.12 }}
                   eventHandlers={{ click: () => selectField(f.id) }} />
        ))}
        {draft && <GeoJSON key={JSON.stringify(draft.geometry)} data={draft.geometry} style={{ color: "#2a78d6", weight: 2, dashArray: null }} />}
        <DrawControls onPolygon={onPolygon} onPin={onPin} />
        <FlyTo field={field} />
      </MapContainer>

      <aside className="w-full space-y-4 overflow-y-auto border-t border-black/10 bg-white p-4 text-sm md:w-96 md:border-l md:border-t-0">
        <ErrorBox error={error} />
        {draft ? (
          <div className="space-y-3">
            <h2 className="font-semibold">{t("map.new", lang)}</h2>
            {draft.boundary_source === "pin_buffer" && <p className="text-[var(--text-secondary)]">{t("bnd.pin", lang)}</p>}
            <label className="block">{t("map.name", lang)}
              <input className="mt-1 w-full rounded border border-black/15 px-2 py-1" value={form.name}
                     onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder={t("map.namePh", lang)} />
            </label>
            <label className="block">{t("map.irrigation", lang)}
              <select className="mt-1 w-full rounded border border-black/15 px-2 py-1" value={form.irrigation_type}
                      onChange={(e) => setForm({ ...form, irrigation_type: e.target.value })}>
                {IRRIGATION.map((i) => <option key={i} value={i}>{t(`irr.${i}`, lang)}</option>)}
              </select>
            </label>
            <div className="grid grid-cols-2 gap-2">
              <label className="block">{t("map.district", lang)}
                <input className="mt-1 w-full rounded border border-black/15 px-2 py-1" value={form.district}
                       onChange={(e) => setForm({ ...form, district: e.target.value })} placeholder="Krishna" />
              </label>
              <label className="block">{t("map.state", lang)}
                <input className="mt-1 w-full rounded border border-black/15 px-2 py-1" value={form.state}
                       onChange={(e) => setForm({ ...form, state: e.target.value })} />
              </label>
            </div>
            <p className="text-xs text-[var(--text-muted)]">{t("map.districtHelp", lang)}</p>
            <div className="flex gap-2">
              <button disabled={busy} onClick={save} className="rounded bg-[var(--brand)] px-3 py-1.5 text-white disabled:opacity-50">
                {t("map.saveBuild", lang)}
              </button>
              <button onClick={() => setDraft(null)} className="rounded border border-black/15 px-3 py-1.5">{t("cancel", lang)}</button>
            </div>
          </div>
        ) : field ? (
          <FieldPanel field={field} lang={lang} onChanged={reloadFields} onDeleted={() => { selectField(null); reloadFields(); }} />
        ) : (
          <div className="space-y-2">
            <h2 className="font-semibold">{t("map.select", lang)}</h2>
            <p className="text-[var(--text-secondary)]">{t("map.help", lang)}</p>
            {busy && <p>{t("map.finding", lang)}</p>}
          </div>
        )}
      </aside>
    </div>
  );
}

function FieldPanel({ field, lang, onChanged, onDeleted }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    api.field(field.id).then(setDetail).catch(setError);
  }, [field.id, field.ingest_status]);
  const f = detail || field;
  const status = t(`status.${f.ingest_status}`, lang);
  const BOUNDARY = { drawn: "bnd.drawn", auto_ndvi: "bnd.auto", auto_sam: "bnd.auto", pin_buffer: "bnd.pin" };

  return (
    <div className="space-y-3">
      <h2 className="font-semibold">{f.name || t("map.select", lang)}</h2>
      <ErrorBox error={error} />
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        <dt className="text-[var(--text-secondary)]">{t("map.area", lang)}</dt><dd>{f.area_ha?.toFixed(2)} ha ({(f.area_ha * 2.471).toFixed(2)} {t("map.acres", lang)})</dd>
        <dt className="text-[var(--text-secondary)]">{t("map.district", lang)}</dt><dd>{f.district || "—"}</dd>
        {detail && <><dt className="text-[var(--text-secondary)]">{t("map.soil", lang)}</dt><dd>{detail.soil_texture ? `${detail.soil_texture}, clay ${detail.clay_pct}%, pH ${detail.ph_h2o}` : "—"}</dd></>}
        {detail && <><dt className="text-[var(--text-secondary)]">{t("map.irrigation", lang)}</dt><dd>{detail.irrigation_type ? t(`irr.${detail.irrigation_type}`, lang) : "—"}</dd></>}
        {detail && <><dt className="text-[var(--text-secondary)]">{t("map.boundary", lang)}</dt><dd>{t(BOUNDARY[detail.boundary_source] || "bnd.drawn", lang)}</dd></>}
        <dt className="text-[var(--text-secondary)]">{t("map.status", lang)}</dt><dd>{status}</dd>
      </dl>
      {f.ingest_status === "failed" && (
        <p className="rounded bg-amber-50 p-2 text-xs text-amber-900">{t("map.failedMsg", lang)}</p>
      )}
      {f.ingest_status === "done" && detail?.ingest_error && (
        <p className="rounded bg-amber-50 p-2 text-xs text-amber-900">{t("map.gapsMsg", lang)}</p>
      )}
      <div className="flex flex-wrap gap-2">
        <button className="rounded border border-black/15 px-3 py-1.5"
                onClick={async () => { await api.refreshField(f.id); onChanged(); }}>{t("map.refresh", lang)}</button>
        <button className="rounded border border-red-300 px-3 py-1.5 text-red-800"
                onClick={async () => { if (confirm(t("map.deleteConfirm", lang))) { await api.deleteField(f.id); onDeleted(); } }}>
          {t("delete", lang)}
        </button>
      </div>
    </div>
  );
}
