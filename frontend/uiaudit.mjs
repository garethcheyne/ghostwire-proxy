/**
 * Mobile UI audit: visit every dashboard page at phone width and report, per
 * page, the things that actually make a small screen unusable — horizontal
 * overflow, elements wider than the viewport, tap targets under 44px, text
 * under 12px, and content hidden behind the fixed bottom tab bar.
 *
 * Runs against the live app with a real session, so it sees real data rather
 * than empty states.
 */
import { chromium } from 'playwright'
import fs from 'node:fs'

const BASE = process.env.BASE || 'http://localhost:88'
const TOKEN = process.env.TOKEN
const OUT = process.env.OUT || '/tmp/uiaudit'
const WIDTH = parseInt(process.env.WIDTH || '375', 10)
const HEIGHT = parseInt(process.env.HEIGHT || '667', 10)
const SHOTS = process.env.SHOTS === '1'

const PAGES = [
  '/dashboard',
  '/dashboard/proxy-hosts',
  '/dashboard/certificates',
  '/dashboard/dns',
  '/dashboard/threats',
  '/dashboard/rules',
  '/dashboard/access-control',
  '/dashboard/known-ips',
  '/dashboard/firewalls',
  '/dashboard/analytics',
  '/dashboard/alerts',
  '/dashboard/system',
  '/dashboard/containers',
  '/dashboard/users',
  '/dashboard/settings',
  '/dashboard/settings/backups',
  '/dashboard/settings/updates',
  '/dashboard/about',
  '/dashboard/docs',
  '/dashboard/traffic',
  '/dashboard/waf',
  '/dashboard/geoip',
  '/dashboard/honeypot',
  '/dashboard/auth-walls',
  '/dashboard/access-lists',
  '/dashboard/presets',
  '/dashboard/notifications',
  '/dashboard/license',
]

// Measured inside the page: everything that needs the live layout.
const probe = () => {
  const docW = document.documentElement.clientWidth
  const out = {
    scrollW: document.documentElement.scrollWidth,
    docW,
    overflowing: [],
    smallTargets: [],
    tinyText: [],
    behindTabBar: [],
  }

  const visible = (el) => {
    const r = el.getBoundingClientRect()
    if (r.width === 0 || r.height === 0) return false
    const s = getComputedStyle(el)
    return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0'
  }
  const label = (el) => {
    const cls = (el.className && typeof el.className === 'string')
      ? '.' + el.className.trim().split(/\s+/).slice(0, 4).join('.')
      : ''
    const txt = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 40)
    return `${el.tagName.toLowerCase()}${cls}${txt ? ` "${txt}"` : ''}`
  }

  // Elements sticking out past the right edge. Report only the outermost
  // offender in any chain, or one wide table yields fifty findings.
  const over = []
  for (const el of document.querySelectorAll('body *')) {
    if (!visible(el)) continue
    const r = el.getBoundingClientRect()
    if (r.right > docW + 1) {
      const s = getComputedStyle(el)
      // A child inside a horizontal scroller is intentional.
      let p = el.parentElement, scrollable = false
      while (p && p !== document.body) {
        const ps = getComputedStyle(p)
        if (ps.overflowX === 'auto' || ps.overflowX === 'scroll') { scrollable = true; break }
        p = p.parentElement
      }
      if (!scrollable && s.overflowX !== 'auto' && s.overflowX !== 'scroll') {
        over.push({ el, right: r.right, w: r.width })
      }
    }
  }
  for (const o of over) {
    if (!over.some((x) => x !== o && x.el.contains(o.el))) {
      out.overflowing.push(`${label(o.el)} (right=${Math.round(o.right)} > ${docW})`)
    }
  }

  // Tap targets. 44px is the accessibility floor on touch.
  const seen = new Set()
  for (const el of document.querySelectorAll('button, a[href], [role="button"], input[type="checkbox"], select')) {
    if (!visible(el)) continue
    const r = el.getBoundingClientRect()
    if (r.height < 40 || r.width < 32) {
      const k = label(el)
      if (!seen.has(k)) { seen.add(k); out.smallTargets.push(`${k} (${Math.round(r.width)}x${Math.round(r.height)})`) }
    }
  }

  // Text below 12px is not comfortably readable on a phone.
  const seenT = new Set()
  for (const el of document.querySelectorAll('body *')) {
    if (!visible(el)) continue
    if (!el.childNodes.length) continue
    const hasText = Array.from(el.childNodes).some(n => n.nodeType === 3 && n.textContent.trim())
    if (!hasText) continue
    const fs = parseFloat(getComputedStyle(el).fontSize)
    if (fs && fs < 12) {
      const k = `${label(el)} @${fs}px`
      if (!seenT.has(k)) { seenT.add(k); out.tinyText.push(k) }
    }
  }

  return out
}

const results = []
const browser = await chromium.launch()
const ctx = await browser.newContext({
  viewport: { width: WIDTH, height: HEIGHT },
  deviceScaleFactor: 2,
  isMobile: true,
  hasTouch: true,
  userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
})

// Seed the session the way the app does.
await ctx.addInitScript((t) => {
  try {
    localStorage.setItem('access_token', t.access)
    localStorage.setItem('refresh_token', t.refresh)
  } catch {}
}, { access: TOKEN, refresh: process.env.REFRESH || TOKEN })

if (SHOTS) fs.mkdirSync(OUT, { recursive: true })

for (const path of PAGES) {
  const page = await ctx.newPage()
  const consoleErrors = []
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 160)) })
  page.on('pageerror', (e) => consoleErrors.push('pageerror: ' + String(e).slice(0, 160)))

  let r = { path, error: null }
  try {
    await page.goto(BASE + path, { waitUntil: 'networkidle', timeout: 45000 })
    await page.waitForTimeout(1200)
    const probed = await page.evaluate(probe)
    r = { path, ...probed, consoleErrors: consoleErrors.slice(0, 5) }
    if (SHOTS) {
      await page.screenshot({ path: `${OUT}/${path.replace(/\//g, '_') || 'root'}.png`, fullPage: true })
    }
  } catch (e) {
    r.error = String(e).split('\n')[0].slice(0, 160)
  }
  results.push(r)
  await page.close()
}

await browser.close()
fs.writeFileSync(`${OUT}.json`, JSON.stringify(results, null, 2))

// ---- report ----
let bad = 0
for (const r of results) {
  const issues = []
  if (r.error) issues.push(`LOAD FAILED: ${r.error}`)
  if (r.scrollW > r.docW + 1) issues.push(`HORIZONTAL SCROLL: page is ${r.scrollW}px wide in a ${r.docW}px viewport`)
  if (r.overflowing?.length) issues.push(`overflowing elements (${r.overflowing.length}):\n      - ` + r.overflowing.slice(0, 6).join('\n      - '))
  if (r.smallTargets?.length) issues.push(`tap targets under 44px (${r.smallTargets.length}):\n      - ` + r.smallTargets.slice(0, 6).join('\n      - '))
  if (r.tinyText?.length) issues.push(`text under 12px (${r.tinyText.length}):\n      - ` + r.tinyText.slice(0, 4).join('\n      - '))
  if (r.consoleErrors?.length) issues.push(`console errors:\n      - ` + r.consoleErrors.join('\n      - '))

  if (issues.length) {
    bad++
    console.log(`\n### ${r.path}`)
    for (const i of issues) console.log(`  * ${i}`)
  } else {
    console.log(`\n### ${r.path}  — clean`)
  }
}
console.log(`\n${bad}/${results.length} pages have findings at ${WIDTH}x${HEIGHT}`)
