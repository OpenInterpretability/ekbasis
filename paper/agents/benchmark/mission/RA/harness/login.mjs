// Signs a seeded test user in to a real app with a headless browser and saves the storage state, so the agent's browser
// starts signed in and never sees a password. The password is read from apps/.env and never printed.
//   node login.mjs <gitea|nextcloud|mail> <username> <out_state.json>
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ENV = Object.fromEntries(fs.readFileSync(path.join(HERE, '..', 'apps', '.env'), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => [l.slice(0, l.indexOf('=')), l.slice(l.indexOf('=') + 1)]));
const [app, user, out] = process.argv.slice(2);
const BASE = { gitea: 'http://127.0.0.1:3330', nextcloud: 'http://127.0.0.1:8481', mail: 'http://127.0.0.1:8491' }[app];
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ locale: 'en-US' });
const page = await context.newPage();
try {
  if (app === 'gitea') {
    await page.goto(`${BASE}/user/login`);
    await page.fill('#user_name', user);
    await page.fill('#password', ENV.USER_PASS);
    await Promise.all([page.waitForNavigation({ timeout: 20000 }), page.click('form.ui.form button.ui.primary.button')]);
    if (page.url().includes('/user/login')) throw new Error('gitea login failed');
  } else if (app === 'nextcloud') {
    await page.goto(`${BASE}/login`);
    await page.fill('#user', user);
    await page.fill('#password', ENV.USER_PASS);
    await page.press('#password', 'Enter');
    await page.waitForURL((u) => !String(u).includes('/login'), { timeout: 30000 });
  } else if (app === 'mail') {
    await page.goto(`${BASE}/`);
    await page.fill('#rcmloginuser', user);
    await page.fill('#rcmloginpwd', ENV.USER_PASS);
    await Promise.all([page.waitForNavigation({ timeout: 30000 }), page.click('#rcmloginsubmit')]);
    if (await page.locator('#rcmloginuser').count()) throw new Error('mail login failed');
  }
  await context.storageState({ path: out });
  console.log(`signed in ${app} ${user} -> ${out}`);
} catch (e) {
  console.error(`login ${app} ${user} failed: ${String(e.message || e).split('\n')[0]}`);
  process.exitCode = 1;
} finally {
  await browser.close();
}
