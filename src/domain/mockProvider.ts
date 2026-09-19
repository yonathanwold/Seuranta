import type { NodeHeartbeat, NormalizedState, PositionEstimate, PositionProvider, ProviderSnapshot, SpatialEvent, TrackerSessionView } from './types'
import { demoFloor } from './floorDefinition'
import { roomDimensions, type RoomModelConfig, defaultRoomConfig } from './roomModel'
import { routeForConfig, sessionZones, simulationRoutes, zoneNames, type SimulationScenario } from './simulation'

export interface SimulationControls {
  playing: boolean
  speed: number
  scenario: SimulationScenario
}

const sessionIds = Object.keys(simulationRoutes)
const nowIso = () => new Date().toISOString()
const interpolate = (route: Array<[number, number]>, phase: number): [number, number] => {
  const scaled = phase * route.length
  const index = Math.floor(scaled) % route.length
  const amount = scaled - index
  const start = route[index]
  const end = route[(index + 1) % route.length]
  return [start[0] + (end[0] - start[0]) * amount, start[1] + (end[1] - start[1]) * amount]
}

export class MockPositionProvider implements PositionProvider {
  readonly kind = 'mock' as const
  private timer: ReturnType<typeof setInterval> | undefined
  private listener: ((snapshot: ProviderSnapshot) => void) | undefined
  private tick = 0
  private revision = 0
  private events: SpatialEvent[] = []
  private readonly roomConfig: RoomModelConfig
  private controls: SimulationControls = { playing: true, speed: 1, scenario: 'walkthrough' }
  private lastGeneratedAt = nowIso()

  constructor(roomConfig: RoomModelConfig = defaultRoomConfig) { this.roomConfig = roomConfig }

  start(listener: (snapshot: ProviderSnapshot) => void): void {
    this.listener = listener
    this.controls.playing = true
    listener({ state: this.createState(), providerStatus: 'live' })
    this.startTimer()
  }

  stop(): void { this.clearTimer(); this.listener = undefined }
  async refresh(): Promise<void> { if (this.controls.playing) this.emit() }
  getSimulationControls(): SimulationControls { return { ...this.controls } }

  setPlaying(playing: boolean): void {
    this.controls.playing = playing
    if (playing) this.startTimer(); else this.clearTimer()
    this.emit()
  }

  setSpeed(speed: number): void {
    this.controls.speed = Math.min(2, Math.max(0.25, speed))
    if (this.controls.playing) this.startTimer()
    this.emit()
  }

  setScenario(scenario: SimulationScenario): void {
    this.controls.scenario = scenario
    this.revision += 1
    this.emit()
  }

  restart(): void {
    this.tick = 0
    this.revision += 1
    this.events = []
    this.emit()
  }

  private startTimer(): void {
    this.clearTimer()
    this.timer = setInterval(() => this.emit(), Math.round(700 / this.controls.speed))
  }

  private clearTimer(): void { if (this.timer) clearInterval(this.timer); this.timer = undefined }
  private emit(): void {
    if (this.controls.playing) this.tick += 1
    this.revision += 1
    this.listener?.({ state: this.createState(), providerStatus: 'live' })
  }

