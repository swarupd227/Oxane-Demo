// Records the monitoring walkthrough against the production build, in the same way as record.mjs:
// magenta and cyan flashes frame each scene for assemble.mjs. Run serve.mjs first.
//   node record-monitoring.mjs && node assemble.mjs Monitoring_Workbench_Demo.mp4
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

process.chdir(import.meta.dirname);
const require = createRequire('C:/Users/swarupd/demo/Kinective/atlas-agent-platform/package.json');
const { chromium } = require('playwright');

const BASE = process.env.APP || 'http://127.0.0.1:5187';
const C = JSON.parse(fs.readFileSync('captions-monitoring.json', 'utf8'));
const READ_MS = 4600;
const WIDTH = 1920;
const HEIGHT = 1080;
const BAND = 190;
const APP = HEIGHT - BAND;
fs.rmSync('rec', { recursive: true, force: true });

const browser = await chromium.launch({ headless: true });

// Warm the cycle and the PDF viewer off camera.
{
  const warm = await browser.newContext({ viewport: { width: WIDTH, height: APP } });
  await warm.request.post(BASE + '/api/monitoring/session/reset');
  const p = await warm.newPage();
  await p.goto(BASE + '/monitoring/reconciliation');
  await p.locator('[data-highlight]').first().waitFor({ timeout: 120000 });
  await warm.request.post(BASE + '/api/monitoring/session/reset');
  await warm.close();
}

const context = await browser.newContext({
  viewport: { width: WIDTH, height: HEIGHT }, deviceScaleFactor: 1, colorScheme: 'light', locale: 'en-GB',
  recordVideo: { dir: 'rec', size: { width: 1920, height: 1080 } },
});
context.setDefaultTimeout(120000);
context.setDefaultNavigationTimeout(120000);
const LAYOUT = `
  html, body, #root { height: ${APP}px !important; max-height: ${APP}px !important; overflow: hidden; }
  .min-h-screen { min-height: ${APP}px !important; }
  [role="dialog"] { max-height: ${APP}px !important; }
  ${[39, 24, 17].map((rem) => `[class*="100vh-${rem}rem"] { max-height: calc(${APP}px - ${rem}rem) !important; }`).join('\n  ')}
  main { overflow: auto; max-height: ${APP - 112}px; }`;
const page = await context.newPage();
const t0 = Date.now();
const secs = () => (Date.now() - t0) / 1000;
const segments = [];
let current = null;
const log = (s) => console.log(`[${secs().toFixed(1)}] ${s}`);
const PACE = 1.22;
const hold = (ms) => page.waitForTimeout(ms >= 1200 ? ms * PACE : ms);

async function flash(color) {
  await page.evaluate((c) => {
    const d = document.createElement('div');
    d.id = 'sync-flash';
    d.style.cssText = `position:fixed;inset:0;z-index:2147483647;background:${c}`;
    document.documentElement.appendChild(d);
  }, color);
  await page.waitForTimeout(700);
  await page.evaluate(() => document.getElementById('sync-flash')?.remove());
  await page.waitForTimeout(150);
}
const start = async (name) => { await page.waitForTimeout(800); await flash('#ff00ff'); current = { name, start: secs() }; log(`start ${name}`); };
const end = async () => { current.end = secs(); await flash('#00ffff'); segments.push(current); current = null; };

