/**
 * Admin sign-in with Better Auth (server side).
 *
 * Better Auth runs here, in the admin UI, and shares the proxy's PostgreSQL with the API:
 * - `users` is its user table (the API's model), mapped below to Better Auth's field names.
 * - `auth_session`, `auth_account` and `auth_verification` hold sessions, passwords and one-time
 *   tokens (created by backend/alembic/versions/0003_better_auth.py).
 * The API reads the session cookie itself (backend/app/core/auth_session.py), so the cookie
 * prefix here and COOKIE_NAMES there must match.
 *
 * Passwords are bcrypt, as the API always stored them, so existing passwords keep working and
 * the API can set passwords when admins manage users. Admin two-factor stays in the API; the
 * adminMfa plugin (./auth-admin-mfa.ts) asks for the second factor before a session exists.
 */
import { betterAuth } from 'better-auth'
import { APIError, createAuthMiddleware } from 'better-auth/api'
import bcrypt from 'bcryptjs'
import { Pool } from 'pg'
import { adminMfa } from './auth-admin-mfa'

const BCRYPT_ROUNDS = 12
const SESSION_DAYS = 7

// DATABASE_URL, or the standard PGHOST/PGUSER/PGPASSWORD/PGDATABASE variables (no URL encoding
// needed for passwords with special characters).
export const pool = new Pool(
  process.env.DATABASE_URL ? { connectionString: process.env.DATABASE_URL } : undefined
)

const timestamps = { createdAt: 'created_at', updatedAt: 'updated_at' }

function clientIp(headers?: Headers | null) {
  if (!headers) return null
  return (
    headers.get('cf-connecting-ip') ||
    headers.get('x-real-ip') ||
    headers.get('x-forwarded-for')?.split(',')[0].trim() ||
    null
  )
}

/** Writes to the API's audit_logs table (the Audit page shows these). */
async function writeAudit(
  action: string,
  user: { id?: string | null; email?: string | null },
  headers?: Headers | null,
  details?: string
) {
  try {
    await pool.query(
      `INSERT INTO audit_logs (id, user_id, email, action, details, ip_address, user_agent, timestamp)
       VALUES (gen_random_uuid()::text, $1, $2, $3, $4, $5, $6, now())`,
      [
        user.id ?? null,
        user.email ?? null,
        action,
        details ?? null,
        clientIp(headers)?.slice(0, 45) ?? null,
        headers?.get('user-agent') ?? null,
      ]
    )
  } catch (error) {
    console.error('audit log write failed', error)
  }
}

/** Audit entry for a user known by id (the email is looked up). */
async function auditUser(action: string, userId: string, headers?: Headers | null, details?: string) {
  const { rows } = await pool.query('SELECT id, email FROM users WHERE id = $1', [userId])
  await writeAudit(action, rows[0] ?? { id: userId }, headers, details)
}

/** A completed sign-in (after any second factor): count it and record it. */
async function recordSignIn(userId: string, headers?: Headers | null, details?: string) {
  const { rows } = await pool.query(
    `UPDATE users SET signin_count = signin_count + 1, last_signin_at = now()
     WHERE id = $1 RETURNING id, email`,
    [userId]
  )
  await writeAudit('login_success', rows[0] ?? { id: userId }, headers, details)
}

/** Failed sign-ins and sign-outs (successful ones are recorded by the adminMfa plugin). */
const auditAuthActivity = createAuthMiddleware(async (ctx) => {
  if (ctx.path === '/sign-in/email') {
    const returned = ctx.context.returned as { statusCode?: number } | Error | undefined
    const failed =
      returned instanceof Error || (!!returned && (returned.statusCode ?? 200) >= 400)
    if (failed) {
      const email = typeof ctx.body?.email === 'string' ? ctx.body.email.toLowerCase() : null
      const message =
        returned instanceof APIError ? returned.message : 'Invalid credentials'
      await writeAudit('login_failed', { email }, ctx.headers ?? ctx.request?.headers, message)
    }
  } else if (ctx.path === '/sign-out') {
    const user = ctx.context.session?.user
    if (user) await writeAudit('logout', user, ctx.headers ?? ctx.request?.headers)
  }
})

