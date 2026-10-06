// Every app of the demo desktop. Contract (each app module's default export):
//   id, title, icon {bg, glyph}, rules (the app's manual in plain English: what Ekbasis is told),
//   windowTitle(state)?, render(state, ui) -> HTML with data-el="<app>.<element>" on everything the agent can act on,
//   describe(state) -> the screen as text for the agent (element ids in [brackets]),
//   click(state, el, world) -> new state (pure), type(state, el, text) -> new state (pure),
//   foresight(state, el) -> null | {label, action, state, questions: [{key, text, options, bad, say: {answer: sentence}}]}
//     (label: shown in the panel; action/state: what Ekbasis is asked about, in plain English; bad: the harmful answer).
// Apps are loaded by id, so a new app only needs its file here; a file that is missing is skipped, any other error shows.
const IDS = ['mail', 'cloud', 'files', 'shop', 'chat', 'drive', 'calendar', 'puzzle'];
const APPS = {};
for (const id of IDS) {
  try {
    APPS[id] = (await import(`./${id}.js`)).default;
  } catch (e) {
    if (!/Failed to fetch|Importing a module script failed|404/.test(String(e))) console.error(`app ${id}:`, e);
  }
}
export default APPS;
