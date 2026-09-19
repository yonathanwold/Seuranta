import { adaptEvent, adaptMode, adaptNode, adaptPosition, adaptSession, adaptState, unwrapData } from './adapters'
import type { NormalizedMode, NormalizedState, PositionProvider, ProviderSnapshot } from './types'

const apiBase = (import.meta.env.VITE_SEURANTA_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export interface LiveScope {
  apiUrl?: string
  runId: string
  deploymentId: string
  buildingId: string
  floorId: string
  mode?: NormalizedMode
}

type WireMessage = { type?: unknown; state_revision?: unknown; data?: unknown }
type WireRecord = Record<string, unknown>

const defaultScope: LiveScope = { runId: 'vt-acb-floor1', deploymentId: 'vt-acb-pilot', buildingId: 'vt-academic-classroom-building', floorId: 'floor-1', mode: 'LIVE' }
const initialState = (scope: LiveScope): NormalizedState => adaptState({ data: { state_revision: 0, generated_at: new Date().toISOString(), run_id: scope.runId, deployment_id: scope.deploymentId, building_id: scope.buildingId, floor_id: scope.floorId, sessions: [], positions: [], nodes: [], recent_events: [], zone_metrics: [], counts: {}, is_partial: true, mode: scope.mode ?? 'LIVE' } })
const isRecord = (value: unknown): value is WireRecord => Boolean(value && typeof value === 'object' && !Array.isArray(value))
const isStatePayload = (value: unknown): value is WireRecord => isRecord(value) && (typeof value.state_revision === 'number' || Array.isArray(value.positions) || Array.isArray(value.nodes) || Array.isArray(value.recent_events))
const revisionOf = (value: unknown): number | undefined => typeof value === 'number' && Number.isFinite(value) ? Math.max(0, Math.round(value)) : undefined
const wireMode = (mode: NormalizedMode | undefined): 'real' | 'simulated' => mode === 'SIMULATION' ? 'simulated' : 'real'
const wireScopeFields = ['run_id', 'deployment_id', 'building_id', 'floor_id'] as const
const recognizedModes = new Set(['LIVE', 'REAL', 'PRODUCTION', 'SIMULATION', 'SIMULATED', 'REPLAY', 'HISTORICAL'])

/** Live adapter: scoped REST snapshot plus typed state-revision WebSocket deltas. */
export class LivePositionProvider implements PositionProvider {
  readonly kind = 'live' as const
  private listener: ((snapshot: ProviderSnapshot) => void) | undefined
  private socket: WebSocket | undefined
  private retryTimer: ReturnType<typeof setTimeout> | undefined
  private retryMs = 1000
  private refreshInFlight = false
  private refreshController: AbortController | undefined
  private state: NormalizedState
  private stopped = true
  private generation = 0
  private readonly scope: LiveScope
  private readonly baseUrl: string

  constructor(scope: Partial<LiveScope> = {}) {
    this.scope = { ...defaultScope, ...scope }
    this.baseUrl = this.scope.apiUrl?.replace(/\/$/, '') || apiBase
    this.state = initialState(this.scope)
  }

  start(listener: (snapshot: ProviderSnapshot) => void): void {
    this.generation += 1
    this.refreshController?.abort()
    this.refreshController = undefined
    this.clearRetryTimer()
    const oldSocket = this.socket
    this.socket = undefined
    oldSocket?.close()
    this.refreshInFlight = false
    this.listener = listener
    this.stopped = false
    this.retryMs = 1000
    this.state = initialState(this.scope)
    this.emit('connecting')
    void this.refresh()
  }

  stop(): void {
    this.generation += 1
    this.stopped = true
    this.refreshController?.abort()
    this.refreshController = undefined
    this.clearRetryTimer()
    const socket = this.socket
    this.socket = undefined
    socket?.close()
    this.refreshInFlight = false
    this.listener = undefined
  }

  async refresh(forceFull = false): Promise<void> {
    if (this.stopped || this.refreshInFlight) return
    const generation = this.generation
    const controller = new AbortController()
    this.refreshController = controller
    this.refreshInFlight = true
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/state?${this.scopeParams(forceFull)}`, { signal: controller.signal })
      if (generation !== this.generation || this.stopped) return
      if (!response.ok) throw new Error(`State request returned ${response.status}`)
      const payload = unwrapData(await response.json())
      if (!isStatePayload(payload) || !this.hasMatchingWireScope(payload)) throw new Error('State response was malformed or outside the configured scope')
      const next = adaptState(payload, this.state)
      if (next.stateRevision < this.state.stateRevision) return
      if (!(next.isPartial && !this.state.isPartial && next.positions.length === 0 && next.nodes.length === 0)) this.state = next
      this.clearRetryTimer()
      this.retryMs = 1000
      this.emit('live')
      this.connectSocket()
    } catch (error) {
      if (generation !== this.generation || this.stopped || (error instanceof DOMException && error.name === 'AbortError')) return
      this.emit(this.state.stateRevision ? 'reconnecting' : 'error', error instanceof Error ? error.message : 'Unable to load live state')
      this.scheduleReconnect()
    } finally {
      if (generation === this.generation) {
        this.refreshInFlight = false
        this.refreshController = undefined
      }
    }
  }

  private scopeParams(forceFull = false): URLSearchParams {
    const params = new URLSearchParams({ run_id: this.scope.runId, deployment_id: this.scope.deploymentId, building_id: this.scope.buildingId, floor_id: this.scope.floorId, mode: wireMode(this.scope.mode) })
    if (!forceFull && this.state.stateRevision > 0) params.set('since_revision', String(this.state.stateRevision))
    return params
  }

  private socketUrl(): string {
    const base = this.baseUrl ? new URL(this.baseUrl, window.location.href) : new URL(window.location.href)
    base.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
    base.pathname = `${base.pathname.replace(/\/$/, '')}/api/v1/live`
    base.search = this.scopeParams().toString()
    return base.toString()
  }

  private connectSocket(): void {
    if (this.stopped || this.socket) return
    const generation = this.generation
    const socket = new WebSocket(this.socketUrl())
    this.socket = socket
    socket.onopen = () => { if (generation !== this.generation || this.socket !== socket) return; this.retryMs = 1000; this.emit('live') }
    socket.onmessage = (event) => { if (generation === this.generation && this.socket === socket) this.handleMessage(event.data) }
    socket.onerror = () => { if (generation === this.generation && this.socket === socket) socket.close() }
    socket.onclose = () => {
      if (generation !== this.generation || this.socket !== socket) return
      this.socket = undefined
      if (!this.stopped) { this.emit('reconnecting'); this.scheduleReconnect() }
    }
  }

  private handleMessage(raw: unknown): void {
    let message: WireMessage
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) as unknown : raw
      if (!isRecord(parsed)) return
      message = parsed
    } catch { return }
    const type = typeof message.type === 'string' ? message.type : ''
    const revision = revisionOf(message.state_revision)
    if (type === 'snapshot_required') {
      const socket = this.socket
      this.socket = undefined
      this.clearRetryTimer()
      socket?.close()
      void this.refresh(true)
      return
    }
    if (type === 'heartbeat' || type === 'observation' || type === 'observations') {
      if (revision !== undefined && revision >= this.state.stateRevision) {
        this.state = revision > this.state.stateRevision ? { ...this.state, stateRevision: revision } : this.state
        this.emit('live')
      }
      return
    }
    if (type === 'snapshot' || type === 'state') {
      const snapshot = unwrapData(message.data)
      if (revision === undefined || revision < this.state.stateRevision || !isStatePayload(snapshot) || !this.hasMatchingWireScope(snapshot)) return
      const next = adaptState(snapshot, this.state)
      next.stateRevision = revision
      if (!(next.isPartial && !this.state.isPartial && next.positions.length === 0 && next.nodes.length === 0)) this.state = next
      this.emit('live')
      return
    }
    const data = unwrapData(message.data)
    if (!isRecord(data)) return
    if (type === 'position') {
      if (revision === undefined || revision < this.state.stateRevision || !this.hasMatchingWireScope(data) || typeof data.session_id !== 'string' || !data.session_id || typeof data.x_m !== 'number' || typeof data.y_m !== 'number') return
      const position = adaptPosition(data)
      if (!this.inScope(position.runId, position.deploymentId, position.buildingId, position.floorId)) return
      const positions = this.replaceBy(this.state.positions, position.sessionId, position, (item) => item.sessionId)
      this.state = { ...this.state, stateRevision: revision, generatedAt: position.calculatedAt, positions, counts: { ...this.state.counts, activeSessions: positions.length } }
      this.emit('live')
      return
    }
    if (type === 'node') {
      if (revision === undefined || revision < this.state.stateRevision || !this.hasMatchingWireScope(data) || typeof data.anchor_id !== 'string' || !data.anchor_id) return
      const node = adaptNode(data)
      if (!this.inScope(node.runId, node.deploymentId, node.buildingId, node.floorId)) return
      const nodes = this.replaceBy(this.state.nodes, node.anchorId, node, (item) => item.anchorId)
      const anchorsOnline = nodes.filter((item) => item.status === 'online').length
      const anchorsDegraded = nodes.filter((item) => item.status === 'degraded').length
      this.state = { ...this.state, stateRevision: revision, generatedAt: node.emittedAt, nodes, counts: { ...this.state.counts, anchorsOnline, anchorsDegraded } }
      this.emit('live')
      return
    }
    if (type === 'event') {
      if (revision === undefined || revision < this.state.stateRevision || !this.hasMatchingWireScope(data) || typeof data.event_id !== 'string' || !data.event_id || typeof data.event_type !== 'string' || !data.event_type) return
      const eventValue = adaptEvent(data)
      if (!this.inScope(eventValue.runId, eventValue.deploymentId, eventValue.buildingId, eventValue.floorId)) return
      this.state = { ...this.state, stateRevision: revision, generatedAt: eventValue.emittedAt, recentEvents: [eventValue, ...this.state.recentEvents.filter((item) => item.eventId !== eventValue.eventId)].slice(0, 25) }
      this.emit('live')
      return
    }
    if (type === 'session' || type === 'session_ended') {
      if (revision === undefined || revision < this.state.stateRevision || !this.hasMatchingWireScope(data) || typeof data.session_id !== 'string' || !data.session_id) return
      const session = adaptSession({ ...data, status: type === 'session_ended' ? 'ended' : data.status })
      if (!this.inScope(session.runId, session.deploymentId, session.buildingId, session.floorId)) return
      const sessions = this.replaceBy(this.state.sessions, session.sessionId, session, (item) => item.sessionId)
      this.state = { ...this.state, stateRevision: revision, generatedAt: session.lastUpdate, sessions }
      this.emit('live')
      return
    }
    // Unknown message types are intentionally ignored. A revision on an
    // unknown payload must not make an untrusted message appear accepted.
  }

  private hasMatchingWireScope(data: WireRecord): boolean {
    const values = wireScopeFields.map((field) => data[field])
    if (values.some((value) => typeof value !== 'string' || !value)) return false
    if (values[0] !== this.scope.runId || values[1] !== this.scope.deploymentId || values[2] !== this.scope.buildingId || values[3] !== this.scope.floorId) return false
    if (data.mode !== undefined) {
      if (typeof data.mode !== 'string') return false
      const normalizedMode = data.mode.trim().toUpperCase()
      if (!recognizedModes.has(normalizedMode) || adaptMode(normalizedMode) !== (this.scope.mode ?? 'LIVE')) return false
    }
    return true
  }

  private inScope(runId: string, deploymentId: string, buildingId: string, floorId: string): boolean {
    return runId === this.scope.runId && deploymentId === this.scope.deploymentId && buildingId === this.scope.buildingId && floorId === this.scope.floorId
  }

  private replaceBy<T>(items: T[], key: string, next: T, getKey: (item: T) => string): T[] {
    const index = items.findIndex((item) => getKey(item) === key)
    if (index < 0) return [...items, next]
    return items.map((item, itemIndex) => itemIndex === index ? next : item)
  }

  private emit(providerStatus: ProviderSnapshot['providerStatus'], lastError?: string): void { this.listener?.({ state: this.state, providerStatus, lastError }) }
  private clearRetryTimer(): void { if (this.retryTimer) clearTimeout(this.retryTimer); this.retryTimer = undefined }
  private scheduleReconnect(): void {
    if (this.stopped || this.retryTimer) return
    this.retryTimer = setTimeout(() => { this.retryTimer = undefined; void this.refresh() }, this.retryMs)
    this.retryMs = Math.min(15000, this.retryMs * 2)
  }
}
