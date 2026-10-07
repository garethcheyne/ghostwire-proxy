import { NextResponse, type NextRequest } from 'next/server'

// The API's /api/internal/* routes are for co-located services only (the proxy
// container, the updater, this app's server side). Runs before the rewrites in
// next.config.ts, and looks at the decoded path so encoded or doubled-slash
// spellings ("/api/%69nternal", "/api//internal") are refused too.
export function proxy(request: NextRequest) {
  let path = request.nextUrl.pathname
  try {
    path = decodeURIComponent(path)
  } catch {
    // malformed escapes: judge the raw path
  }
  if (/^\/api\/+internal(\/|$)/i.test(path.replace(/\\/g, '/'))) {
    return new NextResponse('Not Found', { status: 404, headers: { 'Cache-Control': 'no-store' } })
  }
  return NextResponse.next()
}

export const config = {
  matcher: '/api/:path*',
}
