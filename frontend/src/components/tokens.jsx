// Chart colours as hex (SVG presentation attributes do not resolve CSS variables reliably).
// Same values as the CSS tokens in index.css; series validated against each mode's card surface.
const STATUS = { warning: "#fab219", serious: "#ec835a", critical: "#d03b3b", good: "#0ca30c" };
const LIGHT = {
  surface: "#ffffff", grid: "#e5e2d6", axis: "#c9c5b5", muted: "#7d8378", secondary: "#4f5a4f",
  series1: "#2a78d6", series2: "#eb6834", band: "#efeee9", ...STATUS,
};
const DARK = {
  surface: "#18201a", grid: "#2a332c", axis: "#3c463d", muted: "#8e968b", secondary: "#c0c7bb",
  series1: "#3987e5", series2: "#d95926", band: "#222b24", ...STATUS,
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
