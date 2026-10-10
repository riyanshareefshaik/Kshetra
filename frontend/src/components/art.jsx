// Small hand-drawn style illustrations: crop icons, weather icons and a field scene.
import { Cloud, CloudDrizzle, CloudLightning, CloudRain, CloudSun, Sun } from "lucide-react";

const G = "#2e7d32", G2 = "#66bb6a", GOLD = "#e9a823", SOIL = "#7a5a43", RED = "#d84a3a", WHITE = "#ffffff";

export function CropIcon({ crop, size = 32, className = "" }) {
  const common = { width: size, height: size, viewBox: "0 0 32 32", className, "aria-hidden": true };
  switch (crop) {
    case "paddy":
      return (
        <svg {...common}><path d="M16 30V12" stroke={G} strokeWidth="2" strokeLinecap="round" />
          <path d="M16 18c-4-1-6-4-6-8M16 22c4-1 7-4 7-9" stroke={G2} strokeWidth="2" fill="none" strokeLinecap="round" />
          {[0, 1, 2, 3, 4].map((i) => <ellipse key={i} cx={16 + (i % 2 ? 2.4 : -2.4)} cy={4 + i * 2.2} rx="1.6" ry="2.4" fill={GOLD} />)}</svg>
      );
    case "maize":
      return (
        <svg {...common}><path d="M16 30V18" stroke={G} strokeWidth="2" strokeLinecap="round" />
          <path d="M16 24c-6 0-9-5-9-9 4 1 7 4 9 9zM16 24c6 0 9-5 9-9-4 1-7 4-9 9z" fill={G2} />
          <ellipse cx="16" cy="11" rx="4.5" ry="8" fill={GOLD} />
          {[6, 9, 12, 15].map((y) => <path key={y} d={`M12.5 ${y}h7`} stroke="#c98a12" strokeWidth="0.8" />)}</svg>
      );
    case "cotton":
      return (
        <svg {...common}><path d="M16 30V20" stroke={SOIL} strokeWidth="2" strokeLinecap="round" />
          <path d="M9 21l7-3 7 3-2 3H11z" fill={G} />
          {[[11, 13], [21, 13], [16, 9], [16, 15]].map(([x, y]) => <circle key={`${x}${y}`} cx={x} cy={y} r="4.6" fill={WHITE} stroke="#d9d4c7" />)}</svg>
      );
    case "pulses":
      return (
        <svg {...common}><path d="M6 26C10 14 20 8 27 6" stroke={G} strokeWidth="2" fill="none" strokeLinecap="round" />
          <path d="M9 22c2-5 7-9 12-10-1 6-6 10-12 10z" fill={G2} />
          {[12, 15.5, 19].map((x, i) => <circle key={x} cx={x} cy={19 - i * 2.6} r="1.7" fill="#3b3b2f" />)}</svg>
      );
    case "chilli":
      return (
        <svg {...common}><path d="M19 6c1 2 0 4-2 5" stroke={G} strokeWidth="2.2" fill="none" strokeLinecap="round" />
          <path d="M17 10c4 0 6 3 5 7-1 6-7 11-14 12 4-4 6-8 6-12 0-4 1-7 3-7z" fill={RED} />
          <path d="M14 11c-1-2 0-3 3-3" stroke={G2} strokeWidth="2" fill="none" /></svg>
      );
    case "sugarcane":
      return (
        <svg {...common}>{[11, 17, 23].map((x) => (
          <g key={x}><path d={`M${x} 30V6`} stroke="#9ccc65" strokeWidth="3.4" strokeLinecap="round" />
            {[11, 17, 23].map((y) => <path key={y} d={`M${x - 1.7} ${y}h3.4`} stroke={G} strokeWidth="1.2" />)}</g>
        ))}<path d="M23 7c3-3 6-3 8-2M11 8C8 4 5 4 2 5" stroke={G} strokeWidth="1.6" fill="none" strokeLinecap="round" /></svg>
      );
    default:
      return (
        <svg {...common}><path d="M16 30V14" stroke={G} strokeWidth="2" strokeLinecap="round" />
          <path d="M16 20c-6 0-9-4-9-9 5 0 9 4 9 9zM16 16c0-6 4-10 10-10 0 6-4 10-10 10z" fill={G2} /></svg>
      );
  }
}

/** Weather icon from a forecast day. */
export function WeatherIcon({ day, size = 28, className = "" }) {
  const rain = day?.rain_mm ?? 0;
  const prob = day?.rain_prob ?? 0;
  const props = { size, className, "aria-hidden": true, strokeWidth: 1.8 };
  if (rain >= 64.5) return <CloudLightning {...props} color="#3b6fb0" />;
  if (rain >= 10) return <CloudRain {...props} color="#3b82c4" />;
  if (rain >= 2.5) return <CloudDrizzle {...props} color="#5b9bd5" />;
  if (prob >= 50) return <Cloud {...props} color="#8a96a3" />;
  if (prob >= 25) return <CloudSun {...props} color="#e9a823" />;
  return <Sun {...props} color="#e9a823" />;
}

/** Rolling fields under a rising sun, for welcome and empty screens. */
export function FieldScene({ className = "" }) {
  return (
    <svg viewBox="0 0 320 140" className={className} aria-hidden>
      <defs>
        <linearGradient id="ks-sky" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#fdf4dd" /><stop offset="1" stopColor="#ecf6ea" /></linearGradient>
      </defs>
      <rect width="320" height="140" fill="url(#ks-sky)" />
      <circle cx="248" cy="52" r="22" fill="#f6c453" />
      <path d="M0 92 C60 70 120 78 180 88 S280 84 320 74 V140 H0Z" fill="#a5d6a7" />
      <path d="M0 110 C70 92 150 100 220 108 S300 104 320 98 V140 H0Z" fill="#66bb6a" />
      <path d="M0 126 C80 114 170 120 320 116 V140 H0Z" fill="#2e7d32" />
      {Array.from({ length: 9 }).map((_, i) => (
        <path key={i} d={`M${20 + i * 34} 140 Q ${40 + i * 30} 118 ${60 + i * 28} 104`} stroke="#1b5e20" strokeOpacity="0.25" fill="none" />
      ))}
      <g transform="translate(70 66)"><path d="M0 26V8" stroke="#1b5e20" strokeWidth="2" /><path d="M0 14c-5 0-8-4-8-8 5 0 8 4 8 8zM0 10c0-5 4-8 8-8 0 5-4 8-8 8z" fill="#2e7d32" /></g>
    </svg>
  );
}
