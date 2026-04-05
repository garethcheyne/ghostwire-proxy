import { chromium } from 'playwright';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { readFileSync } from 'fs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const outDir = join(__dirname, '..', 'frontend', 'public', 'screenshots');

// Read creds from .env
const env = {};
for (const line of readFileSync(join(__dirname, '..', '.env'), 'utf8').split('\n')) {
  const m = line.match(/^([A-Z_]+)=(.*)$/);
  if (m) env[m[1]] = m[2];
}

const BASE = process.env.SCREENSHOT_URL || env.SCREENSHOT_URL || 'http://192.168.0.13:88';
const API  = process.env.SCREENSHOT_API_URL || env.SCREENSHOT_API_URL || 'http://192.168.0.13:8089';
const EMAIL = process.env.SCREENSHOT_EMAIL || env.SCREENSHOT_EMAIL;
const PASS  = process.env.SCREENSHOT_PASSWORD || env.SCREENSHOT_PASSWORD;

/** Log in via the API and return the access token */
async function getToken() {
  const res = await fetch(`${API}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: EMAIL, password: PASS }),
  });
  if (!res.ok) throw new Error(`Login failed: ${res.status} ${await res.text()}`);
  const data = await res.json();
  return data.access_token;
}

/** Inject the JWT into the browser context so the Next.js app treats us as logged-in */
async function injectAuth(context, token) {
  await context.addCookies([
    { name: 'access_token', value: token, domain: new URL(BASE).hostname, path: '/' },
  ]);
  // Also set localStorage token on every page
  await context.addInitScript((tok) => {
    localStorage.setItem('access_token', tok);
  }, token);
}

async function main() {
  console.log(`Logging in as ${EMAIL} …`);
  const token = await getToken();
  console.log('✓ Authenticated');

  const browser = await chromium.launch({ headless: true });

  // ── Desktop (wide) screenshots — 1920×1080 ─────────────────
  const desktopCtx = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
  });

  // Unauthenticated — login page
  const dLogin = await desktopCtx.newPage();
  await dLogin.goto(`${BASE}/auth/login`, { waitUntil: 'networkidle' });
  await dLogin.waitForTimeout(2000);
  await dLogin.screenshot({ path: join(outDir, 'login-wide.png'), fullPage: false });
  console.log('✓ login-wide.png');
  await dLogin.close();

  // Inject auth and take dashboard screenshot
  await injectAuth(desktopCtx, token);
  const dDash = await desktopCtx.newPage();
  await dDash.goto(`${BASE}/dashboard/system`, { waitUntil: 'networkidle' });
  await dDash.waitForTimeout(3000);
  await dDash.screenshot({ path: join(outDir, 'dashboard-wide.png'), fullPage: false });
  console.log('✓ dashboard-wide.png');
  await desktopCtx.close();

  // ── Mobile (narrow) screenshots — 390×844 ──────────────────
  const mobileCtx = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    userAgent:
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
  });

  // Unauthenticated — login page
  const mLogin = await mobileCtx.newPage();
  await mLogin.goto(`${BASE}/auth/login`, { waitUntil: 'networkidle' });
  await mLogin.waitForTimeout(2000);
  await mLogin.screenshot({ path: join(outDir, 'login-narrow.png'), fullPage: false });
  console.log('✓ login-narrow.png');
  await mLogin.close();

  // Inject auth and take dashboard screenshot
  await injectAuth(mobileCtx, token);
  const mDash = await mobileCtx.newPage();
  await mDash.goto(`${BASE}/dashboard/system`, { waitUntil: 'networkidle' });
  await mDash.waitForTimeout(3000);
  await mDash.screenshot({ path: join(outDir, 'dashboard-narrow.png'), fullPage: false });
  console.log('✓ dashboard-narrow.png');
  await mobileCtx.close();

  await browser.close();
  console.log('\nAll screenshots saved to frontend/public/screenshots/');
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
