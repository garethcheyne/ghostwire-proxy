const { chromium } = require('playwright');

// ─── Configuration ───────────────────────────────────────────────────────────
const BASE_URL = process.env.SCREENSHOT_URL || 'http://localhost:88';
const API_URL = process.env.SCREENSHOT_API_URL || 'http://localhost:8089';
const EMAIL = process.env.SCREENSHOT_EMAIL || '';
const PASSWORD = process.env.SCREENSHOT_PASSWORD || '';
const VIEWPORT = { width: 1440, height: 900 };
const OUTPUT_DIR = '../../docs/ghostwire-proxy/_img';
const WAIT_MS = 2500; // wait for page data to load

// ─── Pages to Screenshot ─────────────────────────────────────────────────────
const PAGES = [
  // Auth
  { path: '/auth/login',             name: 'login',              needsAuth: false },

  // Overview
  { path: '/dashboard',              name: 'dashboard' },

  // Proxy
  { path: '/dashboard/proxy-hosts',  name: 'proxy-hosts' },
  { path: '/dashboard/certificates', name: 'certificates' },
  { path: '/dashboard/dns',          name: 'dns' },

  // Security - Threats (includes honeypot)
  { path: '/dashboard/threats',      name: 'threats' },
  { path: '/dashboard/threats',      name: 'threats-honeypot',   tab: 'honeypot', wait: 3000 },
  { path: '/dashboard/threats',      name: 'threats-traps',      tab: 'traps', wait: 3000 },

  // Security - Rules (WAF, GeoIP, Rate Limits, Presets)
  { path: '/dashboard/rules',        name: 'rules-waf' },
  { path: '/dashboard/rules',        name: 'rules-geoip',        tab: 'geoip', wait: 3000 },
  { path: '/dashboard/rules',        name: 'rules-rate-limits',  tab: 'rate-limits', wait: 3000 },
  { path: '/dashboard/rules',        name: 'rules-presets',      tab: 'presets', wait: 4000 },

  // Security - Access Control (Auth Walls, IP Access Lists)
  { path: '/dashboard/access-control', name: 'access-control' },
  { path: '/dashboard/access-control', name: 'access-control-ip-lists', tab: 'ip-lists', wait: 3000 },

  // Security - Firewalls (external firewall sync)
  { path: '/dashboard/firewalls',    name: 'firewalls' },

  // Monitoring - Analytics (includes traffic logs)
  { path: '/dashboard/analytics',    name: 'analytics' },
  { path: '/dashboard/analytics',    name: 'analytics-logs',     tab: 'logs', wait: 4000 },
  { path: '/dashboard/analytics',    name: 'analytics-security', tab: 'security', scroll: true, wait: 4000 },
  { path: '/dashboard/analytics',    name: 'analytics-heatmap',  tab: 'security', scrollTo: 'Threat Origin Heatmap', wait: 6000 },
  { path: '/dashboard/alerts',       name: 'alerts' },
  { path: '/dashboard/system',       name: 'system' },

  // Admin - About (includes license, updates)
  { path: '/dashboard/users',        name: 'users' },
  { path: '/dashboard/settings',     name: 'settings',           wait: 5000, timeout: 60000, waitUntil: 'domcontentloaded' },
  { path: '/dashboard/settings/backups', name: 'settings-backups', wait: 4000 },
  { path: '/dashboard/about',        name: 'about' },
  { path: '/dashboard/about',        name: 'about-license',      tab: 'license', wait: 2000 },
  { path: '/dashboard/about',        name: 'about-updates',      tab: 'updates', wait: 3000 },
];

// ─── Redaction map: data-private type → replacement text ─────────────────────
const REDACT = {
  ip:      '●●●.●●●.●●●.●●●',
  domain:  'example.yourdomain.com',
  email:   'admin@example.com',
  address: 'http://10.0.0.x:8080',
  name:    'Admin User',
  host:    'example.yourdomain.com',
};

/**
 * Walk the DOM and replace text content of every element with a data-private
 * attribute.  Runs inside the browser via page.evaluate().
 */
async function redactPage(pg) {
  await pg.evaluate((map) => {
    document.querySelectorAll('[data-private]').forEach((el) => {
      const type = el.getAttribute('data-private');
      const replacement = map[type];
      if (replacement) {
        // For elements containing only text, set textContent directly
        if (el.childElementCount === 0) {
          el.textContent = replacement;
        } else {
          // Walk text nodes inside (e.g. <span data-private> that wraps icon + text)
          const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
          let node;
          while ((node = walker.nextNode())) {
            const trimmed = node.textContent.trim();
            if (trimmed.length > 0) {
              node.textContent = replacement;
              break; // only replace the first meaningful text node
            }
          }
        }
      }
    });
  }, REDACT);
}

