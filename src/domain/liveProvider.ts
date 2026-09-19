import { adaptState, unwrapData } from './adapters'
import type { NormalizedState, PositionProvider, ProviderSnapshot } from './types'

const apiBase = (import.meta.env.VITE_SEURANTA_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''
const initialState = (): NormalizedState => adaptState({ data: { state_revision: 0, generated_at: new Date().toISOString(), positions: [], nodes: [], recent_events: [], zone_metrics: [], counts: {}, is_partial: true, mode: 'LIVE' } })

/** Live adapter: REST snapshot first, then deltas from /api/v1/live. UI never sees wire DTOs. */
export class LivePositionProvider implements PositionProvider {
  readonly kind = 'live' as const
  private listener: ((snapshot: ProviderSnapshot) => void) | undefined
  private socket: WebSocket | undefined
  private retryTimer: ReturnType<typeof setTimeout> | undefined
  private retryMs = 1000
  private state = initialState()
  private stopped = true

  start(listener: (snapshot: ProviderSnapshot) => void): void {
    this.listener = listener; this.stopped = false; this.retryMs = 1000
    void this.refresh()
  }

  stop(): void {
    this.stopped = true; if (this.retryTimer) clearTimeout(this.retryTimer); this.retryTimer = undefined
    this.socket?.close(); this.socket = undefined; this.listener = undefined
  }

  async refresh(): Promise<void> {
    if (this.stopped) return
    const params = new URLSearchParams({ run_id: this.state.runId || 'demo-run-2026-09-19', deployment_id: this.state.deploymentId || 'demo-deployment', building_id: this.state.buildingId || 'riverside-office', floor_id: this.state.floorId || 'floor-2', mode: 'real' })
    try {
      const response = await fetch(`${apiBase}/api/v1/state?${params}`)
      if (!response.ok) throw new Error(`State request returned ${response.status}`)
      this.state = adaptState(await response.json(), this.state)
      this.listener?.({ state: this.state, providerStatus: 'live' })
      this.connectSocket()
    } catch (error) {
      this.listener?.({ state: this.state, providerStatus: this.state.stateRevision ? 'reconnecting' : 'error', lastError: error instanceof Error ? error.message : 'Unable to load live state' })
      this.scheduleReconnect()
    }
  }

  private connectSocket(): void {
    if (this.stopped || this.socket) return
    const base = apiBase ? new URL(apiBase, window.location.href) : new URL(window.location.href)
    base.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
    base.pathname = `${base.pathname.replace(/\/$/, '')}/api/v1/live`
    const socket = new WebSocket(base.toString()); this.socket = socket
    socket.onopen = () => { this.retryMs = 1000; this.listener?.({ state: this.state, providerStatus: 'live' }) }
    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as { type?: string; data?: unknown }
        if (payload.type === 'snapshot' || payload.type === 'state') this.state = adaptState(unwrapData(payload.data), this.state)
        else if (payload.type !== 'heartbeat' && payload.data) this.state = adaptState({ ...this.state, ...(unwrapData(payload.data) as object) }, this.state)
        this.listener?.({ state: this.state, providerStatus: 'live' })
      } catch { this.listener?.({ state: this.state, providerStatus: 'error', lastError: 'Live update could not be read' }) }
    }
    socket.onerror = () => socket.close()
    socket.onclose = () => { this.socket = undefined; if (!this.stopped) this.scheduleReconnect() }
  }

  private scheduleReconnect(): void {
    if (this.stopped || this.retryTimer) return
    this.retryTimer = setTimeout(() => { this.retryTimer = undefined; void this.refresh() }, this.retryMs)
    this.retryMs = Math.min(15000, this.retryMs * 2)
  }
}
