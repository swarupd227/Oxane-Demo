// Records the onboarding walkthrough against the production build with Playwright. Each scene is framed by
// a magenta (start) and cyan (end) flash so assemble.mjs can cut out page loads and waits.
// Same pipeline as the Migration Studio video. Run serve.mjs first.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

process.chdir(import.meta.dirname);
const require = createRequire('C:/Users/swarupd/demo/Kinective/atlas-agent-platform/package.json');
const { chromium } = require('playwright');

const BASE = process.env.APP || 'http://127.0.0.1:5187';
const C = JSON.parse(fs.readFileSync('captions.json', 'utf8'));
const READ_MS = 4600; // Captions are one short sentence, so they need less time than before.
// Recorded 1:1 at 1920x1080: the app is a centred column, so a wider page would only shrink its text.
const WIDTH = 1920;
const HEIGHT = 1080;
const BAND = 190;
const APP = HEIGHT - BAND;
fs.rmSync('rec', { recursive: true, force: true });

const browser = await chromium.launch({ headless: true });

// Warm the workbench and the PDF viewer off camera, so nothing waits on a cold server during the take.
{
  const warm = await browser.newContext({ viewport: { width: WIDTH, height: APP } });
  await warm.request.post(BASE + '/api/session/reset');
  const p = await warm.newPage();
  await p.goto(BASE + '/');
  await p.getByRole('button', { name: 'Start onboarding' }).click();
  await p.getByRole('button', { name: 'Load sandbox pack' }).click();
  await p.getByText('Expected but not received').waitFor({ timeout: 120000 });
  await p.getByRole('button', { name: 'Review facility terms' }).click();
  await p.locator('[data-highlight]').first().waitFor({ timeout: 120000 });
  await warm.request.post(BASE + '/api/session/reset');
  await warm.close();
}

const context = await browser.newContext({
  viewport: { width: WIDTH, height: HEIGHT }, deviceScaleFactor: 1, colorScheme: 'light', locale: 'en-GB',
  recordVideo: { dir: 'rec', size: { width: 1920, height: 1080 } },
});
// The app is held above a solid caption strip. Panels sized from 100vh are re-based on the app's height,
// or they run under the strip and clicks below them scroll the page.
const LAYOUT = `
  html, body, #root { height: ${APP}px !important; max-height: ${APP}px !important; overflow: hidden; }
  .min-h-screen { min-height: ${APP}px !important; }
  [role="dialog"] { max-height: ${APP}px !important; }
  ${[39, 19, 17].map((rem) => `[class*="100vh-${rem}rem"] { max-height: calc(${APP}px - ${rem}rem) !important; }`).join('\n  ')}`;
const page = await context.newPage();
const t0 = Date.now();
const secs = () => (Date.now() - t0) / 1000;
const segments = [];
let current = null;
const log = (s) => console.log(`[${secs().toFixed(1)}] ${s}`);
// Reading time: long holds are stretched so a two-line caption can be read at an easy pace.
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
  await page.getByRole('navigation', { name: 'Onboarding steps' }).waitFor({ timeout: 60000 });
  await hold(1500);
}
async function localGo(name) {
  await page.goto(pathToFileURL(path.resolve('pages', `${name}.html`)).href);
  await hold(300);
}
// A yellow ring that points the viewer at what the caption describes.
const spotlight = (locator, on) => locator.evaluate((el, show) => {
  el.style.transition = 'box-shadow .4s ease';
  el.style.boxShadow = show ? '0 0 0 3px #FFDD00, 0 0 0 7px rgba(255, 221, 0, .25)' : '';
}, on);
const tab = (name) => page.getByRole('navigation', { name: 'Onboarding steps' }).getByRole('link', { name });
const term = (name) => page.locator('tbody').getByRole('button', { name, exact: true });

const onFail = async (e) => {
  console.error(e);
  await page.screenshot({ path: 'fail.png' }).catch(() => {});
  process.exit(1);
};
process.on('unhandledRejection', onFail);
process.on('uncaughtException', onFail);

await context.request.post(BASE + '/api/session/reset');

// ---------------------------------------------------------------- scenes --
await localGo('opening');
await hold(2500);
await start('opening'); await hold(7500); await end();

// The deal and the analyst's mandate.
await go('/');
await page.getByRole('button', { name: 'Start onboarding' }).waitFor();
await start('deal'); await caption(C.deal); await hold(READ_MS); await end();

// Intake: the pack is identified and the missing schedule is found.
await page.getByRole('button', { name: 'Start onboarding' }).click();
await page.getByRole('button', { name: 'Load sandbox pack' }).waitFor();
await page.addStyleTag({ content: LAYOUT });
await start('intake'); await caption(C.intake); await hold(1500);
await page.getByRole('button', { name: 'Load sandbox pack' }).click();
await page.getByText('Expected but not received').waitFor({ timeout: 30000 });
await hold(READ_MS - 1000); await end();

