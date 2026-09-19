import { describe, expect, it, vi } from 'vitest'
import { MockPositionProvider } from '../domain/mockProvider'

describe('mock provider', () => {
  it('emits a complete anonymous demo snapshot and updates revisions', async () => {
    vi.useFakeTimers(); const provider = new MockPositionProvider(); const snapshots: Array<{ stateRevision: number; positions: unknown[] }> = []
    provider.start(({ state }) => snapshots.push({ stateRevision: state.stateRevision, positions: state.positions }))
    expect(snapshots[0].positions).toHaveLength(6); expect(snapshots[0].stateRevision).toBe(0)
    await vi.advanceTimersByTimeAsync(700); expect(snapshots.at(-1)?.stateRevision).toBe(1); expect(snapshots.at(-1)?.positions).toHaveLength(6)
    provider.stop(); vi.useRealTimers()
  })

  it('pauses timestamps and resumes with explicit simulation controls', async () => {
    vi.useFakeTimers(); const provider = new MockPositionProvider(); const snapshots: Array<{ revision: number; calculatedAt: string }> = []
    provider.start(({ state }) => snapshots.push({ revision: state.stateRevision, calculatedAt: state.generatedAt }))
    const beforePause = snapshots.at(-1)!
    provider.setPlaying(false)
    await vi.advanceTimersByTimeAsync(1400)
    expect(snapshots.at(-1)?.calculatedAt).toBe(beforePause.calculatedAt)
    provider.setPlaying(true)
    await vi.advanceTimersByTimeAsync(700)
    expect(snapshots.at(-1)?.revision).toBeGreaterThan(beforePause.revision)
    provider.restart()
    expect(provider.getSimulationControls().playing).toBe(true)
    provider.stop(); vi.useRealTimers()
  })
})
