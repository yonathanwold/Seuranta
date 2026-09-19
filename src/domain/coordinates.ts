import type { PositionEstimate } from './types'
import { PHOTO_ROOM_ASSET, roomAssetScaleXY, roomDimensions, type RoomModelConfig } from './roomModel'

/**
 * World convention: one Three.js unit equals one backend metre. Backend x_m is
 * world X. Backend y_m is the floor-plan depth and becomes world -Z so north
 * reads toward the top of the elevated view. World Y is vertical height.
 * The floor origin is the centre of the configured floor rectangle.
 */
export interface FloorOrigin { xM: number; yM: number }
export interface WorldPoint { x: number; y: number; z: number }
export interface MapPoint { xM: number; yM: number }

export const mapToWorld = (point: MapPoint, origin: FloorOrigin, height = 0): WorldPoint => ({
  x: point.xM - origin.xM,
  y: height,
  z: -(point.yM - origin.yM),
})

export const worldToMap = (point: WorldPoint, origin: FloorOrigin): MapPoint => ({ xM: point.x + origin.xM, yM: origin.yM - point.z })
export const positionToWorld = (position: Pick<PositionEstimate, 'xM' | 'yM'>, origin: FloorOrigin, height = 0): WorldPoint => mapToWorld({ xM: position.xM, yM: position.yM }, origin, height)

/**
 * Convert backend/map metres into the GLB's local space. The asset is centred
 * at (0, 0, 0), with map y increasing toward the model's south wall. A single
 * transform keeps asset placement, anchors and markers on the same axes.
 */
export function mapToRoomAsset(point: MapPoint, config: RoomModelConfig, height = 0): WorldPoint {
  const dimensions = roomDimensions(config)
  const localX = (point.xM - config.originXM) - dimensions.widthM / 2
  const localZ = -((point.yM - config.originYM) - dimensions.depthM / 2)
  const yaw = config.yawDeg * Math.PI / 180
  // Return calibrated world metres. The model primitive is scaled separately
  // from nominal inner dimensions, so markers do not receive that scale twice.
  const x = localX * Math.cos(yaw) + localZ * Math.sin(yaw)
  const z = -localX * Math.sin(yaw) + localZ * Math.cos(yaw)
  return { x, y: height, z }
}

export function roomAssetToMap(point: WorldPoint, config: RoomModelConfig): MapPoint {
  const dimensions = roomDimensions(config)
  const yaw = -config.yawDeg * Math.PI / 180
  const localX = point.x * Math.cos(yaw) + point.z * Math.sin(yaw)
  const localZ = -point.x * Math.sin(yaw) + point.z * Math.cos(yaw)
  return { xM: localX + config.originXM + dimensions.widthM / 2, yM: config.originYM + dimensions.depthM / 2 - localZ }
}

export function roomAssetScale(config: RoomModelConfig): number {
  return roomAssetScaleXY(config).x
}

export const roomAssetNativeBounds = { widthM: PHOTO_ROOM_ASSET.nativeWidthM, depthM: PHOTO_ROOM_ASSET.nativeDepthM }
