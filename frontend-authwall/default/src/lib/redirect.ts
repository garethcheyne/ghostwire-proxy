/**
 * Where the portal may send a visitor after sign-in: only back to this site.
 *
 * Accepts a relative path ("/admin?x=1") or an absolute http(s) URL on this
 * origin. Anything else (other sites, "//evil", "/\evil", "javascript:",
 * control characters) becomes "/". The API applies the same rule.
 */
export function safeRedirect(raw: string | null | undefined, origin: string = window.location.origin): string {
  if (!raw) return '/'
  if (/[\u0000-\u001f\u007f\\]/.test(raw) || raw.trim() !== raw) return '/'
  if (raw.startsWith('//')) return '/'
  let url: URL
  try {
    url = new URL(raw, origin)
  } catch {
    return '/'
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return '/'
  if (url.origin !== origin) return '/'
  if (url.username || url.password) return '/'
  return url.pathname + url.search + url.hash
}

/** Builds a portal URL with properly encoded parameters. */
export function portalUrl(path: string, params: Record<string, string>): string {
  return `/__auth${path}?${new URLSearchParams(params)}`
}
