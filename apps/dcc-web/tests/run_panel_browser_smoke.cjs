const { chromium } = require('playwright');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { setTimeout: delay } = require('node:timers/promises');

async function waitForFixture(port) {
  for (let attempt = 0; attempt < 60; attempt++) {
    try {
      const response = await fetch('http://127.0.0.1:' + port + '/login',
        { signal: AbortSignal.timeout(2000) });
      if (response.ok) return;
    } catch {}
    await delay(500);
  }
  throw new Error('Panel fixture did not start on port ' + port);
}

(async () => {
  await Promise.all([waitForFixture(18878), waitForFixture(18879)]);
  const source = readFileSync(join(__dirname, 'panel_browser_smoke.js'), 'utf8');
  const smoke = new Function('return (' + source + '\n)')();
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    console.log(JSON.stringify(await smoke(page)));
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
