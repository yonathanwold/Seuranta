import { describe, expect, it } from 'vitest'
import { defaultRoomConfig } from '../domain/roomModel'
import { isWalkthroughPoint, moveWithinFloor, walkthroughStart } from '../domain/walkthrough'
import { validateSimulationRoutes } from '../domain/simulation'

describe('walkthrough floor envelope', () => {
  it('stays walkable when driven into every outer edge and cutout', () => {
    const config = defaultRoomConfig
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1], [-1, -1], [1, 1], [-1, 1], [1, -1]]) {
      let point = walkthroughStart(config)
      for (let step = 0; step < 1200; step += 1) {
        point = moveWithinFloor(point, { xM: point.xM + dx, yM: point.yM + dy }, config)
        expect(isWalkthroughPoint(point, config)).toBe(true)
      }
    }
  })
  it('caps long frame jumps and rejects invalid coordinates', () => {
    const start = walkthroughStart(defaultRoomConfig)
    const moved = moveWithinFloor(start, { xM: 10000, yM: 10000 }, defaultRoomConfig)
    expect(Math.hypot(moved.xM - start.xM, moved.yM - start.yM)).toBeLessThanOrEqual(0.50001)
    expect(moveWithinFloor(start, { xM: NaN, yM: 0 }, defaultRoomConfig)).toEqual(start)
  })
  it('uses calibrated dimensions and nonzero origins consistently with routes', () => {
    const config = { ...defaultRoomConfig, originXM: -100, originYM: 80, yawDeg: 45, measuredWidthM: 100, measuredDepthM: 60 }
    expect(validateSimulationRoutes(config)).toEqual([])
    let point = walkthroughStart(config)
    for (let i = 0; i < 1000; i += 1) {
      point = moveWithinFloor(point, { xM: point.xM - 1, yM: point.yM - 1 }, config)
      expect(isWalkthroughPoint(point, config)).toBe(true)
    }
    expect(point.xM).toBeGreaterThan(config.originXM)
    expect(point.yM).toBeGreaterThan(config.originYM)
  })
})
