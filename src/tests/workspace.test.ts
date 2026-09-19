import { describe, expect, it } from 'vitest'
import { MockPositionProvider } from '../domain/mockProvider'
import { defaultRoomConfig } from '../domain/roomModel'
import { buildWorkspace, deviceHealth, eventReviewKey } from '../domain/workspace'
import type { NormalizedState } from '../domain/types'

function snapshot(): NormalizedState {
  let state!: NormalizedState
  const provider = new MockPositionProvider()
  provider.start((payload) => { state = payload.state })
  provider.stop()
  return state
}

describe('shared workspace', () => {
  it('uses the same positions, occupancy, anchor health and hourly count without invented telemetry', () => {
    const state = snapshot()
    const workspace = buildWorkspace(state, defaultRoomConfig)
    expect(workspace.devices).toHaveLength(20)
    expect(workspace.spaces.reduce((sum, room) => sum + room.occupancy, 0)).toBe(20)
    expect(workspace.anchors.every(({ node }) => node?.status === 'online')).toBe(true)
    expect(workspace.eventsLastHour).toBe(state.counts.eventsLastHour)
    expect(workspace.events.length).toBeLessThan(workspace.eventsLastHour)
    expect(workspace.devices.some((device) => 'battery' in device || 'signal' in device)).toBe(false)
    for (const device of workspace.devices) expect(device.position).toBe(state.positions.find((position) => position.sessionId === device.sessionId))
  })
  it('keeps health independent of list order and uses snapshot age', () => {
    const state = snapshot()
    const before = buildWorkspace(state, defaultRoomConfig)
    const after = buildWorkspace({ ...state, positions: [...state.positions].reverse() }, defaultRoomConfig)
    for (const device of before.devices) expect(after.devices.find((item) => item.sessionId === device.sessionId)?.status).toBe(device.status)
    const position = state.positions[0]
    expect(deviceHealth({ ...position, calculatedAt: new Date(Date.parse(state.generatedAt) - 31_000).toISOString() }, state.generatedAt)).toBe('offline')
    expect(deviceHealth({ ...position, confidence: 0.5 }, state.generatedAt)).toBe('degraded')
  })
  it('keeps unknown zones unassigned and event locations tied to the original event', () => {
    const state = snapshot()
    state.positions[0] = { ...state.positions[0], zoneId: 'unknown-zone' }
    const workspace = buildWorkspace(state, defaultRoomConfig)
    expect(workspace.devices[0].spaceId).toBe('unassigned')
    expect(workspace.spaces.reduce((sum, room) => sum + room.occupancy, 0)).toBe(19)
    expect(workspace.events[0].spaceName).toBe('Main circulation')
  })
  it('resolves exactly one scoped event without mutating source data or leaking to a new run', () => {
    const state = snapshot()
    const original = JSON.stringify(state)
    const resolved = new Set([eventReviewKey(state.recentEvents[0])])
    const workspace = buildWorkspace(state, defaultRoomConfig, resolved)
    expect(workspace.events.filter((event) => event.status === 'resolved')).toHaveLength(1)
    expect(JSON.stringify(state)).toBe(original)
    const newRun = { ...state, recentEvents: state.recentEvents.map((event) => ({ ...event, runId: 'another-run' })) }
    expect(buildWorkspace(newRun, defaultRoomConfig, resolved).events.every((event) => event.status === 'active')).toBe(true)
  })
})
