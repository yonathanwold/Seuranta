export type NormalizedMode = 'LIVE' | 'REPLAY' | 'SIMULATION'
export type EntityStatus = 'online' | 'degraded' | 'offline'
export type ProviderStatus = 'connecting' | 'live' | 'reconnecting' | 'offline' | 'error'

export interface Organization {
  organizationId: string
  name: string
  sites: Site[]
}

export interface Site {
  siteId: string
  name: string
  buildings: Building[]
}

export interface Building {
  buildingId: string
  name: string
  floors: Floor[]
}

export interface Floor {
  floorId: string
  name: string
  level: number
  definitionId: string
}

export interface PositionEstimate {
  schemaVersion: string
  positionId: string
  calculatedAt: string
  windowStart: string
  windowEnd: string
  runId: string
  deploymentId: string
  buildingId: string
  floorId: string
  sessionId: string
  rawXM: number
  rawYM: number
  xM: number
  yM: number
  zoneId: string | null
  confidence: number
  accuracyRadiusM: number
  positionMethod: string
  smoothingMethod: string
  anchorsUsed: string[]
  observationCount: number
  mode: NormalizedMode
  sequenceNumber: number
  isOutsideMap: boolean
}

export interface SpatialEvent {
  eventId: string
  eventType: string
  occurredAt: string
  emittedAt: string
  runId: string
  deploymentId: string
  buildingId: string
  floorId: string
  mode: NormalizedMode
  sessionId?: string
  zoneId?: string
  fromZoneId?: string
  toZoneId?: string
  positionId?: string
  dwellMs?: number
  occupancyAfter?: number
  confidence?: number
  eventSequence: number
  metadata: Record<string, unknown>
}

export interface NodeHeartbeat {
  schemaVersion: string
  heartbeatId: string
  emittedAt: string
  runId: string
  deploymentId: string
  buildingId: string
  floorId: string
  anchorId: string
  nodeKind: string
  mode: NormalizedMode
  status: EntityStatus
  agentVersion?: string
  uptimeS: number
  bufferDepth: number
  observationsSentTotal: number
  lastObservationAt: string | null
  captureOk: boolean
  errorCodes: string[]
}

export interface ZoneMetric {
  zoneId: string
  occupancy: number
  dwellSeconds: number
  status: 'clear' | 'active' | 'attention'
}

export interface StateCounts {
  activeSessions: number
  anchorsOnline: number
  anchorsDegraded: number
  eventsLastHour: number
  [key: string]: number
}

export interface NormalizedState {
  stateRevision: number
  generatedAt: string
  deploymentId: string
  buildingId: string
  floorId: string
  runId: string
  mode: NormalizedMode
  counts: StateCounts
  positions: PositionEstimate[]
  nodes: NodeHeartbeat[]
  zones: ZoneMetric[]
  recentEvents: SpatialEvent[]
  isPartial: boolean
}

export interface ProviderSnapshot {
  state: NormalizedState
  providerStatus: ProviderStatus
  lastError?: string
}

export interface PositionProvider {
  readonly kind: 'mock' | 'live'
  start(listener: (snapshot: ProviderSnapshot) => void): void
  stop(): void
  refresh(): Promise<void>
}
