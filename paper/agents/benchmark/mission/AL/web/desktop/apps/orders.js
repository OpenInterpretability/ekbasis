// WS-AL multi-screen app on the flow engine (screens, variables and manual come from the scenario).
import { makeFlowApp } from './flow.js';

const glyph = '<svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 7h12l-1 13H7z"/><path d="M9 7a3 3 0 0 1 6 0"/></svg>';
export default makeFlowApp({ id: 'orders', title: 'Orders', icon: { bg: 'linear-gradient(135deg,#f472b6,#be185d)', glyph } });
