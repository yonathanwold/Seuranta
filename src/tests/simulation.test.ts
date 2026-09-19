import { describe, expect, it } from 'vitest'
import { defaultRoomConfig, type RoomModelConfig } from '../domain/roomModel'
import { routeForConfig, validateSimulationRoutes } from '../domain/simulation'

describe('Virginia Tech first-floor simulation', () => {
  it('keeps all closed route segments in the walkable perimeter', () => {
    expect(validateSimulationRoutes(defaultRoomConfig)).toEqual([])
  })

  it('scales planned routes when the calibrated footprint changes', () => {
    const larger: RoomModelConfig = { ...defaultRoomConfig, measuredWidthM: 100, measuredDepthM: 60, anchors: defaultRoomConfig.anchors }
    const route = routeForConfig('session-a7f3', larger)
    expect(route[0][0]).toBeCloseTo(4.2 * 100 / 76.91949950158596)
    expect(route[0][1]).toBeCloseTo(25.5 * 60 / 44.64731623977423)
    expect(validateSimulationRoutes(larger)).toEqual([])
  })
})
