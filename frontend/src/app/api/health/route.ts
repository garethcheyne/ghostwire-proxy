import { pool } from '@/lib/auth'

const startedAt = Date.now()

/**
 * Readiness for uptime monitors and scripts/upgrade.sh: 200 when the database answers, 503 when it
 * doesn't. (/api/heartbeat only says the process is up; the container healthcheck uses that.)
 */
export async function GET() {
  const began = Date.now()
  try {
    await pool.query('select 1')
    return Response.json(
      {
        ok: true,
        version: process.env.APP_VERSION,
        database: { ok: true, ms: Date.now() - began },
        uptimeSeconds: Math.round((Date.now() - startedAt) / 1000),
      },
      { headers: { 'Cache-Control': 'no-store' } },
    )
  } catch (error) {
    console.error('health: database unavailable', error)
    return Response.json(
      { ok: false, version: process.env.APP_VERSION, database: { ok: false } },
      { status: 503, headers: { 'Cache-Control': 'no-store' } },
    )
  }
}
