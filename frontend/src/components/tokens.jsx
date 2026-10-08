// Chart colours as hex (SVG presentation attributes do not resolve CSS variables reliably).
// Same values as the CSS tokens in index.css: the dataviz reference palette, light surface.
export const C = {
  surface: "#fcfcfb",
  grid: "#e1e0d9",
  axis: "#c3c2b7",
  muted: "#898781",
  secondary: "#52514e",
  series1: "#2a78d6",
  series2: "#eb6834",
  band: "#efeee9",
  warning: "#fab219",
  serious: "#ec835a",
  critical: "#d03b3b",
  good: "#0ca30c",
};

/** Bar shape with a 2px surface gap between neighbouring bars and 2px rounded data-end. */
export function GapBar({ x, y, width, height, fill }) {
  if (!height || height <= 0) return null;
  const w = Math.max(width - 2, 1);
  const r = Math.min(2, w / 2, height);
  return <path d={`M${x + 1},${y + height} V${y + r} Q${x + 1},${y} ${x + 1 + r},${y} H${x + 1 + w - r} Q${x + 1 + w},${y} ${x + 1 + w},${y + r} V${y + height} Z`} fill={fill ?? C.series1} />;
}

export const axisProps = { stroke: C.axis, tick: { fill: C.muted, fontSize: 11 } };
