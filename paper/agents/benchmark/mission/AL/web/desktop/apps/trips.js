// WS-AL multi-screen app on the flow engine (screens, variables and manual come from the scenario).
import { makeFlowApp } from './flow.js';

const glyph = '<svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 16l20-8-8 12-2-5z"/></svg>';
export default makeFlowApp({ id: 'trips', title: 'Trips', icon: { bg: 'linear-gradient(135deg,#fb923c,#c2410c)', glyph } });
