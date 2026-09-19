'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { authClient } from '@/lib/auth-client'

export default function Home() {
  const router = useRouter()

  useEffect(() => {
    authClient
      .getSession()
      .then(({ data }) => router.push(data ? '/dashboard' : '/auth/login'))
      .catch(() => router.push('/auth/login'))
  }, [router])

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="animate-pulse text-muted-foreground">Loading...</div>
    </div>
  )
}
