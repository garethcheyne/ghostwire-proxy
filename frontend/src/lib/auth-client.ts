import { createAuthClient } from 'better-auth/react'
import { inferAdditionalFields } from 'better-auth/client/plugins'
import type { auth } from './auth'

/** Admin sign-in (Better Auth). The session is an httpOnly cookie the API also accepts. */
export const authClient = createAuthClient({
  plugins: [inferAdditionalFields<typeof auth>()],
})

export const { useSession, signIn, signOut } = authClient
