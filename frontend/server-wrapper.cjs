// Starts the Next.js standalone server (server.js) after making the client
// address trustworthy.
//
// The admin UI is reached both directly (port 88) and through the OpenResty
// proxy. Forwarding headers (X-Forwarded-For, X-Real-IP, CF-Connecting-IP) are
// only believed when the TCP peer is a trusted proxy (TRUSTED_PROXIES: IPs,
// CIDRs or host names; default loopback + the ghostwire-proxy-nginx container).
// Every request then carries exactly one resolved address in X-Real-IP and
// X-Forwarded-For, which is what Better Auth's sign-in rate limit and the
// audit log read, and what the API receives through the rewrites.
'use strict'

const http = require('http')
const net = require('net')
const dns = require('dns')

const DEFAULT_TRUSTED = '127.0.0.1,::1,ghostwire-proxy-nginx'
const REFRESH_MS = 60_000

function parseIp(value) {
  if (!value) return null
  let v = String(value).trim().replace(/^"|"$/g, '')
  if (v.startsWith('[')) v = v.slice(1).split(']')[0]
  else if ((v.match(/:/g) || []).length === 1) v = v.split(':')[0]
  if (v.toLowerCase().startsWith('::ffff:') && net.isIPv4(v.slice(7))) v = v.slice(7)
  return net.isIP(v) ? v : null
}

function buildBlockList(spec, resolved) {
  const list = new net.BlockList()
  const names = []
  for (const raw of spec.split(',').map((s) => s.trim()).filter(Boolean)) {
    const [addr, bits] = raw.split('/')
    const family = net.isIP(addr)
    if (family) {
      const type = family === 6 ? 'ipv6' : 'ipv4'
      if (bits !== undefined) list.addSubnet(addr, Number(bits), type)
      else list.addAddress(addr, type)
    } else {
      names.push(raw)
    }
  }
  for (const addr of resolved) list.addAddress(addr, net.isIP(addr) === 6 ? 'ipv6' : 'ipv4')
  return { list, names }
}

function createTrusted(spec = process.env.TRUSTED_PROXIES || DEFAULT_TRUSTED) {
  let state = buildBlockList(spec, [])
  const trusted = {
    isTrusted(ip) {
      if (!ip) return false
      return state.list.check(ip, net.isIP(ip) === 6 ? 'ipv6' : 'ipv4')
    },
    async refresh() {
      const resolved = []
      for (const name of state.names) {
        try {
          const addrs = await dns.promises.lookup(name, { all: true })
          for (const a of addrs) resolved.push(a.address)
        } catch {
          // not resolvable (yet): that name is simply not trusted
        }
      }
      state = buildBlockList(spec, resolved)
    },
    clientIp(peer, forwardedFor, realIp) {
      const peerIp = parseIp(peer)
      if (!peerIp) return null
      if (!trusted.isTrusted(peerIp)) return peerIp
      const hops = String(forwardedFor || '')
        .split(',')
        .map((h) => h.trim())
        .filter(Boolean)
      if (hops.length) {
        let last = null
        for (let i = hops.length - 1; i >= 0; i--) {
          const ip = parseIp(hops[i])
          if (!ip) break
          last = ip
          if (!trusted.isTrusted(ip)) return ip
        }
        return last || peerIp
      }
      return parseIp(realIp) || peerIp
    },
  }
  return trusted
}

function sanitize(trusted, req) {
  const h = req.headers
  const ip = trusted.clientIp(req.socket && req.socket.remoteAddress, h['x-forwarded-for'], h['x-real-ip']) || ''
  delete h['cf-connecting-ip']
  delete h['true-client-ip']
  delete h['x-client-ip']
  if (ip) {
    h['x-real-ip'] = ip
    h['x-forwarded-for'] = ip
  } else {
    delete h['x-real-ip']
    delete h['x-forwarded-for']
  }
}

function install(trusted) {
  const emit = http.Server.prototype.emit
  http.Server.prototype.emit = function (event, req, ...rest) {
    if (event === 'request' && req && req.headers) sanitize(trusted, req)
    return emit.call(this, event, req, ...rest)
  }
}

module.exports = { createTrusted, sanitize, parseIp }

if (require.main === module) {
  const trusted = createTrusted()
  install(trusted)
  trusted.refresh().finally(() => {
    setInterval(() => trusted.refresh(), REFRESH_MS).unref()
    require('./server.js')
  })
}
