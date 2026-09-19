import { afterEach, describe, expect, it, vi } from 'vitest'

const trackerMarkup = `
  <button id="enable-button"></button>
  <section id="session-card" hidden></section>
  <div id="status-pill"><span></span><b></b></div>
  <p id="permission-note"></p><p id="tracker-message"></p>
  <button id="calibrate-button"></button><button id="stop-button"></button>
  <button id="new-session-button" hidden></button>
  <section id="dev-card" hidden></section><button id="dev-button"></button>
  <strong id="session-short"></strong><span id="accuracy-value"></span>
  <span id="position-value"></span><span id="updates-value"></span>
  <span id="last-update-value"></span><span id="deployment-label"></span>
`

const waitFor = async (predicate: () => boolean) => {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (predicate()) return
    await new Promise((resolve) => setTimeout(resolve, 10))
  }
  throw new Error('Timed out waiting for tracker state')
}

describe('static tracker session recovery', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.resetModules()
    document.body.innerHTML = ''
  })

  it('rotates a persisted ended session and permits an explicit replacement session', async () => {
    document.body.innerHTML = trackerMarkup
    window.isSecureContext = true
    const oldSession = 'session-ended-test'
    window.localStorage.setItem('seuranta.tracker.session_id.v1', oldSession)
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: { watchPosition: vi.fn(() => 1), clearWatch: vi.fn() },
    })

    class MockSocket {
      static OPEN = 1
      readyState = 0
      onopen: (() => void) | undefined
      onmessage: ((event: { data: string }) => void) | undefined
      onclose: (() => void) | undefined
      constructor() {
        setTimeout(() => this.open(), 0)
      }
      open() {
        this.readyState = MockSocket.OPEN
        this.onopen?.()
      }
      send(value: string) {
        const message = JSON.parse(value) as { type?: string; session_id?: string }
        if (message.type !== 'hello') return
        setTimeout(() => this.onmessage?.({
          data: JSON.stringify(message.session_id === oldSession
            ? { type: 'error', code: 'tracker_session_ended', message: 'session has ended; start a new anonymous session' }
            : { type: 'connected', status: 'connected', session_id: message.session_id }),
        }), 0)
      }
      close() {
        this.readyState = 3
        this.onclose?.()
      }
    }
    vi.stubGlobal('WebSocket', MockSocket)
    Object.defineProperty(window, 'WebSocket', { configurable: true, value: MockSocket })
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/tracker/config')) return new Response(JSON.stringify({ data: { dev_mode: false } }), { status: 200 })
      if (url.includes('/api/v1/sessions/') && init?.method === 'POST') return new Response(JSON.stringify({ data: {} }), { status: 200 })
      return new Response(JSON.stringify({ data: {} }), { status: 200 })
    }))

    // @ts-expect-error the browser tracker is a static script, not a module
    await import('../../tracker/tracker.js?session-recovery-test')
    document.getElementById('enable-button')?.click()
    await new Promise((resolve) => setTimeout(resolve, 100))
    await waitFor(() => document.getElementById('status-pill')?.textContent === 'Connected')

    const replacementSession = window.localStorage.getItem('seuranta.tracker.session_id.v1')
    expect(replacementSession).toMatch(/^session-/)
    expect(replacementSession).not.toBe(oldSession)
    expect(document.getElementById('tracker-message')?.textContent).not.toContain('session has ended')

    document.getElementById('stop-button')?.click()
    await waitFor(() => document.getElementById('new-session-button')?.hidden === false)
    expect(document.getElementById('enable-button')).toHaveProperty('disabled', true)

    document.getElementById('new-session-button')?.click()
    const explicitSession = window.localStorage.getItem('seuranta.tracker.session_id.v1')
    expect(explicitSession).toMatch(/^session-/)
    expect(explicitSession).not.toBe(replacementSession)
    expect(document.getElementById('enable-button')).toHaveProperty('disabled', false)
    document.getElementById('enable-button')?.click()
    await waitFor(() => document.getElementById('status-pill')?.textContent === 'Connected')
  })
})
