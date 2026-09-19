import { describe, expect, it } from 'vitest'
import { demoFloor } from '../domain/floorDefinition'

describe('demo floor definition', () => {
  it('keeps rooms, anchors, and walls within the estimated first-floor footprint', () => {
    expect(demoFloor.widthM).toBeCloseTo(76.9195); expect(demoFloor.depthM).toBeCloseTo(44.6473); expect(demoFloor.anchors).toHaveLength(4)
    expect(new Set(demoFloor.anchors.map((anchor) => anchor.anchorId)).size).toBe(4)
    for (const room of demoFloor.rooms) { expect(room.xM).toBeGreaterThanOrEqual(0); expect(room.yM).toBeGreaterThanOrEqual(0); expect(room.xM + room.widthM).toBeLessThanOrEqual(demoFloor.widthM); expect(room.yM + room.depthM).toBeLessThanOrEqual(demoFloor.depthM) }
    for (const anchor of demoFloor.anchors) { expect(anchor.xM).toBeGreaterThanOrEqual(0); expect(anchor.xM).toBeLessThanOrEqual(demoFloor.widthM); expect(anchor.yM).toBeGreaterThanOrEqual(0); expect(anchor.yM).toBeLessThanOrEqual(demoFloor.depthM) }
  })
})
