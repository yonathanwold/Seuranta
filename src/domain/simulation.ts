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
}

const referenceDimensions = { widthM: PHOTO_ROOM_ASSET.nativeWidthM, depthM: PHOTO_ROOM_ASSET.nativeDepthM }

export const sessionZones: Record<string, string> = {
  'session-a7f3': 'main-circulation',
  'session-b9d1': 'classroom-west',
  'session-c4e2': 'classroom-center',
  'session-d2a8': 'lecture-hall',
  'session-e5f6': 'collaborative-classroom',
  'session-f8c1': 'south-social',
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

export function isWalkablePoint(xM: number, yM: number, config: RoomModelConfig): boolean {
  const { widthM, depthM } = roomDimensions(config)
  return xM >= 0 && xM <= widthM && yM >= 0 && yM <= depthM
}

export function validateSimulationRoutes(config: RoomModelConfig): string[] {
  const errors: string[] = []
  for (const [sessionId] of Object.entries(simulationRoutes)) {
    const scaledRoute = routeForConfig(sessionId, config)
    if (scaledRoute.length < 2) errors.push(`${sessionId} has fewer than two route points.`)
    for (const [xM, yM] of scaledRoute) if (!isWalkablePoint(xM, yM, config)) errors.push(`${sessionId} contains a point outside the floor (${xM}, ${yM}).`)
    for (let index = 0; index < scaledRoute.length; index += 1) {
      const start = scaledRoute[index]
      const end = scaledRoute[(index + 1) % scaledRoute.length]
      for (let step = 1; step < 8; step += 1) {
        const amount = step / 8
        if (!isWalkablePoint(start[0] + (end[0] - start[0]) * amount, start[1] + (end[1] - start[1]) * amount, config)) errors.push(`${sessionId} segment ${index} leaves the floor.`)
      }
    }
  }
  return errors
}
