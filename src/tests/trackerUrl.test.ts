import { describe, expect, it } from 'vitest'
import { resolveTrackerUrl } from '../domain/trackerUrl'

describe('phone tracker URL resolution', () => {
  it('accepts a configured HTTPS public URL and adds the tracker path', () => {
    expect(resolveTrackerUrl('https://demo.example.test', 'http://localhost:4173').url).toBe('https://demo.example.test/tracker/')
    expect(resolveTrackerUrl('https://demo.example.test/tracker/', 'http://localhost:4173').url).toBe('https://demo.example.test/tracker/')
  })

  it('rejects localhost and non-HTTPS fallback URLs for phone QR use', () => {
    expect(resolveTrackerUrl(undefined, 'http://127.0.0.1:8000').url).toBeNull()
    expect(resolveTrackerUrl('http://192.168.1.4:8000', 'http://localhost:4173').reason).toContain('HTTPS')
  })
})
