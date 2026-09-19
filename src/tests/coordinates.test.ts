import { describe, expect, it } from 'vitest'
import { mapToWorld, worldToMap } from '../domain/coordinates'

describe('coordinate transform', () => {
  const origin = { xM: 16, yM: 11 }
  it('maps backend x/y to world x/-z in metres', () => expect(mapToWorld({ xM: 18, yM: 8 }, origin, 0.5)).toEqual({ x: 2, y: 0.5, z: 3 }))
  it('round trips world points through the UI transform', () => {
    const point = { xM: 6.25, yM: 19.75 }
    const world = mapToWorld(point, origin, 0.2)
    expect(worldToMap(world, origin)).toEqual(point)
  })
})
