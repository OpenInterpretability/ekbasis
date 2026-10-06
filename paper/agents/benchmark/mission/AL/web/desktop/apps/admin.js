// WS-AL multi-screen app on the flow engine (screens, variables and manual come from the scenario).
import { makeFlowApp } from './flow.js';

const glyph = '<svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="8" r="3"/><path d="M3 20c0-3 3-5 6-5s6 2 6 5M16 11a3 3 0 1 0 0-6M21 20c0-2-1.5-3.5-3.5-4.3"/></svg>';
export default makeFlowApp({ id: 'admin', title: 'Team Admin', icon: { bg: 'linear-gradient(135deg,#38bdf8,#0369a1)', glyph } });
