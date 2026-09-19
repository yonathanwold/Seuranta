import type {
  NodeHeartbeat,
  NormalizedMode,
  NormalizedState,
  PositionEstimate,
  TrackerSessionView,
  SpatialEvent,
  EntityStatus,
  StateCounts,
} from './types'

type UnknownRecord = Record<string, unknown>

const asRecord = (value: unknown): UnknownRecord => (value && typeof value === 'object' ? value as UnknownRecord : {})
const text = (value: unknown, fallback = ''): string => typeof value === 'string' ? value : fallback
const number = (value: unknown, fallback = 0): number => typeof value === 'number' && Number.isFinite(value) ? value : fallback
const bool = (value: unknown, fallback = false): boolean => typeof value === 'boolean' ? value : fallback

/** Normalize backend mode variants (REAL/SIMULATED, LIVE/REPLAY/SIMULATION) at one boundary. */
export function adaptMode(value: unknown): NormalizedMode {
  const normalized = text(value).trim().toUpperCase()
  if (normalized === 'LIVE' || normalized === 'REAL' || normalized === 'PRODUCTION') return 'LIVE'
  if (normalized === 'REPLAY' || normalized === 'HISTORICAL') return 'REPLAY'
  return 'SIMULATION'
}

export function adaptStatus(value: unknown, captureOk = true): EntityStatus {
  const normalized = text(value).trim().toLowerCase()
  if (normalized === 'offline' || normalized === 'down') return 'offline'
  if (normalized === 'degraded' || normalized === 'warning' || !captureOk) return 'degraded'
  return 'online'
}

const timestamp = (value: unknown): string => text(value, new Date().toISOString())

export function adaptPosition(input: unknown): PositionEstimate {
  const source = asRecord(input)
  return {
    schemaVersion: text(source.schema_version, '1.0'),
    positionId: text(source.position_id, crypto.randomUUID()),
    calculatedAt: timestamp(source.calculated_at),
    windowStart: timestamp(source.window_start),
    windowEnd: timestamp(source.window_end),
    runId: text(source.run_id), deploymentId: text(source.deployment_id),
    buildingId: text(source.building_id), floorId: text(source.floor_id),
    sessionId: text(source.session_id), rawXM: number(source.raw_x_m), rawYM: number(source.raw_y_m),
    xM: number(source.x_m), yM: number(source.y_m), zoneId: typeof source.zone_id === 'string' ? source.zone_id : null,
    confidence: Math.min(1, Math.max(0, number(source.confidence))),
    accuracyRadiusM: Math.max(0, number(source.accuracy_radius_m, 1)),
    positionMethod: text(source.position_method, 'unknown'), smoothingMethod: text(source.smoothing_method, 'none'),
    anchorsUsed: Array.isArray(source.anchors_used) ? source.anchors_used.filter((item): item is string => typeof item === 'string') : [],
    observationCount: Math.max(0, Math.round(number(source.observation_count))), mode: adaptMode(source.mode),
    sequenceNumber: Math.max(0, Math.round(number(source.sequence_number))), isOutsideMap: bool(source.is_outside_map),
  }
}

export function adaptNode(input: unknown): NodeHeartbeat {
  const source = asRecord(input)
  const captureOk = bool(source.capture_ok, true)
  return {
    schemaVersion: text(source.schema_version, '1.0'), heartbeatId: text(source.heartbeat_id, text(source.anchor_id)),
    emittedAt: timestamp(source.emitted_at), runId: text(source.run_id), deploymentId: text(source.deployment_id),
    buildingId: text(source.building_id), floorId: text(source.floor_id), anchorId: text(source.anchor_id),
    nodeKind: text(source.node_kind, 'anchor'), mode: adaptMode(source.mode), status: adaptStatus(source.status, captureOk),
    agentVersion: typeof source.agent_version === 'string' ? source.agent_version : undefined,
    uptimeS: Math.max(0, Math.round(number(source.uptime_s))), bufferDepth: Math.max(0, Math.round(number(source.buffer_depth))),
    observationsSentTotal: Math.max(0, Math.round(number(source.observations_sent_total))),
    lastObservationAt: typeof source.last_observation_at === 'string' ? source.last_observation_at : null,
    captureOk, errorCodes: Array.isArray(source.error_codes) ? source.error_codes.filter((item): item is string => typeof item === 'string') : [],
  }
}

