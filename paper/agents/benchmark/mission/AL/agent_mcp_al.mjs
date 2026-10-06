// WS-AL copy (+ `advise` when AHEAD=1). MCP server (stdio) that gives a real agent its hands on the demo desktop: every tool is forwarded to the stage
// (stage.mjs). BLIND=1 leaves out `foresee` (the same agent without a world model). STAGE_URL picks the stage.
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';

const STAGE = process.env.STAGE_URL || 'http://127.0.0.1:8771';
const BLIND = process.env.BLIND === '1';
const server = new McpServer({ name: 'desk', version: '1.0.0' });

async function call(op, params = {}) {
  const r = await fetch(`${STAGE}/${op}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(params) });
  const j = await r.json();
  if (j.error) return { content: [{ type: 'text', text: `Error: ${j.error}` }], isError: true };
  return { content: [{ type: 'text', text: String(j.result) }] };
}

server.registerTool('look', { description: 'See the screen: the open windows, their content, and every element you can act on, with its id in [brackets].', inputSchema: {} },
  () => call('look'));
server.registerTool('open_app', { description: "Open an app from the dock by its id (for example 'mail'), or bring it to the front.", inputSchema: { app: z.string() } },
  ({ app }) => call('open_app', { app }));
server.registerTool('click', { description: 'Click an element by its id (from look). The click really happens.', inputSchema: { element: z.string() } },
  ({ element }) => call('click', { element }));
server.registerTool('type_text', { description: 'Type text into a field by its id; it replaces what the field holds.', inputSchema: { element: z.string(), text: z.string() } },
  ({ element, text }) => call('type_text', { element, text }));
if (!BLIND) {
  server.registerTool('foresee', {
    description: 'Before clicking an element that sends, deletes, buys, shares, submits, publishes or shuts something down, ask '
      + 'Ekbasis, a world model, what clicking it will do. It reads the app\'s rules and the current state and answers the '
      + 'questions that matter, each with its confidence. Nothing is clicked.',
    inputSchema: { element: z.string() },
  }, ({ element }) => call('foresee', { element }));
}
if (process.env.AHEAD === '1') {
  server.registerTool('advise', {
    description: 'Ask Ekbasis, a world model that knows how this app works, which action moves your task forward. It ranks '
      + 'the actions on the current screen (or up to 3 element ids you name) and predicts what the consequential ones '
      + 'would do, each with its confidence. Nothing is clicked.',
    inputSchema: { candidates: z.array(z.string()).max(3).optional() },
  }, ({ candidates }) => call('advise', { candidates: candidates || [] }));
}
if (process.env.TRACK === '1') {
  server.registerTool('balances', {
    description: 'Ask Ekbasis, a world model that has followed every instruction processed so far, for the current balance '
      + 'of each account, with its confidence. It looks at the real balances by itself (using one of your balance checks) '
      + 'when it is unsure. Nothing is processed.',
    inputSchema: {},
  }, () => call('balances'));
}
server.registerTool('say', { description: 'Tell the user, in one short sentence, what you are about to do and why. Shown on screen.', inputSchema: { text: z.string() } },
  ({ text }) => call('say', { text }));
server.registerTool('done', { description: 'Finish the task with one short sentence on what you did.', inputSchema: { summary: z.string() } },
  ({ summary }) => call('done', { summary }));

await server.connect(new StdioServerTransport());