// ─── Main ────────────────────────────────────────────────────────────────────
(async () => {
  const fs = require('fs');
  const path = require('path');

  // Ensure output directory exists
  const outDir = path.resolve(__dirname, OUTPUT_DIR);
  fs.mkdirSync(outDir, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    colorScheme: 'dark',
    deviceScaleFactor: 1,
  });

  const page = await context.newPage();

  // ── Login via API then inject token ──────────────────────────────────────
  console.log('Logging in via API...');
  let accessToken, refreshToken;
  try {
    const http = require('http');
    const loginData = JSON.stringify({ email: EMAIL, password: PASSWORD });
    const tokenData = await new Promise((resolve, reject) => {
      const req = http.request(`${API_URL}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(loginData) },
      }, (res) => {
        let body = '';
        res.on('data', (chunk) => body += chunk);
        res.on('end', () => {
          if (res.statusCode === 200) resolve(JSON.parse(body));
          else reject(new Error(`Login failed: ${res.statusCode} ${body}`));
        });
      });
      req.on('error', reject);
      req.write(loginData);
      req.end();
    });
    accessToken = tokenData.access_token;
    refreshToken = tokenData.refresh_token;
    console.log('Login successful via API');
  } catch (err) {
    console.error(`Login failed: ${err.message}`);
    console.log('Tip: Set SCREENSHOT_EMAIL and SCREENSHOT_PASSWORD env vars');
    await browser.close();
    process.exit(1);
  }

  // Navigate to app and inject the tokens into localStorage
  await page.goto(`${BASE_URL}/auth/login`, { waitUntil: 'networkidle' });
  await page.evaluate(({ access, refresh }) => {
    localStorage.setItem('access_token', access);
    localStorage.setItem('refresh_token', refresh);
  }, { access: accessToken, refresh: refreshToken });

  // Navigate to dashboard to verify auth
  await page.goto(`${BASE_URL}/dashboard`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(WAIT_MS);
  console.log('Dashboard loaded');

  // ── Capture each page ────────────────────────────────────────────────────
  for (const entry of PAGES) {
    const needsAuth = entry.needsAuth !== false;

    if (!needsAuth) {
      // Open in a fresh context for unauthenticated pages
      const freshContext = await browser.newContext({
        viewport: VIEWPORT,
        colorScheme: 'dark',
        deviceScaleFactor: 1,
      });
      const freshPage = await freshContext.newPage();
      try {
        console.log(`Capturing (no-auth): ${entry.name} → ${entry.path}`);
        await freshPage.goto(`${BASE_URL}${entry.path}`, { waitUntil: 'networkidle' });
        await freshPage.waitForTimeout(WAIT_MS);
        await redactPage(freshPage);
        await freshPage.screenshot({
          path: path.join(outDir, `${entry.name}.png`),
          fullPage: false,
        });
        console.log(`  ✓ ${entry.name}.png`);
      } catch (err) {
        console.error(`  ✗ ${entry.name}: ${err.message}`);
      }
      await freshContext.close();
      continue;
    }

    try {
      console.log(`Capturing: ${entry.name} → ${entry.path}`);
      await page.goto(`${BASE_URL}${entry.path}`, { waitUntil: entry.waitUntil || 'networkidle', timeout: entry.timeout || 30000 });
      await page.waitForTimeout(entry.wait || WAIT_MS);

      // Click a specific tab if requested
      if (entry.tab) {
        const tabButton = page.locator(`[data-value="${entry.tab}"], [value="${entry.tab}"]`).first();
        if (await tabButton.count()) {
          await tabButton.click();
          await page.waitForTimeout(3000);
        }
      }

      // Scroll to bottom if requested (to reveal heatmaps etc.)
      if (entry.scroll) {
        await page.evaluate(() => window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' }));
        await page.waitForTimeout(2000);
      }

      // Scroll to a specific heading so it's visible in the viewport
      if (entry.scrollTo) {
        await page.evaluate((heading) => {
          const els = [...document.querySelectorAll('h3, h2, h4')];
          const target = els.find((el) => el.textContent.includes(heading));
          if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, entry.scrollTo);
        await page.waitForTimeout(3000);
      }

      await redactPage(page);
      await page.screenshot({
        path: path.join(outDir, `${entry.name}.png`),
        fullPage: false,
      });
      console.log(`  ✓ ${entry.name}.png`);
    } catch (err) {
      console.error(`  ✗ ${entry.name}: ${err.message}`);
    }
  }

  await browser.close();
  console.log(`\nDone! Screenshots saved to ${outDir}`);
})();
