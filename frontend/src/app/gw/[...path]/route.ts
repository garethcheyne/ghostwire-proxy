// The /gw/ relay for visitor analytics: Ghostwire Analytics' tracker served from this origin, and what
// it sends forwarded to the Analytics URL in Settings. A 404 while visitor analytics is off.
import { createGhostwireRelay } from '@/components/analytics'
import { getAnalyticsConfig } from '@/lib/analytics-config'

export const { GET, POST } = createGhostwireRelay(getAnalyticsConfig)