export function adaptSession(input: unknown): TrackerSessionView {
  const source = asRecord(input)
  const endedAt = typeof source.ended_at === 'string' ? source.ended_at : null
  const rawStatus = text(source.status, endedAt ? 'ended' : 'active').trim().toLowerCase()
  const status: TrackerSessionView['status'] = ['active', 'degraded', 'ended', 'expired', 'silent'].includes(rawStatus)
    ? rawStatus as TrackerSessionView['status']
    : 'unknown'
  return {
    sessionId: text(source.session_id), runId: text(source.run_id), deploymentId: text(source.deployment_id),
    buildingId: text(source.building_id), floorId: text(source.floor_id), mode: adaptMode(source.mode),
    startedAt: timestamp(source.started_at), lastUpdate: timestamp(source.last_update ?? source.started_at), endedAt,
    status, observationCount: Math.max(0, Math.round(number(source.observation_count))),
  }
}

export function adaptEvent(input: unknown): SpatialEvent {
  const source = asRecord(input)
  const metadata = asRecord(source.metadata ?? source.attributes)
  return {
    eventId: text(source.event_id, crypto.randomUUID()), eventType: text(source.event_type, 'POSITION_UPDATED'),
    occurredAt: timestamp(source.occurred_at), emittedAt: timestamp(source.emitted_at), runId: text(source.run_id),
    deploymentId: text(source.deployment_id), buildingId: text(source.building_id), floorId: text(source.floor_id), mode: adaptMode(source.mode),
    sessionId: typeof source.session_id === 'string' ? source.session_id : undefined, zoneId: typeof source.zone_id === 'string' ? source.zone_id : undefined,
    fromZoneId: typeof source.from_zone_id === 'string' ? source.from_zone_id : typeof metadata.from_zone_id === 'string' ? metadata.from_zone_id : undefined,
    toZoneId: typeof source.to_zone_id === 'string' ? source.to_zone_id : typeof metadata.to_zone_id === 'string' ? metadata.to_zone_id : undefined,
    positionId: typeof source.position_id === 'string' ? source.position_id : undefined,
    dwellMs: typeof source.dwell_ms === 'number' ? source.dwell_ms : undefined, occupancyAfter: typeof source.occupancy_after === 'number' ? source.occupancy_after : undefined,
    confidence: typeof source.confidence === 'number' ? source.confidence : undefined,
    eventSequence: Math.max(0, Math.round(number(source.event_sequence))), metadata,
  }
}

export function unwrapData(input: unknown): unknown {
  const source = asRecord(input)
  return 'data' in source ? source.data : input
}

export function adaptState(input: unknown, fallback: Partial<NormalizedState> = {}): NormalizedState {
  const source = asRecord(unwrapData(input))
  const positions = Array.isArray(source.positions) ? source.positions.map(adaptPosition) : []
  const sessions = Array.isArray(source.sessions) ? source.sessions.map(adaptSession) : []
  const nodes = Array.isArray(source.nodes) ? source.nodes.map(adaptNode) : []
  const recentEvents = Array.isArray(source.recent_events) ? source.recent_events.map(adaptEvent) : []
  const rawCounts = asRecord(source.counts)
  const counts: StateCounts = {
    activeSessions: number(rawCounts.active_sessions, positions.length),
    anchorsOnline: number(rawCounts.anchors_online, nodes.filter((node) => node.status === 'online').length),
    anchorsDegraded: number(rawCounts.anchors_degraded, nodes.filter((node) => node.status === 'degraded').length),
    eventsLastHour: number(rawCounts.events_last_hour, recentEvents.length),
  }
  return {
    stateRevision: Math.round(number(source.state_revision, fallback.stateRevision ?? 0)), generatedAt: timestamp(source.generated_at),
    deploymentId: text(source.deployment_id, fallback.deploymentId ?? ''), buildingId: text(source.building_id, fallback.buildingId ?? ''), floorId: text(source.floor_id, fallback.floorId ?? ''),
    runId: text(source.run_id, fallback.runId ?? ''), mode: adaptMode(source.mode ?? fallback.mode), counts,
    sessions, positions, nodes, zones: Array.isArray(source.zone_metrics) ? source.zone_metrics.map((zone) => {
      const item = asRecord(zone); return { zoneId: text(item.zone_id), occupancy: Math.max(0, number(item.occupancy)), dwellSeconds: Math.max(0, number(item.dwell_seconds)), status: (text(item.status, 'clear') as 'clear' | 'active' | 'attention') }
    }) : [], recentEvents, isPartial: bool(source.is_partial, fallback.isPartial ?? false),
  }
}
