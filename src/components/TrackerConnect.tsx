import { Check, Copy, QrCode } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { NormalizedMode } from '../domain/types'

interface TrackerConnectProps {
  mode: NormalizedMode
  apiUrl: string
  connectedCount: number
}

const trimUrl = (value: string) => value.replace(/\/$/, '')

export function TrackerConnect({ mode, apiUrl, connectedCount }: TrackerConnectProps) {
  const [copied, setCopied] = useState(false)
  const [serverPublicUrl, setServerPublicUrl] = useState('')
  const serverApiUrl = trimUrl(apiUrl || (import.meta.env.VITE_SEURANTA_API_URL as string | undefined) || window.location.origin)
  useEffect(() => {
    let cancelled = false
    void fetch(`${serverApiUrl}/api/v1/tracker/config`).then((response) => response.ok ? response.json() : null).then((body: { data?: { public_tracker_url?: string | null } } | null) => {
      if (!cancelled && body?.data?.public_tracker_url) setServerPublicUrl(body.data.public_tracker_url)
    }).catch(() => undefined)
    return () => { cancelled = true }
  }, [serverApiUrl])
  const trackerUrl = useMemo(() => {
    const configured = import.meta.env.VITE_SEURANTA_PUBLIC_TRACKER_URL as string | undefined
    return trimUrl(configured || serverPublicUrl || `${serverApiUrl}/tracker/`) + '/'
  }, [serverApiUrl, serverPublicUrl])
  const qrUrl = `${serverApiUrl}/api/v1/tracker/qr?url=${encodeURIComponent(trackerUrl)}`

  if (mode !== 'LIVE') return null

  const copyUrl = async () => {
    try {
      await navigator.clipboard.writeText(trackerUrl)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      setCopied(false)
    }
  }

  return <section className="tracker-connect" aria-label="Connect a consenting phone">
    <div className="tracker-connect-copy">
      <div className="panel-heading"><span><QrCode size={15} /> Connect device</span><span className="live-badge">LIVE</span></div>
      <h2>Scan to join this live deployment.</h2>
      <p>Open the tracker on a consenting iPhone or Android device. Location permission is requested only after the person presses Enable Precise Location.</p>
      <button className="tracker-url" onClick={() => { void copyUrl() }} title="Copy tracker URL"><code>{trackerUrl}</code>{copied ? <Check size={14} /> : <Copy size={14} />}</button>
      <small>{copied ? 'Tracker URL copied.' : 'The tracker page is served by the configured backend.'}</small>
    </div>
    <div className="tracker-qr-wrap"><img src={qrUrl} alt="QR code for the Seuranta phone tracker" /><span>Connected devices: {connectedCount}</span></div>
  </section>
}