// Terms, each with its source.
await page.getByRole('button', { name: 'Review facility terms' }).click();
await page.locator('[data-highlight]').first().waitFor({ timeout: 60000 });
await hold(600);
await start('terms'); await caption(C.terms); await hold(READ_MS - 600);
await term('Facility limit').click();
await page.getByRole('img', { name: /page 61/ }).waitFor({ timeout: 30000 });
await page.locator('[data-highlight]').first().waitFor({ timeout: 30000 });
await caption(C.facility); await hold(READ_MS);
await page.keyboard.press('a'); // The approve shortcut: clicking the button would scroll the page.
await term('Advance rate').click();
await page.locator('[data-highlight]').first().waitFor({ timeout: 30000 });
const grounding = page.getByRole('group', { name: 'Ontology grounding' });
await spotlight(grounding, true);
await caption(C.ontology); await hold(READ_MS + 600);
await spotlight(grounding, false);
await caption(C.amended); await hold(READ_MS);
await page.keyboard.press('a'); // The approve shortcut: clicking the button would scroll the page.
await hold(600);
await caption(C.bulk); await hold(1400);
await page.getByRole('button', { name: /Approve high-confidence Tier 2 and 3/ }).click();
await page.getByText(/2[0-9] of 26 approved/).waitFor();
await hold(2800); await end();

// Rules drafted by the AI, accepted by the engine, and a change held for a second analyst.
await go('/rules');
const ruleConcepts = page.getByLabel('Facility Ontology concepts');
await start('rules'); await caption(C.rules); await hold(600);
for (const index of [0, 1]) await spotlight(ruleConcepts.nth(index), true);
await hold(READ_MS);
for (const index of [0, 1]) await spotlight(ruleConcepts.nth(index), false);
await page.getByRole('button', { name: 'Edit E5' }).click();
await page.getByRole('spinbutton').fill('70000');
await page.getByText('Loans becoming ineligible').waitFor();
await caption(C.ruleEdit); await hold(2400);
await page.getByRole('dialog').getByRole('textbox').pressSequentially('Stress test for the April tape', { delay: 35 });
await hold(500);
await page.getByRole('button', { name: 'Save as pending' }).click();
await page.getByText('Pending rule set v2:').waitFor();
await hold(2000); await end();

// Mapping.
await go('/mapping');
await page.getByText('38 tape columns mapped').waitFor();
const columnConcepts = page.locator('[title="Facility Ontology concept"]');
await start('mapping'); await caption(C.mapping); await hold(600);
for (const index of [0, 1, 2]) await spotlight(columnConcepts.nth(index), true);
await hold(READ_MS - 400);
for (const index of [0, 1, 2]) await spotlight(columnConcepts.nth(index), false);
await page.getByRole('button', { name: /Accept remaining/ }).click();
await hold(2600); await end();

// Validation by the deterministic engine.
await go('/validation');
await start('validation'); await caption(C.validation); await hold(1800);
await page.getByRole('button', { name: 'Run the April tape' }).click();
await page.getByText('Eligible pool bridge').waitFor({ timeout: 30000 });
await hold(READ_MS - 1800);
await caption(C.bridge); await hold(READ_MS);
await page.getByRole('button', { name: /Duplicate VINs/ }).click();
await page.getByText('Possible double pledging.').waitFor();
await page.getByText('Possible double pledging.').scrollIntoViewIfNeeded();
await caption(C.drill); await hold(3800); await end();

// The exception queue, where people decide.
await go('/exceptions');
await page.getByText('3 open of 10').waitFor();
await start('exceptions'); await caption(C.queue); await hold(1600);
await page.getByRole('button', { name: /41 loans over 30 days/ }).click();
await hold(1400);
await page.getByRole('button', { name: 'Draft query' }).click();
await hold(1600);
await page.getByRole('button', { name: 'Log query' }).click();
await hold(700);
await page.getByRole('button', { name: /6 loans share 3 VINs/ }).click();
await hold(1300);
await page.getByRole('button', { name: 'Escalate to credit' }).click();
await hold(700);
await page.getByRole('button', { name: /Sunrise Motors/ }).click();
await hold(1300);
await page.getByRole('button', { name: 'Accept', exact: true }).click();
await page.getByText('Borrowing base recalculated').waitFor({ timeout: 30000 });
await caption(C.sunrise); await hold(READ_MS + 1200); await end();

// Approval under two-person control.
await go('/approve');
await page.getByText('You prepared this case').waitFor();
await start('approve'); await caption(C.approve); await hold(READ_MS - 800);
await page.getByRole('button', { name: 'Second analyst' }).click();
await page.getByRole('heading', { name: 'Change summary' }).waitFor();
await caption(C.reviewer); await hold(2600);
await page.getByLabel('Decision reason').scrollIntoViewIfNeeded();
await page.getByLabel('Decision reason').pressSequentially("The agreement's threshold stands", { delay: 30 });
await page.getByRole('button', { name: 'Decline' }).click();
await hold(900);
await page.getByRole('checkbox').check();
await hold(700);
await page.getByRole('button', { name: /Approve with \d open items/ }).click();
await page.getByText('Approved with open items').first().waitFor();
await page.getByRole('link', { name: 'Download load file' }).scrollIntoViewIfNeeded();
await hold(800);
await caption(C.approved); await hold(READ_MS - 800); await end();

// Results, measured and not forecast.
await go('/results');
await page.getByText('Exceptions found', { exact: true }).waitFor();
await start('results'); await caption(C.results); await hold(READ_MS + 1200); await end();

await localGo('closing');
await hold(2500);
await start('closing'); await hold(9500); await end();

await context.request.post(BASE + '/api/session/reset');
const video = await page.video().path();
await context.close();
await browser.close();
fs.writeFileSync('segments.json', JSON.stringify({ video, segments }, null, 2));
const total = segments.reduce((sum, s) => sum + s.end - s.start, 0);
log(`done: ${segments.length} scenes, about ${total.toFixed(0)}s of content`);
