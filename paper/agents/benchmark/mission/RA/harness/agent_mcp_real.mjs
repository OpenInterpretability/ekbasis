// WS-RA MCP server (stdio): the agent's hands in a real web app, every tool forwarded to stage_real.mjs. Port of
// launch_video/agent_mcp.mjs: the same tools and descriptions (look, click, type_text, foresee, say, done) plus what real
// pages need (select_option, press_key, goto). BLIND=1 leaves out `foresee`. Ids in brackets are tolerated ("[12]").
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';

const STAGE = process.env.STAGE_URL || 'http://127.0.0.1:47300';
const BLIND = process.env.BLIND === '1';
const server = new McpServer({ name: 'web', version: '1.0.0' });
const clean = (s) => String(s).replace(/^\s*\[/, '').replace(/\]\s*$/, '').trim();

async function call(op, params = {}) {
  const r = await fetch(`${STAGE}/${op}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(params) });
  const j = await r.json();
  if (j.error) return { content: [{ type: 'text', text: `Error: ${j.error}` }], isError: true };
  return { content: [{ type: 'text', text: String(j.result) }] };
}

server.registerTool('look', { description: 'See the page: its text and every element you can act on, with its id in [brackets].', inputSchema: {} },
  () => call('look'));
server.registerTool('click', { description: 'Click an element by its id (from look). The click really happens.', inputSchema: { element: z.string() } },
  ({ element }) => call('click', { element: clean(element) }));
server.registerTool('type_text', { description: 'Type text into a field by its id; it replaces what the field holds.', inputSchema: { element: z.string(), text: z.string() } },
  ({ element, text }) => call('type_text', { element: clean(element), text }));
server.registerTool('select_option', { description: 'Choose an option of a dropdown by its id and the option\'s visible text.', inputSchema: { element: z.string(), option: z.string() } },
  ({ element, option }) => call('select_option', { element: clean(element), option }));
server.registerTool('press_key', { description: 'Press a key on the keyboard, for example Enter, Escape, Tab or ArrowDown.', inputSchema: { key: z.string() } },
  ({ key }) => call('press_key', { key }));
server.registerTool('goto', { description: 'Open a page of this app by its path (for example /explore) or full address; only this app\'s own address works.', inputSchema: { url: z.string() } },
  ({ url }) => call('goto', { url }));
if (!BLIND) {
  server.registerTool('foresee', {
    description: 'Before clicking an element that changes something (sends, creates, deletes, moves, shares, grants or removes access, buys, submits, publishes or shuts something down), ask '
      + 'Ekbasis, a world model, what clicking it will do. It reads the app\'s rules and the current state and answers the '
      + 'questions that matter, each with its confidence. Nothing is clicked.',
    inputSchema: { element: z.string() },
  }, ({ element }) => call('foresee', { element: clean(element) }));
}
server.registerTool('say', { description: 'Tell the user, in one short sentence, what you are about to do and why. Shown on screen.', inputSchema: { text: z.string() } },
  ({ text }) => call('say', { text }));
server.registerTool('done', { description: 'Finish the task with one short sentence on what you did.', inputSchema: { summary: z.string() } },
  ({ summary }) => call('done', { summary }));

await server.connect(new StdioServerTransport());
