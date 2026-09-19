export interface TrackerUrlResolution {
  url: string | null
  reason: string | null
}

const loopbackHosts = new Set(['localhost', '127.0.0.1', '[::1]'])

/** Phone QR codes must point at an HTTPS address that another device can reach. */
export function resolveTrackerUrl(configuredUrl: string | undefined, currentOrigin: string): TrackerUrlResolution {
  const candidate = configuredUrl?.trim() || currentOrigin
  try {
    const parsed = new URL(candidate)
    if (parsed.protocol !== 'https:') return { url: null, reason: 'Configure SEURANTA_PUBLIC_TRACKER_URL with a phone-reachable HTTPS tracker URL.' }
    if (loopbackHosts.has(parsed.hostname.toLowerCase())) return { url: null, reason: 'The current tracker address is localhost. Configure a phone-reachable HTTPS tracker URL before scanning.' }
    const pathname = parsed.pathname.replace(/\/+$/, '')
    parsed.pathname = pathname.endsWith('/tracker') ? `${pathname}/` : `${pathname}/tracker/`
    parsed.search = ''
    parsed.hash = ''
    return { url: parsed.toString(), reason: null }
  } catch {
    return { url: null, reason: 'The configured tracker URL is invalid. Use a complete HTTPS URL.' }
  }
}
