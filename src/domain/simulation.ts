import { PHOTO_ROOM_ASSET, roomDimensions, type RoomModelConfig } from './roomModel'

export type SimulationScenario = 'walkthrough' | 'weak-signal'

/**
 * Loops traced from the first-floor plan in the supplied metadata. They keep
 * movement inside circulation and learning spaces instead of walking through
 * the building envelope. Coordinates are metres in the floor-local grid.
 */
export const simulationRoutes: Record<string, Array<[number, number]>> = {
  'session-a7f3': [[4.2, 25.5], [10.5, 28.5], [27, 28.8], [45, 27.2], [62, 25.4], [69.5, 27], [61, 30], [42, 27.4], [20, 24], [8.5, 22]],
  'session-b9d1': [[20, 35], [30, 35], [30, 41], [20, 41]],
  'session-c4e2': [[34, 35], [45, 35], [45, 41], [34, 41]],
  'session-d2a8': [[19, 12], [31, 11], [34, 19], [21, 20]],
  'session-e5f6': [[39, 11], [52, 10], [55, 18], [45, 20], [39, 17]],
  'session-f8c1': [[54, 18], [63, 19], [62, 24], [54, 23]],
  'session-g3b7': [[8, 32], [14, 34], [18, 31], [12, 29]],
  'session-h6d2': [[27, 36], [33, 36], [33, 41], [28, 41]],
  'session-j1e8': [[48, 36], [56, 36], [56, 41], [48, 41]],
  'session-k5f4': [[18, 13], [27, 12], [31, 18], [22, 20]],
  'session-l2c9': [[27, 8], [34, 9], [34, 16], [28, 16]],
  'session-m8a1': [[45, 8], [52, 8], [54, 14], [47, 15]],
  'session-n4d6': [[58, 8], [66, 10], [67, 17], [60, 17]],
  'session-p7b3': [[66, 19], [73, 20], [73, 26], [67, 25]],
  'session-q9e5': [[17, 34], [24, 34], [26, 39], [19, 39]],
  'session-r6f2': [[36, 34], [42, 33], [48, 37], [43, 40]],
  'session-s3c8': [[47, 14], [55, 14], [58, 20], [51, 21]],
  'session-t5a4': [[14, 34], [22, 34], [24, 40], [16, 40]],
  'session-u8d1': [[54, 14], [64, 15], [66, 21], [58, 23]],
  'session-v2b7': [[39, 18], [44, 18], [47, 22], [40, 23]],
}

const referenceDimensions = { widthM: PHOTO_ROOM_ASSET.nativeWidthM, depthM: PHOTO_ROOM_ASSET.nativeDepthM }

export const sessionZones: Record<string, string> = {
  'session-a7f3': 'main-circulation',
  'session-b9d1': 'classroom-west',
  'session-c4e2': 'classroom-center',
  'session-d2a8': 'lecture-hall',
  'session-e5f6': 'collaborative-classroom',
  'session-f8c1': 'south-social',
  'session-g3b7': 'main-circulation',
  'session-h6d2': 'classroom-west',
  'session-j1e8': 'classroom-center',
  'session-k5f4': 'lecture-hall',
  'session-l2c9': 'lecture-hall',
  'session-m8a1': 'collaborative-classroom',
  'session-n4d6': 'south-social',
  'session-p7b3': 'main-circulation',
  'session-q9e5': 'classroom-west',
  'session-r6f2': 'classroom-center',
  'session-s3c8': 'collaborative-classroom',
  'session-t5a4': 'classroom-west',
  'session-u8d1': 'south-social',
  'session-v2b7': 'collaborative-classroom',
}

export const zoneNames: Record<string, string> = {
  'main-circulation': 'Main circulation',
  'classroom-west': 'West active-learning classroom',
  'classroom-center': 'Central instructional classroom',
  'lecture-hall': 'Lecture / auditorium',
  'collaborative-classroom': 'Curved collaborative classroom',
  'south-social': 'Open collaboration area',
}

export function routeForConfig(sessionId: string, config: RoomModelConfig): Array<[number, number]> {
  const route = simulationRoutes[sessionId] ?? []
  const dimensions = roomDimensions(config)
  return route.map(([xM, yM]) => [xM * dimensions.widthM / referenceDimensions.widthM, yM * dimensions.depthM / referenceDimensions.depthM])
}

interface WalkableRegion { minX: number; maxX: number; minY: number; maxY: number }

// These are intentionally simple navigation envelopes, not a replacement for
// the positioning team's floor graph. They follow the visible first-floor
// rooms and corridors, leave the exterior blocked, and overlap at doorway
// bands so a route can move between a room and circulation without crossing a
// wall. Coordinates are percentages of the calibrated footprint so a measured
// setup scales them with the rest of the demo.
const walkableRegions: WalkableRegion[] = [
  { minX: 0.03, maxX: 0.97, minY: 0.42, maxY: 0.78 },
  { minX: 0.13, maxX: 0.43, minY: 0.66, maxY: 0.97 },
  { minX: 0.41, maxX: 0.74, minY: 0.66, maxY: 0.97 },
  { minX: 0.14, maxX: 0.47, minY: 0.15, maxY: 0.55 },
  { minX: 0.44, maxX: 0.76, minY: 0.15, maxY: 0.58 },
  { minX: 0.66, maxX: 0.95, minY: 0.15, maxY: 0.60 },
]

const zoneRegions: Record<string, WalkableRegion[]> = {
  'main-circulation': [walkableRegions[0]],
  'classroom-west': [walkableRegions[1]],
  'classroom-center': [walkableRegions[2]],
  'lecture-hall': [walkableRegions[3]],
  'collaborative-classroom': [walkableRegions[4]],
  'south-social': [walkableRegions[5]],
}

const inRegion = (x: number, y: number, region: WalkableRegion): boolean => x >= region.minX && x <= region.maxX && y >= region.minY && y <= region.maxY

export function isWalkablePoint(xM: number, yM: number, config: RoomModelConfig, zoneId?: string): boolean {
  const { widthM, depthM } = roomDimensions(config)
  if (xM < 0 || xM > widthM || yM < 0 || yM > depthM) return false
  const normalizedX = xM / widthM
  const normalizedY = yM / depthM
  const regions = zoneId ? zoneRegions[zoneId] ?? walkableRegions : walkableRegions
  return regions.some((region) => inRegion(normalizedX, normalizedY, region))
}

export function validateSimulationRoutes(config: RoomModelConfig): string[] {
  const errors: string[] = []
  for (const [sessionId] of Object.entries(simulationRoutes)) {
    const scaledRoute = routeForConfig(sessionId, config)
    if (scaledRoute.length < 2) errors.push(`${sessionId} has fewer than two route points.`)
    const zoneId = sessionZones[sessionId]
    for (const [xM, yM] of scaledRoute) if (!isWalkablePoint(xM, yM, config, zoneId)) errors.push(`${sessionId} contains a point outside its walkable ${zoneId ?? 'floor'} region (${xM}, ${yM}).`)
    for (let index = 0; index < scaledRoute.length; index += 1) {
      const start = scaledRoute[index]
      const end = scaledRoute[(index + 1) % scaledRoute.length]
      for (let step = 1; step < 8; step += 1) {
        const amount = step / 8
        if (!isWalkablePoint(start[0] + (end[0] - start[0]) * amount, start[1] + (end[1] - start[1]) * amount, config, zoneId)) errors.push(`${sessionId} segment ${index} leaves its walkable region.`)
      }
    }
  }
  return errors
}
