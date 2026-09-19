/**
 * Admin two-factor for Better Auth sign-in, backed by the API's existing two-factor service.
 *
 * Two-factor secrets, backup codes and the "required for everyone" policy live in the API
 * (admin_mfa_service, users.totp_*), as before this moved to Better Auth, so nobody re-enrols.
 * After a correct password this plugin decides what sign-in still needs:
 *
 *   none   -> the session stands.
 *   totp   -> the session is withdrawn and a short-lived signed challenge cookie is set; the
 *             session is created once /admin-mfa/verify accepts a code (TOTP or backup code).
 *   enrol  -> two-factor is required and the user hasn't set it up: /admin-mfa/enrol/begin and
 *             /admin-mfa/enrol/confirm set it up, then the session is created.
 *
 * Codes are checked by the API over its internal endpoints (/api/internal/admin-mfa/*).
 * Modelled on Better Auth's own twoFactor plugin, which can't be used directly because it keeps
 * its own secrets (in a format existing authenticator apps wouldn't match).
 */
import type { BetterAuthPlugin } from 'better-auth'
import { APIError, createAuthEndpoint, createAuthMiddleware } from 'better-auth/api'
import { deleteSessionCookie, expireCookie, setSessionCookie } from 'better-auth/cookies'
import { generateRandomString } from 'better-auth/crypto'
import { z } from 'zod'

const CHALLENGE_COOKIE = 'admin_mfa'
const CHALLENGE_SECONDS = 10 * 60
const MAX_ATTEMPTS = 5

type Stage = 'totp' | 'enrol'
type Challenge = { userId: string; stage: Stage; attempts: number }

interface AdminMfaOptions {
  /** A completed sign-in (after any second factor): count it and write the audit entry. */
  onSignIn: (userId: string, headers: Headers | undefined, details?: string) => Promise<void>
  audit: (action: string, userId: string, headers: Headers | undefined, details?: string) => Promise<void>
}

async function internalApi<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const backend = process.env.BACKEND_URL || 'http://ghostwire-proxy-api:8000'
  const response = await fetch(`${backend}/api/internal/admin-mfa${path}`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'X-Internal-Auth': process.env.INTERNAL_AUTH_TOKEN || '',
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(10_000),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new APIError(response.status === 409 ? 'CONFLICT' : 'BAD_REQUEST', {
      message: typeof data?.detail === 'string' ? data.detail : 'Two-factor check failed',
    })
  }
  return data as T
}

const codeBody = z.object({ code: z.string().trim().min(6).max(32) })

