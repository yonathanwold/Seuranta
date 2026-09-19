import { describe, expect, it } from 'vitest'
import { mapToRoomAsset, mapToWorld, roomAssetToMap, worldToMap } from '../domain/coordinates'
import { defaultRoomConfig, roomDimensions } from '../domain/roomModel'

describe('coordinate transform', () => {
  const origin = { xM: 16, yM: 11 }
  it('maps backend x/y to world x/-z in metres', () => expect(mapToWorld({ xM: 18, yM: 8 }, origin, 0.5)).toEqual({ x: 2, y: 0.5, z: 3 }))
  it('round trips world points through the UI transform', () => {
    const point = { xM: 6.25, yM: 19.75 }
    const world = mapToWorld(point, origin, 0.2)
    expect(worldToMap(world, origin)).toEqual(point)
  })
  it('maps calibrated room boundaries to the model centreline in world metres', () => {
    const dimensions = roomDimensions(defaultRoomConfig)
    const lower = mapToRoomAsset({ xM: 0, yM: 0 }, defaultRoomConfig)
    const upper = mapToRoomAsset({ xM: dimensions.widthM, yM: dimensions.depthM }, defaultRoomConfig)
    expect(lower.x).toBeCloseTo(-dimensions.widthM / 2)
    expect(lower.z).toBeCloseTo(dimensions.depthM / 2)
    expect(upper.x).toBeCloseTo(dimensions.widthM / 2)
    expect(upper.z).toBeCloseTo(-dimensions.depthM / 2)
    expect(roomAssetToMap(lower, defaultRoomConfig)).toEqual({ xM: 0, yM: 0 })
    expect(roomAssetToMap(upper, defaultRoomConfig)).toEqual({ xM: dimensions.widthM, yM: dimensions.depthM })
  })
})
