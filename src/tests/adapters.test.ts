import { describe, expect, it } from 'vitest'
import { adaptEvent, adaptMode, adaptNode, adaptPosition, adaptState } from '../domain/adapters'

describe('contract adapters', () => {
  it('normalizes mode vocabulary across branches', () => {
    expect(adaptMode('REAL')).toBe('LIVE'); expect(adaptMode('simulated')).toBe('SIMULATION'); expect(adaptMode('REPLAY')).toBe('REPLAY');
  })
  it('normalizes snake case positions and clamps confidence', () => {
    const result = adaptPosition({ schema_version: '1.0', position_id: 'p1', calculated_at: '2026-01-01T00:00:00Z', window_start: '2026-01-01T00:00:00Z', window_end: '2026-01-01T00:00:00Z', run_id: 'run', deployment_id: 'dep', building_id: 'b', floor_id: 'f', session_id: 's', raw_x_m: 1, raw_y_m: 2, x_m: 1.1, y_m: 1.9, confidence: 1.4, accuracy_radius_m: -2, mode: 'real', anchors_used: ['a1'], observation_count: 4, sequence_number: 2 })
    expect(result.confidence).toBe(1); expect(result.accuracyRadiusM).toBe(0); expect(result.mode).toBe('LIVE');
  })
  it('accepts node statuses and event attributes safely', () => {
    expect(adaptNode({ anchor_id: 'a1', status: 'ONLINE', capture_ok: true }).status).toBe('online')
    expect(adaptNode({ anchor_id: 'a2', status: 'online', capture_ok: false }).status).toBe('degraded')
    expect(adaptEvent({ event_id: 'e1', event_type: 'ZONE_ENTERED', attributes: { to_zone_id: 'office' } }).toZoneId).toBe('office')
  })
  it('unwraps BuildingState data envelopes and derives fallback counts', () => {
    const state = adaptState({ data: { state_revision: 7, mode: 'SIMULATED', positions: [{ session_id: 's', x_m: 1, y_m: 2, confidence: .8, accuracy_radius_m: 1 }], nodes: [{ anchor_id: 'a', status: 'online' }] } })
    expect(state.stateRevision).toBe(7); expect(state.mode).toBe('SIMULATION'); expect(state.counts.activeSessions).toBe(1); expect(state.counts.anchorsOnline).toBe(1)
  })
})