async function caption(text) {
  await page.evaluate(({ t, band }) => {
    let bar = document.getElementById('demo-caption');
    if (!bar) {
      bar = document.createElement('div');
      bar.id = 'demo-caption';
      bar.innerHTML = '<div class="rule"></div><div class="txt"></div>';
      const s = document.createElement('style');
      s.textContent = `
        #demo-caption { position: fixed; left: 0; right: 0; bottom: 0; height: ${band}px; z-index: 2147483646;
          pointer-events: none; display: flex; flex-direction: column; align-items: center; justify-content: center;
          padding: 0 180px; text-align: center; opacity: 0; transition: opacity .6s ease; background: #141414; }
        #demo-caption .rule { width: 64px; height: 4px; background: #FFDD00; margin: 0 auto 15px; }
        #demo-caption .txt { font: 500 35px/1.3 Arial, Helvetica, sans-serif; color: #fff; letter-spacing: .2px; }`;
      document.head.appendChild(s);
      document.body.appendChild(bar);
    }
    const txt = bar.querySelector('.txt');
    if (bar.style.opacity === '1') {
      bar.style.opacity = '0';
      setTimeout(() => { txt.textContent = t; bar.style.opacity = '1'; }, 600);
    } else {
      txt.textContent = t;
      requestAnimationFrame(() => { bar.style.opacity = '1'; });
    }
  }, { t: text, band: BAND });
  await hold(700);
}

async function go(p) {
  await page.goto(BASE + p, { waitUntil: 'domcontentloaded' });
  await page.addStyleTag({ content: LAYOUT });
  await page.getByRole('navigation', { name: 'Monitoring steps' }).waitFor({ timeout: 60000 });
  await hold(1500);
}
async function localGo(name) {
  await page.goto(pathToFileURL(path.resolve('pages', `${name}.html`)).href);
  await hold(300);
}
const spotlight = (locator, on) => locator.evaluate((el, show) => {
  el.style.transition = 'box-shadow .4s ease';
  el.style.boxShadow = show ? '0 0 0 3px #FFDD00, 0 0 0 7px rgba(255, 221, 0, .25)' : '';
}, on);
const act = (type, actor, payload) => context.request.post(BASE + '/api/monitoring/session/events',
  { data: { type, actor, payload } });

const onFail = async (e) => {
  console.error(e);
  await page.screenshot({ path: 'fail.png' }).catch(() => {});
  process.exit(1);
};
process.on('unhandledRejection', onFail);
process.on('uncaughtException', onFail);

await context.request.post(BASE + '/api/monitoring/session/reset');

// ---------------------------------------------------------------- scenes --
await localGo('monitoring-opening');
await hold(2500);
await start('opening'); await hold(7500); await end();

// The portfolio: three facilities, one cycle.
await go('/monitoring');
await page.getByRole('heading', { name: 'Portfolio monitor' }).waitFor();
await start('portfolio'); await caption(C.portfolio); await hold(READ_MS + 400); await end();

// Collection: the late file is chased, the new columns are mapped.
await go('/monitoring/submissions');
const late = page.getByRole('status').filter({ hasText: 'was due' });
await start('submissions'); await spotlight(late, true); await caption(C.late); await hold(1800);
await page.getByRole('button', { name: 'View chase' }).click();
await hold(READ_MS - 1200);
await page.keyboard.press('Escape');
await spotlight(late, false);
const layout = page.getByText('Layout change: Bramble May tape').locator('xpath=ancestor::div[contains(@class,"rounded-xl")][1]');
await spotlight(layout, true);
await caption(C.layout); await hold(READ_MS - 800);
await page.getByRole('button', { name: 'Confirm mapping' }).click();
await hold(1400); await spotlight(layout, false); await end();

// Reconciliation, in code.
await go('/monitoring/reconciliation');
await page.locator('[data-highlight]').first().waitFor({ timeout: 30000 });
await start('reconcile'); await caption(C.rollforward); await hold(READ_MS);
const gap = page.getByText('Gap', { exact: true }).locator('xpath=ancestor::tr[1]');
await spotlight(gap, true);
await caption(C.gap); await hold(1800);
await page.getByRole('button', { name: /Open the 27 loans/ }).click();
await hold(READ_MS - 1200);
await page.keyboard.press('Escape');
await spotlight(gap, false);
await page.getByRole('button', { name: /Open the 9 loans/ }).scrollIntoViewIfNeeded();
await caption(C.chargeoffs); await hold(1400);
await page.getByRole('button', { name: /Open the 9 loans/ }).click();
await hold(READ_MS - 800);
await page.keyboard.press('Escape'); await hold(500); await end();

