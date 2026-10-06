// WS-AL multi-screen app on the flow engine (screens, variables and manual come from the scenario).
import { makeFlowApp } from './flow.js';

const glyph = '<svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2"/></svg>';
export default makeFlowApp({ id: 'settings', title: 'Settings', icon: { bg: 'linear-gradient(135deg,#94a3b8,#334155)', glyph } });
