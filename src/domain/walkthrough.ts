import type { MapPoint } from './coordinates'
import { roomDimensions, type RoomModelConfig } from './roomModel'
import { isWalkablePoint } from './simulation'

export function walkthroughStart(config: RoomModelConfig): MapPoint {
  const { widthM, depthM } = roomDimensions(config)
  return { xM: config.originXM + widthM * 0.5, yM: config.originYM + depthM * 0.58 }
}

export function isWalkthroughPoint(point: MapPoint, config: RoomModelConfig): boolean {
  return isWalkablePoint(point.xM, point.yM, config)
}

/** Substep movement through the shared envelope; slide along blocked edges. */
export function moveWithinFloor(from: MapPoint, to: MapPoint, config: RoomModelConfig): MapPoint {
  let safe = isWalkthroughPoint(from, config) ? { ...from } : walkthroughStart(config)
  if (![to.xM, to.yM].every(Number.isFinite)) return safe
  const dx = to.xM - safe.xM
  const dy = to.yM - safe.yM
  // Bound each camera move as well as each collision sample after a slow frame.
  const distance = Math.hypot(dx, dy)
  const fraction = Math.min(1, 0.5 / Math.max(distance, 0.001))
  const steps = Math.max(1, Math.ceil(distance * fraction / 0.05))
  for (let step = 0; step < steps; step += 1) {
    const next = { xM: safe.xM + dx * fraction / steps, yM: safe.yM + dy * fraction / steps }
    if (isWalkthroughPoint(next, config)) safe = next
    else {
      const alongX = { xM: next.xM, yM: safe.yM }
      if (isWalkthroughPoint(alongX, config)) safe = alongX
      const alongY = { xM: safe.xM, yM: next.yM }
      if (isWalkthroughPoint(alongY, config)) safe = alongY
    }
  }
  return safe
}