export function adminMfa(options: AdminMfaOptions) {
  // The pending challenge from the signed cookie, or a 401 telling the user to sign in again.
  async function readChallenge(ctx: any, stage: Stage) {
    const cookie = ctx.context.createAuthCookie(CHALLENGE_COOKIE, { maxAge: CHALLENGE_SECONDS })
    const identifier = await ctx.getSignedCookie(cookie.name, ctx.context.secret)
    const record = identifier
      ? await ctx.context.internalAdapter.findVerificationValue(identifier)
      : null
    const challenge: Challenge | null = record ? JSON.parse(record.value) : null
    if (!record || !challenge || record.expiresAt < new Date() || challenge.stage !== stage) {
      expireCookie(ctx, cookie)
      throw new APIError('UNAUTHORIZED', { message: 'Sign-in expired. Enter your password again.' })
    }
    return { cookie, identifier: identifier as string, challenge }
  }

  // A wrong code: count it, and drop the challenge after MAX_ATTEMPTS.
  async function failAttempt(ctx: any, identifier: string, challenge: Challenge, cookie: any) {
    const attempts = challenge.attempts + 1
    if (attempts >= MAX_ATTEMPTS) {
      await ctx.context.internalAdapter.deleteVerificationByIdentifier(identifier)
      expireCookie(ctx, cookie)
      throw new APIError('UNAUTHORIZED', {
        message: 'Too many wrong codes. Enter your password again.',
      })
    }
    await ctx.context.internalAdapter.updateVerificationByIdentifier(identifier, {
      value: JSON.stringify({ ...challenge, attempts }),
    })
  }

  // Second factor done: create the real session.
  async function completeSignIn(ctx: any, identifier: string, cookie: any, userId: string, details?: string) {
    await ctx.context.internalAdapter.deleteVerificationByIdentifier(identifier)
    expireCookie(ctx, cookie)
    const user = await ctx.context.internalAdapter.findUserById(userId)
    if (!user) throw new APIError('UNAUTHORIZED', { message: 'Account not found' })
    const session = await ctx.context.internalAdapter.createSession(userId, false)
    await setSessionCookie(ctx, { session, user })
    await options.onSignIn(userId, ctx.headers ?? ctx.request?.headers, details)
  }

  return {
    id: 'admin-mfa',
    hooks: {
      after: [
        {
          matcher: (context) => context.path === '/sign-in/email',
          handler: createAuthMiddleware(async (ctx) => {
            const data = ctx.context.newSession
            if (!data) return
            const headers = ctx.headers ?? ctx.request?.headers
            const { required } = await internalApi<{ required: Stage | 'none' }>('/state', {
              user_id: data.user.id,
            })
            if (required === 'none') {
              await options.onSignIn(data.user.id, headers)
              return
            }

            // Password accepted, but it isn't enough on its own: withdraw the session.
            deleteSessionCookie(ctx, true)
            await ctx.context.internalAdapter.deleteSession(data.session.token)
            ctx.context.setNewSession(null)

            const identifier = `admin-mfa-${generateRandomString(32)}`
            const challenge: Challenge = { userId: data.user.id, stage: required, attempts: 0 }
            await ctx.context.internalAdapter.createVerificationValue({
              identifier,
              value: JSON.stringify(challenge),
              expiresAt: new Date(Date.now() + CHALLENGE_SECONDS * 1000),
            })
            const cookie = ctx.context.createAuthCookie(CHALLENGE_COOKIE, { maxAge: CHALLENGE_SECONDS })
            await ctx.setSignedCookie(cookie.name, identifier, ctx.context.secret, cookie.attributes)

            await options.audit(
              required === 'totp' ? 'login_mfa_challenged' : 'login_mfa_enrolment_required',
              data.user.id,
              headers,
              required === 'totp'
                ? 'Password accepted, awaiting TOTP'
                : 'MFA required org-wide; user not enrolled'
            )
            return ctx.json({ mfa: required })
          }),
        },
      ],
    },
    endpoints: {
      adminMfaVerify: createAuthEndpoint(
        '/admin-mfa/verify',
        { method: 'POST', body: codeBody },
        async (ctx) => {
          const { cookie, identifier, challenge } = await readChallenge(ctx, 'totp')
          const result = await internalApi<{ ok: boolean; backup_codes_remaining: number | null }>(
            '/verify',
            { user_id: challenge.userId, code: ctx.body.code }
          )
          if (!result.ok) {
            await options.audit(
              'login_mfa_failed',
              challenge.userId,
              ctx.headers ?? ctx.request?.headers,
              'Invalid TOTP or backup code'
            )
            await failAttempt(ctx, identifier, challenge, cookie)
            throw new APIError('UNAUTHORIZED', { message: 'Invalid verification code' })
          }
          await completeSignIn(
            ctx,
            identifier,
            cookie,
            challenge.userId,
            `Second factor verified (${result.backup_codes_remaining ?? 0} backup codes remaining)`
          )
          return ctx.json({ ok: true, backupCodesRemaining: result.backup_codes_remaining })
        }
      ),
      adminMfaEnrolBegin: createAuthEndpoint('/admin-mfa/enrol/begin', { method: 'POST' }, async (ctx) => {
        const { challenge } = await readChallenge(ctx, 'enrol')
        const setup = await internalApi<{
          secret: string
          provisioning_uri: string
          qr_code: string | null
          backup_codes: string[]
        }>('/enrol/begin', { user_id: challenge.userId })
        await options.audit('mfa_setup_started', challenge.userId, ctx.headers ?? ctx.request?.headers)
        return ctx.json(setup)
      }),
      adminMfaEnrolConfirm: createAuthEndpoint(
        '/admin-mfa/enrol/confirm',
        { method: 'POST', body: codeBody },
        async (ctx) => {
          const { cookie, identifier, challenge } = await readChallenge(ctx, 'enrol')
          const headers = ctx.headers ?? ctx.request?.headers
          const { ok } = await internalApi<{ ok: boolean }>('/enrol/confirm', {
            user_id: challenge.userId,
            code: ctx.body.code,
          })
          if (!ok) {
            await options.audit('mfa_setup_failed', challenge.userId, headers, 'Invalid code during enrolment')
            await failAttempt(ctx, identifier, challenge, cookie)
            throw new APIError('BAD_REQUEST', {
              message: "That code didn't match. Check your device's clock and try again.",
            })
          }
          await options.audit('mfa_enabled', challenge.userId, headers)
          await completeSignIn(ctx, identifier, cookie, challenge.userId, 'Two-factor set up at sign-in')
          return ctx.json({ ok: true })
        }
      ),
    },
    rateLimit: [
      { pathMatcher: (path: string) => path.startsWith('/admin-mfa/'), window: 60, max: 10 },
    ],
  } satisfies BetterAuthPlugin
}
