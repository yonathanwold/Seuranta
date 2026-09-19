import { Check, Copy, QrCode } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { NormalizedMode } from '../domain/types'
import { resolveTrackerUrl } from '../domain/trackerUrl'

interface TrackerConnectProps {
  mode: NormalizedMode
  apiUrl: string
  connectedCount: number
}

const trimUrl = (value: string) => value.replace(/\/$/, '')

export function TrackerConnect({ mode, apiUrl, connectedCount }: TrackerConnectProps) {
  const [copied, setCopied] = useState(false)
  const [serverPublicUrl, setServerPublicUrl] = useState('')
  const [configState, setConfigState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [configError, setConfigError] = useState('')
  const [qrState, setQrState] = useState<'loading' | 'ready' | 'error' | 'unavailable'>('loading')
  const serverApiUrl = trimUrl(apiUrl || (import.meta.env.VITE_SEURANTA_API_URL as string | undefined) || window.location.origin)
  useEffect(() => {
    let cancelled = false
    setConfigState('loading')
    void fetch(`${serverApiUrl}/api/v1/tracker/config`).then(async (response) => {
      if (!response.ok) throw new Error(`Tracker configuration returned ${response.status}`)
      return response.json() as Promise<{ data?: { public_tracker_url?: string | null } }>
    }).then((body) => {
      if (!cancelled) { setServerPublicUrl(body.data?.public_tracker_url ?? ''); setConfigState('ready'); setConfigError('') }
    }).catch((error: unknown) => {
      if (!cancelled) { setConfigState('error'); setConfigError(error instanceof Error ? error.message : 'Tracker configuration could not be loaded.') }
    })
    return () => { cancelled = true }
  }, [serverApiUrl])
  const configured = import.meta.env.VITE_SEURANTA_PUBLIC_TRACKER_URL as string | undefined
  const trackerResolution = useMemo(() => resolveTrackerUrl(configured || serverPublicUrl || undefined, window.location.origin), [configured, serverPublicUrl])
  const trackerUrl = trackerResolution.url
  const qrUrl = trackerUrl ? `${serverApiUrl}/api/v1/tracker/qr?url=${encodeURIComponent(trackerUrl)}` : ''
  useEffect(() => { setQrState(trackerUrl ? 'loading' : 'unavailable') }, [trackerUrl])

  if (mode !== 'LIVE') return null

  const copyUrl = async () => {
    try {
      if (!trackerUrl) return
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
      {trackerUrl ? <button className="tracker-url" onClick={() => { void copyUrl() }} title="Copy tracker URL"><code>{trackerUrl}</code>{copied ? <Check size={14} /> : <Copy size={14} />}</button> : <p className="tracker-connect-warning" role="status">{configState === 'error' ? `${configError} ` : ''}{trackerResolution.reason ?? 'Waiting for tracker configuration.'}</p>}
      <small>{copied ? 'Tracker URL copied.' : trackerUrl ? 'This is the configured HTTPS tracker address for consenting phones.' : 'The QR code stays hidden until a valid phone-reachable HTTPS tracker URL is configured.'}</small>
    </div>
    <div className="tracker-qr-wrap">
      {qrState === 'loading' && <span role="status">Loading QR…</span>}
      {qrState === 'unavailable' && <span role="status">QR unavailable until HTTPS tracker URL is configured.</span>}
      {qrState === 'error' && <span role="status">QR could not be rendered. Check the API QR service.</span>}
      {trackerUrl && qrState !== 'error' && <img src={qrUrl} alt="QR code for the Seuranta phone tracker" onLoad={() => setQrState('ready')} onError={() => setQrState('error')} />}
      <span>Connected devices: {connectedCount}</span>
    </div>
  </section>
}
