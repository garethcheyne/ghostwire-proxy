// Liveness: the process is up. The container healthcheck uses this; /api/health also checks the
// database.
export function GET() {
  return Response.json({ ok: true }, { headers: { 'Cache-Control': 'no-store' } })
}
