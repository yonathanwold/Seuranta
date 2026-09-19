import type { PositionEstimate } from './types'

export type PositionSourceKind = 'phone' | 'development' | 'simulation' | 'other'

/**
 * Classify a position for operator-facing labels without exposing any
 * identity beyond the anonymous session contract.
 */
export function positionSourceKind(position: PositionEstimate): PositionSourceKind {
  if (position.mode === 'SIMULATION') return 'simulation'
  if (position.positionMethod === 'phone-geolocation') return 'phone'
  if (position.positionMethod === 'dev-simulation') return 'development'
  return 'other'
}

export function positionSourceLabel(position: PositionEstimate): string {
  switch (positionSourceKind(position)) {
    case 'phone': return 'Live phone location'
    case 'development': return 'Development injection'
    case 'simulation': return 'Simulation'
    default: return position.mode === 'LIVE' ? 'Live position' : 'Position source unavailable'
  }
}

/** Live and simulated entities share the same high-contrast marker geometry.
 * Selection is communicated by the outline/radius rather than recoloring the
 * sphere, so a live phone remains an opaque black sphere in every state.
 */
export const entityMarkerStyle = {
  color: '#050505',
  selectedOutline: '#b5791d',
  selectedOutlineWidth: 0.08,
} as const
