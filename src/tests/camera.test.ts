import { describe, expect, it } from 'vitest'
import { cameraAfterSelection } from '../domain/camera'

describe('camera selection requests', () => {
  it('retargets Focus once when the selected session identity changes', () => {
    const focused = { preset: 'focus' as const, selectedId: 'session-a', request: 4 }
    expect(cameraAfterSelection(focused, 'session-b')).toEqual({ preset: 'focus', selectedId: 'session-b', request: 5 })
    expect(cameraAfterSelection(focused, 'session-a')).toEqual(focused)
  })

  it('does not request camera motion for ordinary selection or telemetry-like repeats', () => {
    const overview = { preset: 'overview' as const, selectedId: null, request: 2 }
    expect(cameraAfterSelection(overview, 'session-a')).toEqual({ preset: 'overview', selectedId: 'session-a', request: 2 })
    expect(cameraAfterSelection({ ...overview, selectedId: 'session-a' }, 'anchor-a')).toEqual({ preset: 'overview', selectedId: 'anchor-a', request: 2 })
  })
})
