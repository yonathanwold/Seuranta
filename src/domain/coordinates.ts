import type { PositionEstimate } from './types'

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