// The terms in force for the period.
await go('/monitoring/terms');
await page.locator('[data-highlight]').first().waitFor({ timeout: 30000 });
await start('terms'); await caption(C.terms); await hold(READ_MS - 600);
await page.getByRole('radio', { name: 'June 2026' }).click();
await hold(2000);
await page.getByRole('radio', { name: 'May 2026' }).click();
await hold(1400); await end();

// Covenants and triggers.
await go('/monitoring/covenants');
await page.locator('[data-highlight]').first().waitFor({ timeout: 30000 });
await start('covenants'); await caption(C.trigger); await hold(READ_MS);
await caption(C.whatif); await hold(900);
await page.getByRole('button', { name: 'Run what-if for June' }).click();
await page.getByRole('status').filter({ hasText: 'With June' }).waitFor();
await hold(READ_MS - 400);
// The caption changes with the tab, not after the page behind it has loaded.
await page.getByRole('tab', { name: /Bramble/ }).click();
await caption(C.leverage);
await page.locator('[data-highlight]').first().waitFor({ timeout: 30000 });
await hold(READ_MS + 600); await end();

// Collateral across facilities.
await go('/monitoring/collateral');
await start('collateral'); await caption(C.collateral); await hold(1400);
await page.getByRole('button', { name: 'Open both tape rows' }).click();
await hold(READ_MS); await end();

// Triage: the analyst decides two on camera.
await go('/monitoring/triage');
await start('triage'); await caption(C.triage); await hold(2200);
for (let i = 0; i < 2; i++) {
  await page.getByRole('button', { name: /^Confirm/ }).first().click();
  await hold(1500);
}
const held = page.getByRole('region', { name: 'Logged, no alert' });
await spotlight(held, true);
await caption(C.noise); await hold(READ_MS); await spotlight(held, false); await end();

// The rest were decided the same way.
const cycle = await (await context.request.get(BASE + '/api/monitoring/cycle')).json();
const session = await (await context.request.get(BASE + '/api/monitoring/session')).json();
for (const f of cycle.findings) {
  if (!session.decisions[f.id]) await act('triage', 'analyst', { id: f.id, outcome: f.suggested.outcome });
}

// The lender pack, drafted by AI, approved by a second analyst.
await go('/monitoring/pack');
await start('pack'); await caption(C.pack); await hold(1600);
// The charge-off figure carries its source: clicking it opens the servicer report page.
await page.getByRole('button', { name: /140,112\.77/ }).first().click();
await hold(READ_MS - 600);
await page.getByRole('button', { name: 'Approve and send' }).click();
await page.getByRole('alert').waitFor();
await caption(C.approve); await hold(2400);
await page.getByLabel('Act as second analyst').check();
await hold(600);
await page.getByRole('button', { name: 'Approve and send' }).click();
await page.getByText('Approved and sent').first().waitFor();
await hold(2600); await end();

// The other two packs, approved the same way.
for (const facility of ['northmoor', 'kestrel']) await act('approve-pack', 'approver', { facility });

// Results.
await go('/monitoring/results');
await page.getByText('Material issues missed').waitFor();
await start('results'); await caption(C.results); await hold(READ_MS + 1600); await end();

await localGo('monitoring-closing');
await hold(2500);
await start('closing'); await hold(9500); await end();

await context.request.post(BASE + '/api/monitoring/session/reset');
const video = await page.video().path();
await context.close();
await browser.close();
fs.writeFileSync('segments.json', JSON.stringify({ video, segments }, null, 2));
const total = segments.reduce((sum, s) => sum + s.end - s.start, 0);
log(`done: ${segments.length} scenes, about ${total.toFixed(0)}s of content`);
