import { chromium } from 'playwright';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const outDir = join(__dirname, '..', 'frontend', 'public', 'screenshots');

const BASE = 'http://192.168.0.13';

async function main() {
  const browser = await chromium.launch({ headless: true });

  // ── Desktop (wide) screenshots ──────────────────────────────
  const desktopCtx = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
  });
  const dPage = await desktopCtx.newPage();

  // Login page – wide
  await dPage.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
  await dPage.waitForTimeout(1000);
  await dPage.screenshot({ path: join(outDir, 'login-wide.png'), fullPage: false });
  console.log('✓ login-wide.png');

  // Dashboard – wide  (need to login first)
  // Try navigating to dashboard – if redirected to login, fill creds
  await dPage.goto(`${BASE}/dashboard/system`, { waitUntil: 'networkidle' });
  await dPage.waitForTimeout(2000);
  await dPage.screenshot({ path: join(outDir, 'dashboard-wide.png'), fullPage: false });
  console.log('✓ dashboard-wide.png');

  await desktopCtx.close();

  // ── Mobile (narrow) screenshots ─────────────────────────────
  const mobileCtx = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    userAgent:
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
  });
  const mPage = await mobileCtx.newPage();

  // Login page – narrow
  await mPage.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
  await mPage.waitForTimeout(1000);
  await mPage.screenshot({ path: join(outDir, 'login-narrow.png'), fullPage: false });
  console.log('✓ login-narrow.png');

  // Dashboard – narrow
  await mPage.goto(`${BASE}/dashboard/system`, { waitUntil: 'networkidle' });
  await mPage.waitForTimeout(2000);
  await mPage.screenshot({ path: join(outDir, 'dashboard-narrow.png'), fullPage: false });
  console.log('✓ dashboard-narrow.png');

  await mobileCtx.close();
  await browser.close();
  console.log('\nAll screenshots saved to frontend/public/screenshots/');
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
