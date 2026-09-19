'use client'

import { ThemeProvider } from 'next-themes'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'
import { Toaster } from '@/components/toaster'
import { StaleDeploymentHandler } from '@/components/stale-deployment-handler'
import { ServiceWorkerRegistrar } from '@/components/service-worker-registrar'

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000,
            refetchOnWindowFocus: false,
          },
        },
      })
  )

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider
        attribute="class"
        defaultTheme="dark"
        enableSystem
        disableTransitionOnChange
      >
        {children}
        <Toaster />
        <StaleDeploymentHandler />
        <ServiceWorkerRegistrar />
      </ThemeProvider>
    </QueryClientProvider>
  )
}
