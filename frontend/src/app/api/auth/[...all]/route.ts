import { toNextJsHandler } from 'better-auth/next-js'
import { auth } from '@/lib/auth'

// Better Auth's endpoints (/api/auth/sign-in/email, /get-session, /sign-out, ...). Route handlers
// take precedence over next.config's fallback rewrite of /api/* to the FastAPI backend.
export const { GET, POST } = toNextJsHandler(auth)