export const auth = betterAuth({
  appName: 'Ghostwire Proxy',
  secret: process.env.BETTER_AUTH_SECRET,
  // Optional: without it the address is taken from each request (the UI is often opened both
  // by IP on port 88 and through a domain).
  baseURL: process.env.BETTER_AUTH_URL || undefined,
  // Sign-in requests must come from the address the browser is on (or BETTER_AUTH_URL's). Taken
  // from the Host header: behind Docker's port mapping and reverse proxies, request.url is the
  // container's own address (e.g. localhost:3000), not what the browser used.
  trustedOrigins: async (request) => {
    const host = request?.headers.get('x-forwarded-host') || request?.headers.get('host')
    return host ? [`http://${host}`, `https://${host}`] : []
  },
  database: pool,
  advanced: {
    cookiePrefix: 'gwp',
    // Secure cookies only when BETTER_AUTH_URL is https. Better Auth's default (secure in production)
    // would lock out anyone opening the UI by IP over plain http (http://192.168.x.x:88), since
    // browsers drop Secure cookies there. The cookie is httpOnly and SameSite=Lax either way.
    useSecureCookies: (process.env.BETTER_AUTH_URL || '').startsWith('https://'),
    // String ids like the API's own rows (the columns have no database default).
    database: { generateId: () => crypto.randomUUID() },
    ipAddress: { ipAddressHeaders: ['cf-connecting-ip', 'x-real-ip', 'x-forwarded-for'] },
  },
  emailAndPassword: {
    enabled: true,
    // Admins create users (Users page); the first one comes from the setup screen.
    disableSignUp: true,
    minPasswordLength: 8,
    password: {
      hash: (password) => bcrypt.hash(password, BCRYPT_ROUNDS),
      verify: ({ hash, password }) => bcrypt.compare(password, hash),
    },
  },
  user: {
    modelName: 'users',
    fields: { emailVerified: 'email_verified', ...timestamps },
    additionalFields: {
      role: { type: 'string', required: false, input: false },
      isActive: { type: 'boolean', fieldName: 'is_active', required: false, input: false },
    },
  },
  session: {
    modelName: 'auth_session',
    fields: {
      userId: 'user_id',
      expiresAt: 'expires_at',
      ipAddress: 'ip_address',
      userAgent: 'user_agent',
      ...timestamps,
    },
    expiresIn: SESSION_DAYS * 24 * 60 * 60,
    updateAge: 24 * 60 * 60,
  },
  account: {
    modelName: 'auth_account',
    fields: {
      userId: 'user_id',
      accountId: 'account_id',
      providerId: 'provider_id',
      accessToken: 'access_token',
      refreshToken: 'refresh_token',
      idToken: 'id_token',
      accessTokenExpiresAt: 'access_token_expires_at',
      refreshTokenExpiresAt: 'refresh_token_expires_at',
      ...timestamps,
    },
  },
  verification: {
    modelName: 'auth_verification',
    fields: { expiresAt: 'expires_at', ...timestamps },
  },
  databaseHooks: {
    session: {
      create: {
        // Disabled accounts can't sign in (the API also refuses them on every request).
        before: async (session) => {
          const { rows } = await pool.query('SELECT is_active FROM users WHERE id = $1', [
            session.userId,
          ])
          if (!rows[0]?.is_active) {
            throw new APIError('FORBIDDEN', { message: 'Account is disabled' })
          }
        },
      },
    },
  },
  hooks: {
    after: auditAuthActivity,
  },
  plugins: [adminMfa({ onSignIn: recordSignIn, audit: auditUser })],
})

export type AuthSession = typeof auth.$Infer.Session
