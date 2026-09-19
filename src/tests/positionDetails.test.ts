import { describe, expect, it } from 'vitest'
import { positionDetailFields } from '../domain/positionDetails'
import type { PositionEstimate } from '../domain/types'

const position: PositionEstimate = {
  schemaVersion: '1.0', positionId: 'position-1', calculatedAt: '2026-09-19T12:00:00.000Z',
  windowStart: '2026-09-19T11:59:59.000Z', windowEnd: '2026-09-19T12:00:00.000Z', runId: 'run-1',
  deploymentId: 'deployment-1', buildingId: 'building-1', floorId: 'floor-1', sessionId: 'session-safe',
  rawXM: 12.5, rawYM: 18.5, xM: 12.2, yM: 18.1, zoneId: null, confidence: .84, accuracyRadiusM: 4.2,
  positionMethod: 'phone-geolocation', smoothingMethod: 'ema', anchorsUsed: [], observationCount: 7,
  mode: 'LIVE', sequenceNumber: 7, isOutsideMap: true,
}

describe('safe position detail derivation', () => {
  it('includes every safe normalized telemetry field and is honest about missing values', () => {
    const fields = positionDetailFields(position, '2026-09-19T12:00:05.000Z')
    const values = new Map(fields.map((field) => [field.key, field.value]))
    expect(values.get('sessionId')).toBe('session-safe')
    expect(values.get('floorPosition')).toContain('12.20')
    expect(values.get('rawFloorPosition')).toContain('12.50')
    expect(values.get('source')).toBe('Live phone location')
    expect(values.get('zone')).toBe('Unavailable')
    expect(values.get('anchors')).toBe('Unavailable')
    expect(values.get('age')).toBe('5s old')
    expect(values.get('outsideMap')).toBe('Yes')
  })

  it('does not derive personal, network, geographic, or packet fields', () => {
    const serialized = JSON.stringify(positionDetailFields(position, position.calculatedAt)).toLowerCase()
    for (const forbidden of ['phone number', 'mac address', 'ip address', 'latitude', 'longitude', 'packet payload']) expect(serialized).not.toContain(forbidden)
  })
})
