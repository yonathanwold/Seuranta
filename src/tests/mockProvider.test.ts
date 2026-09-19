import { describe, expect, it, vi } from 'vitest'
import { MockPositionProvider } from '../domain/mockProvider'

describe('mock provider', () => {
  it('emits a complete anonymous demo snapshot and updates revisions', async () => {
    vi.useFakeTimers(); const provider = new MockPositionProvider(); const snapshots: Array<{ stateRevision: number; positions: unknown[] }> = []
    provider.start(({ state }) => snapshots.push({ stateRevision: state.stateRevision, positions: state.positions }))
    expect(snapshots[0].positions).toHaveLength(5); expect(snapshots[0].stateRevision).toBe(0)
    await vi.advanceTimersByTimeAsync(700); expect(snapshots.at(-1)?.stateRevision).toBe(1); expect(snapshots.at(-1)?.positions).toHaveLength(5)
    provider.stop(); vi.useRealTimers()
  })
})
