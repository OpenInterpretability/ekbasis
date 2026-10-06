// Dock icons: a gradient tile and a white line glyph (inline SVG, so nothing depends on an emoji font).
const svg = (d, extra = '') => `<svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ${extra}>${d}</svg>`;
export const ICONS = {
  mail: { bg: 'linear-gradient(135deg,#60a5fa,#2563eb)', glyph: svg('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>') },
  cloud: { bg: 'linear-gradient(135deg,#2dd4bf,#0f766e)', glyph: svg('<path d="M7 18h10a4 4 0 0 0 .5-7.97A6 6 0 0 0 6.1 9.5 4.25 4.25 0 0 0 7 18z"/>') },
  files: { bg: 'linear-gradient(135deg,#fbbf24,#d97706)', glyph: svg('<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>') },
  shop: { bg: 'linear-gradient(135deg,#f472b6,#db2777)', glyph: svg('<path d="M6 7h12l-1 13H7z"/><path d="M9 7a3 3 0 0 1 6 0"/>') },
  chat: { bg: 'linear-gradient(135deg,#a78bfa,#7c3aed)', glyph: svg('<path d="M4 5h16v11H9l-5 4z"/>') },
  drive: { bg: 'linear-gradient(135deg,#4ade80,#16a34a)', glyph: svg('<path d="M12 3l9 15H3z"/><path d="M8 13h8"/>') },
  tax: { bg: 'linear-gradient(135deg,#94a3b8,#475569)', glyph: svg('<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4M10 12h5M10 16h5"/>') },
  calendar: { bg: 'linear-gradient(135deg,#fb7185,#e11d48)', glyph: svg('<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/>') },
  repo: { bg: 'linear-gradient(135deg,#64748b,#1e293b)', glyph: svg('<circle cx="7" cy="6" r="2"/><circle cx="7" cy="18" r="2"/><circle cx="17" cy="9" r="2"/><path d="M7 8v8M17 11c0 4-6 3-10 5"/>') },
  puzzle: { bg: 'linear-gradient(135deg,#818cf8,#4338ca)', glyph: svg('<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/>') },
};
