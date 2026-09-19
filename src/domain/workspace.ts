import type { AnchorDefinition } from './floorDefinition'
import type { NormalizedState, NodeHeartbeat, PositionEstimate, SpatialEvent } from './types'
import type { RoomModelConfig } from './roomModel'

export type WorkspaceDeviceStatus = 'online' | 'degraded' | 'offline'
export type WorkspaceSpaceStatus = 'available' | 'occupied' | 'attention'
export type WorkspaceEventSeverity = 'critical' | 'warning' | 'info'
export type WorkspaceEventStatus = 'active' | 'resolved'

export interface WorkspaceSpace {
  id: string
  zoneId: string
  name: string
  type: string
  capacity: number
  occupancy: number
  status: WorkspaceSpaceStatus
}

export interface WorkspaceDevice {
  id: string
  sessionId: string
  type: 'Tracked device'
  status: WorkspaceDeviceStatus
  lastSeen: string
  battery: number
  signal: 'Strong' | 'Good' | 'Weak'
  spaceId: string
  spaceName: string
  tags: string[]
  xM: number
  yM: number
  confidence: number
  accuracyRadiusM: number
  position: PositionEstimate
}

export interface WorkspaceAnchor {
  anchor: AnchorDefinition
  node?: NodeHeartbeat
}

export interface WorkspaceEvent {
  id: string
  title: string
  severity: WorkspaceEventSeverity
  status: WorkspaceEventStatus
  sourceId: string
  sourceLabel: string
  spaceId: string
  spaceName: string
  occurredAt: string
  description: string
  event: SpatialEvent
}

export interface WorkspaceModel {
  devices: WorkspaceDevice[]
  anchors: WorkspaceAnchor[]
  spaces: WorkspaceSpace[]
  events: WorkspaceEvent[]
  onlineDevices: number
  degradedDevices: number
  offlineDevices: number
  averageConfidence: number
  eventsLastHour: number
}

const spaceCatalog: Array<Omit<WorkspaceSpace, 'occupancy' | 'status'>> = [
  { id: 'circulation', zoneId: 'main-circulation', name: 'Main circulation', type: 'Shared area', capacity: 8 },
  { id: 'room-101a', zoneId: 'classroom-west', name: 'Room 101A', type: 'Active-learning classroom', capacity: 24 },
  { id: 'room-102b', zoneId: 'classroom-center', name: 'Room 102B', type: 'Instructional classroom', capacity: 24 },
  { id: 'lecture-hall', zoneId: 'lecture-hall', name: 'Lecture hall', type: 'Lecture space', capacity: 48 },
  { id: 'room-103', zoneId: 'collaborative-classroom', name: 'Room 103', type: 'Collaborative classroom', capacity: 18 },
  { id: 'south-commons', zoneId: 'south-social', name: 'South commons', type: 'Open collaboration area', capacity: 20 },
]

const deviceLabel = (sessionId: string): string => sessionId.replace(/^session-/, '').slice(0, 4).toUpperCase()
const formatTimestamp = (timestamp: string): string => new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(timestamp))

function eventDetails(event: SpatialEvent, device: WorkspaceDevice | undefined, space: WorkspaceSpace): Pick<WorkspaceEvent, 'title' | 'severity' | 'description'> {
  if (event.eventType === 'SESSION_STARTED') return { title: 'Device session started', severity: 'info', description: `${device?.id ?? event.sessionId ?? 'Anonymous device'} started a positioning session in ${space.name}.` }
  if (event.eventType.includes('ZONE')) return { title: 'Device moved between spaces', severity: 'info', description: `${device?.id ?? 'Anonymous device'} moved through ${space.name}.` }
  if (event.eventType.includes('HEARTBEAT')) return { title: 'Anchor heartbeat received', severity: 'info', description: `The ${event.metadata.anchor_label ?? 'anchor'} reported a healthy heartbeat.` }
  return { title: event.eventType.replaceAll('_', ' ').toLowerCase().replace(/(^|\s)\S/g, (letter) => letter.toUpperCase()), severity: event.confidence !== undefined && event.confidence < 0.6 ? 'warning' : 'info', description: `The positioning pipeline reported an update for ${space.name}.` }
}

export function buildWorkspace(snapshot: NormalizedState, roomConfig: RoomModelConfig): WorkspaceModel {
  const baseSpaces = spaceCatalog.map((space) => ({ ...space, occupancy: snapshot.positions.filter((position) => position.zoneId === space.zoneId).length, status: 'available' as WorkspaceSpaceStatus }))
  const spaces: WorkspaceSpace[] = baseSpaces.map((space) => ({ ...space, status: (space.occupancy > space.capacity ? 'attention' : space.occupancy > space.capacity * 0.72 ? 'occupied' : 'available') as WorkspaceSpaceStatus }))
  const spaceMap = new Map(spaces.map((space) => [space.zoneId, space]))
  const devices = snapshot.positions.map((position, index): WorkspaceDevice => {
    const space = spaceMap.get(position.zoneId ?? '') ?? spaces[0]
    const status: WorkspaceDeviceStatus = index === snapshot.positions.length - 1 ? 'offline' : position.confidence < 0.72 || index % 9 === 7 ? 'degraded' : 'online'
    const signal: WorkspaceDevice['signal'] = position.confidence >= 0.84 ? 'Strong' : position.confidence >= 0.72 ? 'Good' : 'Weak'
    return {
      id: deviceLabel(position.sessionId), sessionId: position.sessionId, type: 'Tracked device', status,
      lastSeen: formatTimestamp(position.calculatedAt), battery: Math.max(12, 96 - ((index * 7) % 84)), signal,
      spaceId: space.id, spaceName: space.name, tags: [space.type, position.mode === 'SIMULATION' ? 'Simulation' : 'Live position'],
      xM: position.xM, yM: position.yM, confidence: position.confidence, accuracyRadiusM: position.accuracyRadiusM, position,
    }
  })
  const deviceMap = new Map(devices.map((device) => [device.sessionId, device]))
  const anchors = roomConfig.anchors.map((anchor) => ({ anchor, node: snapshot.nodes.find((node) => node.anchorId === anchor.anchorId) }))
  const events = snapshot.recentEvents.map((event, index): WorkspaceEvent => {
    const device = event.sessionId ? deviceMap.get(event.sessionId) : undefined
    const space = spaceMap.get(event.zoneId ?? device?.position.zoneId ?? '') ?? spaces[0]
    const details = eventDetails(event, device, space)
    return { id: event.eventId, ...details, severity: device?.status === 'degraded' ? 'warning' : details.severity, status: index === 0 ? 'active' : 'resolved', sourceId: device?.id ?? event.sessionId ?? 'SYSTEM', sourceLabel: device?.id ?? event.sessionId ?? 'System', spaceId: space.id, spaceName: space.name, occurredAt: formatTimestamp(event.occurredAt), event }
  })
  const averageConfidence = devices.length ? devices.reduce((sum, device) => sum + device.confidence, 0) / devices.length : 0
  return {
    devices, anchors, spaces, events, onlineDevices: devices.filter((device) => device.status === 'online').length,
    degradedDevices: devices.filter((device) => device.status === 'degraded').length,
    offlineDevices: devices.filter((device) => device.status === 'offline').length,
    averageConfidence, eventsLastHour: events.length,
  }
}
