// The API's /api/internal/* routes are for the proxy container, the updater and
// this app's own server side, which call the API directly on the Docker network.
// They are never served through the admin UI: this handler takes precedence over
// the generic /api/* fallback rewrite in next.config.ts.

function notFound() {
  return new Response('Not Found', { status: 404, headers: { 'Cache-Control': 'no-store' } })
}

export const dynamic = 'force-dynamic'

export const GET = notFound
export const HEAD = notFound
export const POST = notFound
export const PUT = notFound
export const PATCH = notFound
export const DELETE = notFound
export const OPTIONS = notFound
