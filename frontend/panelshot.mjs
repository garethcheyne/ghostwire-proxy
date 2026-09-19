import { chromium } from 'playwright'
const b = await chromium.launch()
const ctx = await b.newContext({ viewport:{width:1440,height:1100} })
await ctx.addInitScript((t)=>{try{localStorage.setItem('access_token',t);localStorage.setItem('refresh_token',t)}catch{}}, process.env.TOKEN)
const p = await ctx.newPage()
await p.goto('http://localhost:88/dashboard/containers', {waitUntil:'networkidle', timeout:90000})
await p.waitForFunction(()=>document.body.innerText.includes('Automatic OS package updates'), {timeout:120000}).catch(()=>{})
await p.waitForTimeout(2500)
const info = await p.evaluate(() => {
  const has = (t) => document.body.innerText.includes(t)
  const toggles = [...document.querySelectorAll('input[type=checkbox]')].length
  return {
    panelPresent: has('Automatic OS package updates'),
    scheduleField: has('Schedule (cron, UTC)'),
    exclusions: has('Never update in place'),
    updateAllButton: has('Update all now'),
    securityOnly: has('Security updates only'),
    checkboxes: toggles,
  }
})
console.log(JSON.stringify(info, null, 2))
const sec = p.locator('div').filter({ hasText: /^Automatic OS package updates/ }).first()
const card = p.locator('div.rounded-xl').filter({ has: p.locator('h2:has-text("Automatic OS package updates")') }).first()
if (await card.count()) await card.screenshot({ path: process.env.OUT + '/autoupdate-panel.png' })
await b.close()
