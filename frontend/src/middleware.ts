import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export function middleware(request: NextRequest) {
  const response = NextResponse.next()

  // Strip headers that leak framework identity
  response.headers.delete('x-nextjs-cache')
  response.headers.delete('x-nextjs-prerender')
  response.headers.delete('x-nextjs-stale-time')
  response.headers.delete('x-nextjs-matched-path')

  return response
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
}
