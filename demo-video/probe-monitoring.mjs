// Walks the monitoring cycle once, saving a screenshot after each step, and fails on any API error.
import fs from 'node:fs';
import { createRequire } from 'node:module';

process.chdir(import.meta.dirname);
const require = createRequire('C:/Users/swarupd/demo/Kinective/atlas-agent-platform/package.json');
const { chromium } = require('playwright');

const BASE = process.env.APP || 'http://127.0.0.1:5187';
const OUT = 'probe-monitoring';
fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(OUT);
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1920, height: 1080 }, colorScheme: 'light', locale: 'en-GB' });
const page = await context.newPage();
const problems = [];
page.on('response', async (r) => { if (r.url().includes('/api') && !r.ok() && r.status() !== 409) problems.push(`API ${r.status()} ${r.url()}`); });
page.on('pageerror', (e) => problems.push(`page error: ${e.message}`));
page.on('console', (m) => { if (m.type() === 'error') problems.push(`console: ${m.text()}`); });
let n = 0;
const shot = async (name) => { await page.waitForTimeout(900); await page.screenshot({ path: `${OUT}/${String(n++).padStart(2, '0')}-${name}.png` }); console.log('shot', name); };
const step = (name) => page.getByRole('navigation', { name: 'Monitoring steps' }).getByRole('link', { name }).click();

try {
  await context.request.post(BASE + '/api/monitoring/session/reset');
  await page.goto(BASE + '/monitoring');
  await page.getByRole('heading', { name: 'Portfolio monitor' }).waitFor({ timeout: 30000 });
  await shot('portfolio');
  await step('Submissions');
  await page.getByRole('heading', { name: 'Submission tracker' }).waitFor();
  await shot('submissions');
  await page.getByRole('button', { name: 'View chase' }).click();
  await shot('chase');
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Confirm mapping' }).click();
  await step('Reconcile');
  await page.locator('[data-highlight]').first().waitFor({ timeout: 20000 });
  await shot('reconciliation');
  await page.getByRole('button', { name: /Open the 27 loans/ }).click();
  await shot('missing-loans');
  await page.keyboard.press('Escape');
  await step('Terms');
  await shot('terms-may');
  await page.getByRole('radio', { name: 'June 2026' }).click();
  await shot('terms-june');
  await step('Covenants');
  await page.getByRole('button', { name: 'Run what-if for June' }).click();
  await page.getByRole('status').filter({ hasText: 'With June' }).waitFor();
  await shot('covenants-northmoor');
  await page.getByRole('tab', { name: /Bramble/ }).click();
  await shot('covenants-bramble');
  await page.getByRole('tab', { name: /Kestrel/ }).click();
  await shot('covenants-kestrel');
  await step('Collateral');
  await page.getByRole('button', { name: 'Open both tape rows' }).click();
  await shot('collateral');
  await step('Triage');
  await page.getByRole('heading', { name: 'Triage' }).waitFor();
  await shot('triage');
  for (let i = 0; i < 9; i++) {
    const confirm = page.getByRole('button', { name: /^Confirm/ });
    if (!(await confirm.count())) break;
    await confirm.first().click();
    await page.waitForTimeout(400);
  }
  await shot('triage-done');
  await step('Lender pack');
  await shot('pack-bramble');
  await page.getByRole('button', { name: 'Approve and send' }).click();
  await page.getByRole('alert').waitFor();
  await shot('pack-self-approval-refused');
  await page.getByLabel('Act as second analyst').check();
  for (const name of ['Bramble Auto Receivables I', 'Northmoor Motor Credit Trust', 'Kestrel Credit Fund III']) {
    await page.getByRole('tab', { name: new RegExp(name) }).click();
    await page.getByRole('button', { name: 'Approve and send' }).click();
    await page.getByText('Approved and sent').first().waitFor();
  }
  await shot('pack-approved');
  await step('Scorecard');
  await page.getByText('Material issues missed').waitFor();
  await shot('scorecard');
} catch (e) {
  console.error(e);
  await page.screenshot({ path: `${OUT}/fail.png` });
  process.exitCode = 1;
} finally {
  console.log(problems.length ? problems.join('\n') : 'no API or page errors');
  await browser.close();
}
