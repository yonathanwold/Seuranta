import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LivePositionProvider } from '../domain/liveProvider'

const scope = { runId: 'run-1', deploymentId: 'deployment-1', buildingId: 'building-1', floorId: 'floor-2', mode: 'LIVE' as const }
const wireScope = { run_id: scope.runId, deployment_id: scope.deploymentId, building_id: scope.buildingId, floor_id: scope.floorId }

const position = (sessionId = 'session-a', xM = 4) => ({
  schema_version: '1.0', position_id: `position-${sessionId}`, calculated_at: '2026-09-19T12:00:00.000Z',
  window_start: '2026-09-19T11:59:59.000Z', window_end: '2026-09-19T12:00:00.000Z', ...wireScope,
  session_id: sessionId, raw_x_m: xM, raw_y_m: 3, x_m: xM, y_m: 3, zone_id: 'office', confidence: .92,
  accuracy_radius_m: .8, position_method: 'wknn', smoothing_method: 'ema', anchors_used: ['a-01'], observation_count: 4,
  mode: 'real', sequence_number: 1, is_outside_map: false,
})

const node = (anchorId = 'a-01') => ({
  schema_version: '1.0', heartbeat_id: `heartbeat-${anchorId}`, emitted_at: '2026-09-19T12:00:00.000Z', ...wireScope,
  anchor_id: anchorId, node_kind: 'anchor', mode: 'real', status: 'online', uptime_s: 10, buffer_depth: 0,
  observations_sent_total: 3, last_observation_at: '2026-09-19T11:59:59.000Z', capture_ok: true, error_codes: [],
})

const event = (eventId = 'event-1') => ({
  event_id: eventId, event_type: 'ZONE_ENTERED', occurred_at: '2026-09-19T12:00:00.000Z', emitted_at: '2026-09-19T12:00:00.000Z', ...wireScope,
  mode: 'real', session_id: 'session-a', to_zone_id: 'office', event_sequence: 1,
})

const snapshot = (revision = 4, positions = [position()]) => ({
  data: {
    state_revision: revision, generated_at: '2026-09-19T12:00:00.000Z', ...wireScope, mode: 'real', positions,
    nodes: [node()], recent_events: [], zone_metrics: [], counts: {}, is_partial: false,
  },
})

class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  readonly url: string
  readonly readyState = 1
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  close() { this.onclose?.() }
  open() { this.onopen?.() }
  send(type: string, data: unknown, stateRevision: number) { this.onmessage?.({ data: JSON.stringify({ type, state_revision: stateRevision, data }) }) }
}

