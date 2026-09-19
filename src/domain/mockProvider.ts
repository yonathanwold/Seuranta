import type { NodeHeartbeat, NormalizedState, PositionEstimate, PositionProvider, ProviderSnapshot, SpatialEvent } from './types'
import { demoFloor } from './floorDefinition'

const sessionIds = ['session-a7f3', 'session-b9d1', 'session-c4e2', 'session-d8f6', 'session-e1a9']
const routePoints: Array<Array<[number, number]>> = [
  [[5.5, 11.2], [11, 11.2], [18, 11.2], [22, 13], [24.5, 16.5], [21.5, 13]],
  [[8.5, 12.7], [12.5, 12.7], [15.5, 12.7], [15.5, 6], [12.5, 6], [10.5, 12.5]],
  [[4.8, 5.6], [8.2, 5.6], [11, 10.8], [18.5, 10.8], [20.5, 6], [17.8, 5.4]],
  [[19, 17], [23, 17], [27, 17], [27, 12], [23.5, 11], [18.8, 12]],
  [[25, 5.5], [23.5, 8.5], [19, 10], [14, 10], [8.5, 11], [6.5, 16.5]],
]

const nowIso = () => new Date().toISOString()
const interpolate = (route: Array<[number, number]>, phase: number): [number, number] => {
  const scaled = phase * (route.length - 1)
  const index = Math.min(route.length - 2, Math.floor(scaled))
  const amount = scaled - index
  const start = route[index]
  const end = route[index + 1]
  return [start[0] + (end[0] - start[0]) * amount, start[1] + (end[1] - start[1]) * amount]
}

const zoneFor = (x: number, y: number): string | null => {
  const room = demoFloor.rooms.find((candidate) => x >= candidate.xM && x <= candidate.xM + candidate.widthM && y >= candidate.yM && y <= candidate.yM + candidate.depthM)
  return room?.zoneId ?? (y >= 9.2 && y <= 15.2 ? 'corridor' : null)
}

export class MockPositionProvider implements PositionProvider {
  readonly kind = 'mock' as const
  private timer: ReturnType<typeof setInterval> | undefined
  private listener: ((snapshot: ProviderSnapshot) => void) | undefined
  private tick = 0
  private revision = 0
  private events: SpatialEvent[] = []
  private previousZones = new Map<string, string | null>()

  start(listener: (snapshot: ProviderSnapshot) => void): void {
    this.listener = listener
    listener({ state: this.createState(), providerStatus: 'live' })
    this.timer = setInterval(() => this.emit(), 700)
  }

  stop(): void { if (this.timer) clearInterval(this.timer); this.timer = undefined; this.listener = undefined }
  async refresh(): Promise<void> { this.emit() }

  private emit(): void { this.tick += 1; this.revision += 1; this.listener?.({ state: this.createState(), providerStatus: 'live' }) }

  private createState(): NormalizedState {
    const generatedAt = nowIso()
    const positions: PositionEstimate[] = sessionIds.map((sessionId, index) => {
      const phase = ((this.tick * 0.008 + index * 0.17) % 1)
      const [xM, yM] = interpolate(routePoints[index], phase)
      const zoneId = zoneFor(xM, yM)
      const previousZone = this.previousZones.get(sessionId)
      if (previousZone !== undefined && previousZone !== zoneId && zoneId) {
        this.events = [{
          eventId: `${sessionId}-${this.tick}`, eventType: 'ZONE_ENTERED', occurredAt: generatedAt, emittedAt: generatedAt,
          runId: 'demo-run-2026-09-19', deploymentId: 'demo-deployment', buildingId: demoFloor.buildingId, floorId: demoFloor.floorId,
          mode: 'SIMULATION' as const, sessionId, zoneId, fromZoneId: previousZone ?? undefined, toZoneId: zoneId, eventSequence: this.tick,
          confidence: 0.86 - index * 0.04, metadata: {},
        }, ...this.events].slice(0, 7)
      }
      this.previousZones.set(sessionId, zoneId)
      return {
        schemaVersion: '1.0', positionId: `${sessionId}-${this.tick}`, calculatedAt: generatedAt, windowStart: generatedAt, windowEnd: generatedAt,
        runId: 'demo-run-2026-09-19', deploymentId: 'demo-deployment', buildingId: demoFloor.buildingId, floorId: demoFloor.floorId, sessionId,
        rawXM: xM + Math.sin(this.tick * 0.1 + index) * 0.12, rawYM: yM + Math.cos(this.tick * 0.11 + index) * 0.12, xM, yM, zoneId,
        confidence: 0.91 - index * 0.055, accuracyRadiusM: 0.8 + index * 0.18, positionMethod: 'mock-route', smoothingMethod: 'EMA',
        anchorsUsed: ['a-01', 'a-02', 'a-03'].slice(0, index % 2 === 0 ? 3 : 2), observationCount: 10 + index, mode: 'SIMULATION', sequenceNumber: this.tick, isOutsideMap: false,
      }
    })
    const statuses: NodeHeartbeat['status'][] = ['online', 'degraded', 'online', 'degraded']
    const nodes: NodeHeartbeat[] = demoFloor.anchors.map((anchor, index) => ({
      schemaVersion: '1.0', heartbeatId: `heartbeat-${anchor.anchorId}-${this.tick}`, emittedAt: generatedAt, runId: 'demo-run-2026-09-19', deploymentId: 'demo-deployment',
      buildingId: demoFloor.buildingId, floorId: demoFloor.floorId, anchorId: anchor.anchorId, nodeKind: 'wifi-monitor', mode: 'SIMULATION', status: statuses[index],
      agentVersion: 'mock-1.0', uptimeS: 86400 + this.tick * 2, bufferDepth: statuses[index] === 'degraded' ? 7 : 0, observationsSentTotal: 18024 + this.tick,
      lastObservationAt: generatedAt, captureOk: statuses[index] !== 'offline', errorCodes: statuses[index] === 'degraded' ? ['BUFFER_BACKLOG'] : [],
    }))
    return {
      stateRevision: this.revision, generatedAt, deploymentId: 'demo-deployment', buildingId: demoFloor.buildingId, floorId: demoFloor.floorId, runId: 'demo-run-2026-09-19', mode: 'SIMULATION',
      counts: { activeSessions: positions.length, anchorsOnline: 2, anchorsDegraded: 2, eventsLastHour: 14 }, positions, nodes, zones: demoFloor.zones.map((zone) => ({ zoneId: zone.zoneId, occupancy: positions.filter((position) => position.zoneId === zone.zoneId).length, dwellSeconds: 82 + zone.zoneId.length * 9, status: positions.some((position) => position.zoneId === zone.zoneId) ? 'active' : 'clear' })), recentEvents: this.events,
      isPartial: false,
    }
  }
}
