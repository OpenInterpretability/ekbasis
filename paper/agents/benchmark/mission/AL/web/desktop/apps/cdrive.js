// WS-AL multi-screen app on the flow engine (screens, variables and manual come from the scenario).
import { makeFlowApp } from './flow.js';

const glyph = '<svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 18h10a4 4 0 0 0 .5-7.97A6 6 0 0 0 6.1 9.5 4.25 4.25 0 0 0 7 18z"/></svg>';
export default makeFlowApp({ id: 'cdrive', title: 'Cloud Drive', icon: { bg: 'linear-gradient(135deg,#4ade80,#15803d)', glyph } });