  private createState(): NormalizedState {
    const generatedAt = this.controls.playing || this.tick === 0 ? nowIso() : this.lastGeneratedAt
    this.lastGeneratedAt = generatedAt
    const dimensions = roomDimensions(this.roomConfig)
    const positions: PositionEstimate[] = sessionIds.map((sessionId, index) => {
      const route = routeForConfig(sessionId, this.roomConfig)
      const phase = ((this.tick * 0.009 + index * 0.24) % 1)
      const [xM, yM] = interpolate(route, phase)
      const weakSignal = this.controls.scenario === 'weak-signal' && index === 1
      const confidence = Math.max(0.68, (weakSignal ? 0.68 : 0.94) - index * 0.012)
      const accuracyRadiusM = weakSignal ? 1.25 : 0.45 + (index % 6) * 0.06
      return {
        schemaVersion: '1.0', positionId: `${sessionId}-${this.tick}`, calculatedAt: generatedAt, windowStart: generatedAt, windowEnd: generatedAt,
        runId: 'demo-run-2026-09-19', deploymentId: 'demo-deployment', buildingId: demoFloor.buildingId, floorId: demoFloor.floorId, sessionId,
        rawXM: xM + Math.sin(this.tick * 0.1 + index) * 0.14, rawYM: yM + Math.cos(this.tick * 0.11 + index) * 0.14, xM, yM, zoneId: sessionZones[sessionId],
        confidence, accuracyRadiusM, positionMethod: 'demo-route', smoothingMethod: 'EMA', anchorsUsed: this.roomConfig.anchors.slice(0, index === 1 ? 2 : 4).map((anchor) => anchor.anchorId), observationCount: 8 + index,
        mode: 'SIMULATION', sequenceNumber: this.tick, isOutsideMap: xM < this.roomConfig.originXM || xM > this.roomConfig.originXM + dimensions.widthM || yM < this.roomConfig.originYM || yM > this.roomConfig.originYM + dimensions.depthM,
      }
    })
    if ((this.tick === 0 || this.tick === 1) && this.events.length === 0) {
      this.events = positions.map((position, index) => ({
        eventId: `${position.sessionId}-started`, eventType: 'SESSION_STARTED', occurredAt: generatedAt, emittedAt: generatedAt,
        runId: 'demo-run-2026-09-19', deploymentId: 'demo-deployment', buildingId: demoFloor.buildingId, floorId: demoFloor.floorId,
        mode: 'SIMULATION' as const, sessionId: position.sessionId, zoneId: position.zoneId ?? undefined, toZoneId: position.zoneId ?? undefined, eventSequence: index + 1, confidence: position.confidence, metadata: { source: 'simulation' },
      }))
    }
    const weakAnchor = this.controls.scenario === 'weak-signal' ? this.roomConfig.anchors[1]?.anchorId : undefined
    const nodes: NodeHeartbeat[] = this.roomConfig.anchors.map((anchor, index) => {
      const degraded = weakAnchor === anchor.anchorId
      return {
        schemaVersion: '1.0', heartbeatId: `heartbeat-${anchor.anchorId}-${this.tick}`, emittedAt: generatedAt, runId: 'demo-run-2026-09-19', deploymentId: 'demo-deployment',
        buildingId: demoFloor.buildingId, floorId: demoFloor.floorId, anchorId: anchor.anchorId, nodeKind: 'planned-anchor', mode: 'SIMULATION', status: degraded ? 'degraded' : 'online',
        agentVersion: 'mock-1.0', uptimeS: 1800 + this.tick * 2, bufferDepth: degraded ? 12 : 0, observationsSentTotal: 1200 + this.tick * 3 + index,
        lastObservationAt: generatedAt, captureOk: !degraded, errorCodes: degraded ? ['WEAK_SIGNAL'] : [],
      }
    })
    const sessions: TrackerSessionView[] = positions.map((position) => ({
      sessionId: position.sessionId, runId: position.runId, deploymentId: position.deploymentId, buildingId: position.buildingId,
      floorId: position.floorId, mode: position.mode, startedAt: position.calculatedAt, lastUpdate: position.calculatedAt,
      endedAt: null, status: 'active', observationCount: position.observationCount,
    }))
    return {
      stateRevision: this.revision, generatedAt, deploymentId: 'demo-deployment', buildingId: demoFloor.buildingId, floorId: demoFloor.floorId, runId: 'demo-run-2026-09-19', mode: 'SIMULATION',
      counts: { activeSessions: positions.length, anchorsOnline: nodes.filter((node) => node.status === 'online').length, anchorsDegraded: nodes.filter((node) => node.status === 'degraded').length, eventsLastHour: this.events.length },
      sessions, positions, nodes, zones: Object.entries(zoneNames).map(([zoneId]) => ({ zoneId, occupancy: positions.filter((position) => position.zoneId === zoneId).length, dwellSeconds: Math.round(this.tick * 0.7), status: 'active' })), recentEvents: this.events.slice(0, 8), isPartial: false,
    }
  }
}
