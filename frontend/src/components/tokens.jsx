// Chart colours as hex (SVG presentation attributes do not resolve CSS variables reliably).
// Same values as the CSS tokens in index.css; series validated against each mode's card surface.
const STATUS = { warning: "#fab219", serious: "#ec835a", critical: "#d03b3b", good: "#0ca30c" };
const LIGHT = {
  surface: "#ffffff", grid: "#ececea", axis: "#d4d4d0", muted: "#868c86", secondary: "#545a55",
  series1: "#2a78d6", series2: "#eb6834", band: "#f1f1ee", ...STATUS,
};
const DARK = {
  surface: "#141416", grid: "#26262a", axis: "#3a3a40", muted: "#85898a", secondary: "#b9bcb8",
  series1: "#3987e5", series2: "#d95926", band: "#1c1c20", ...STATUS,
};

// Read at render time; the theme provider switches it before the tree re-renders.
export const C = { ...LIGHT };
export function setChartTheme(mode) {
  Object.assign(C, mode === "dark" ? DARK : LIGHT);
  axisProps.stroke = C.axis;
  axisProps.tick = { fill: C.muted, fontSize: 11 };
}

/** Bar shape with a 2px surface gap between neighbouring bars and 2px rounded data-end. */
export function GapBar({ x, y, width, height, fill }) {
  if (!height || height <= 0) return null;
  const w = Math.max(width - 2, 1);
  const r = Math.min(2, w / 2, height);
  return <path d={`M${x + 1},${y + height} V${y + r} Q${x + 1},${y} ${x + 1 + r},${y} H${x + 1 + w - r} Q${x + 1 + w},${y} ${x + 1 + w},${y + r} V${y + height} Z`} fill={fill ?? C.series1} />;
}

export const axisProps = { stroke: LIGHT.axis, tick: { fill: LIGHT.muted, fontSize: 11 } };
