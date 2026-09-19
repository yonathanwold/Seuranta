import { describe, expect, it } from 'vitest'
import { entityMarkerStyle, positionSourceKind, positionSourceLabel } from '../domain/marker'
import type { PositionEstimate } from '../domain/types'

const base = (mode: PositionEstimate['mode'], positionMethod: string): PositionEstimate => ({
  schemaVersion: '1.0', positionId: 'position-1', calculatedAt: '2026-09-19T12:00:00.000Z',
  windowStart: '2026-09-19T12:00:00.000Z', windowEnd: '2026-09-19T12:00:00.000Z', runId: 'run',
  deploymentId: 'deployment', buildingId: 'building', floorId: 'floor', sessionId: 'session-1', rawXM: 1,
  rawYM: 2, xM: 1, yM: 2, zoneId: null, confidence: .8, accuracyRadiusM: 2, positionMethod,
  smoothingMethod: 'ema', anchorsUsed: [], observationCount: 1, mode, sequenceNumber: 1, isOutsideMap: false,
})

describe('position marker classification and style', () => {
  it('distinguishes phone, development, and simulation sources', () => {
    expect(positionSourceKind(base('LIVE', 'phone-geolocation'))).toBe('phone')
    expect(positionSourceLabel(base('LIVE', 'phone-geolocation'))).toBe('Live phone location')
    expect(positionSourceKind(base('LIVE', 'dev-simulation'))).toBe('development')
    expect(positionSourceKind(base('SIMULATION', 'route'))).toBe('simulation')
  })

  it('keeps the sphere opaque black while reserving outline for selection', () => {
    expect(entityMarkerStyle.color).toBe('#050505')
    expect(entityMarkerStyle.color).not.toBe(entityMarkerStyle.selectedOutline)
    expect(entityMarkerStyle.selectedOutlineWidth).toBeGreaterThan(0)
  })
})