describe('live provider', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    FakeWebSocket.instances = []
    fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot() })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('WebSocket', FakeWebSocket)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('hydrates from scoped REST and opens a scoped WebSocket with data mode mapping', async () => {
    const provider = new LivePositionProvider(scope)
    const snapshots: number[] = []
    provider.start(({ state }) => snapshots.push(state.stateRevision))
    await vi.waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
    const socket = FakeWebSocket.instances[0]
    expect(String(fetchMock.mock.calls[0][0])).toContain('run_id=run-1')
    expect(String(fetchMock.mock.calls[0][0])).toContain('mode=real')
    expect(socket.url).toContain('deployment_id=deployment-1')
    expect(socket.url).toContain('building_id=building-1')
    expect(socket.url).toContain('floor_id=floor-2')
    expect(socket.url).toContain('mode=real')
    expect(socket.url).toContain('since_revision=4')
    expect(snapshots.at(-1)).toBe(4)
    provider.stop()
  })

  it('maps a normalized simulation scope to the data API mode vocabulary', async () => {
    const provider = new LivePositionProvider({ ...scope, mode: 'SIMULATION' })
    provider.start(() => undefined)
    await vi.waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
    expect(String(fetchMock.mock.calls[0][0])).toContain('mode=simulated')
    expect(FakeWebSocket.instances[0].url).toContain('mode=simulated')
    provider.stop()
  })

  it('reduces typed position, node, and event deltas without re-adapting normalized state', async () => {
    const provider = new LivePositionProvider(scope)
    const states: Array<{ revision: number; positionX: number; nodes: number; events: number }> = []
    provider.start(({ state }) => states.push({ revision: state.stateRevision, positionX: state.positions[0]?.xM ?? -1, nodes: state.nodes.length, events: state.recentEvents.length }))
    await vi.waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
    const socket = FakeWebSocket.instances[0]
    socket.send('position', position('session-a', 9), 5)
    socket.send('node', { ...node('a-02'), status: 'degraded' }, 6)
    socket.send('event', event('event-1'), 7)
    expect(states.at(-1)).toEqual({ revision: 7, positionX: 9, nodes: 2, events: 1 })
    socket.send('position', { session_id: '' }, 8)
    socket.send('unknown-message', { state_revision: 'not-a-number' }, 9)
    expect(states.at(-1)).toEqual({ revision: 9, positionX: 9, nodes: 2, events: 1 })
    socket.send('heartbeat', {}, 8)
    expect(states.at(-1)?.revision).toBe(9)
    provider.stop()
  })

  it('ignores missing or cross-scope position, node, and event deltas', async () => {
    const provider = new LivePositionProvider(scope)
    const states: Array<{ revision: number; positions: number; nodes: number; events: number }> = []
    provider.start(({ state }) => states.push({ revision: state.stateRevision, positions: state.positions.length, nodes: state.nodes.length, events: state.recentEvents.length }))
    await vi.waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
    const socket = FakeWebSocket.instances[0]
    const missingPosition = { ...position('session-missing') } as Record<string, unknown>
    delete missingPosition.run_id
    const crossPosition = { ...position('session-cross'), floor_id: 'floor-elsewhere' }
    const missingNode = { ...node('a-missing') } as Record<string, unknown>
    delete missingNode.deployment_id
    const crossNode = { ...node('a-cross'), building_id: 'building-elsewhere' }
    const missingEvent = { ...event('event-missing') } as Record<string, unknown>
    delete missingEvent.floor_id
    const crossEvent = { ...event('event-cross'), run_id: 'run-elsewhere' }
    socket.send('position', missingPosition, 8)
    socket.send('position', crossPosition, 9)
    socket.send('node', missingNode, 10)
    socket.send('node', crossNode, 9)
    socket.send('event', missingEvent, 11)
    socket.send('event', crossEvent, 12)
    expect(states.at(-1)).toEqual({ revision: 4, positions: 1, nodes: 1, events: 0 })
    provider.stop()
  })

  it('forces a full REST rehydrate on snapshot_required and preserves state on malformed messages', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => snapshot(4) }).mockResolvedValueOnce({ ok: true, json: async () => snapshot(9, [position('session-a', 12)]) })
    const provider = new LivePositionProvider(scope)
    const states: Array<{ revision: number; x: number }> = []
    provider.start(({ state }) => states.push({ revision: state.stateRevision, x: state.positions[0]?.xM ?? -1 }))
    await vi.waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
    const socket = FakeWebSocket.instances[0]
    socket.send('position', { session_id: 'bad-but-incomplete' }, 5)
    expect(states.at(-1)?.x).toBe(4)
    socket.send('snapshot_required', {}, 6)
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(String(fetchMock.mock.calls[1][0])).not.toContain('since_revision')
    await vi.waitFor(() => expect(states.at(-1)).toEqual({ revision: 9, x: 12 }))
    provider.stop()
  })

  it('retains the last state while a socket reconnects', async () => {
    const provider = new LivePositionProvider(scope)
    const states: Array<{ status: string; revision: number }> = []
    provider.start(({ state, providerStatus }) => states.push({ status: providerStatus, revision: state.stateRevision }))
    await vi.waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
    FakeWebSocket.instances[0].close()
    expect(states.at(-1)).toEqual({ status: 'reconnecting', revision: 4 })
    provider.stop()
  })
})
