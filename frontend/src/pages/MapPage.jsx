import { useEffect, useState } from "react";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import "@geoman-io/leaflet-geoman-free";

// Default view: Krishna district, Andhra Pradesh (paddy / cotton / maize belt).
const CENTER = [16.5, 80.65];

function DrawControls({ onBoundary }) {
  const map = useMap();
  useEffect(() => {
    map.pm.addControls({
      position: "topleft",
      drawMarker: true,
      drawPolygon: true,
      drawRectangle: true,
      drawCircle: false,
      drawCircleMarker: false,
      drawPolyline: false,
      drawText: false,
      cutPolygon: false,
      rotateMode: false,
    });
    const onCreate = (e) => onBoundary(e.layer.toGeoJSON());
    map.on("pm:create", onCreate);
    return () => {
      map.off("pm:create", onCreate);
      map.pm.removeControls();
    };
  }, [map, onBoundary]);
  return null;
}

export default function MapPage() {
  const [shape, setShape] = useState(null);
  return (
    <div className="flex h-full flex-col md:flex-row">
      <MapContainer center={CENTER} zoom={14} className="min-h-[60vh] flex-1">
        <TileLayer
          attribution="Imagery &copy; Esri"
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
        />
        <DrawControls onBoundary={setShape} />
      </MapContainer>
      <aside className="w-full border-t border-stone-200 bg-white p-4 text-sm md:w-80 md:border-l md:border-t-0">
        <h2 className="font-semibold">Select a field</h2>
        <p className="mt-1 text-stone-600">Drop a pin or draw the field boundary.</p>
        {shape && (
          <pre className="mt-3 max-h-64 overflow-auto rounded bg-stone-100 p-2 text-xs">
            {JSON.stringify(shape.geometry, null, 1)}
          </pre>
        )}
      </aside>
    </div>
  );
}
