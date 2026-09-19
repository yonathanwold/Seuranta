/* global window, document, crypto, WebSocket, navigator, fetch */
(() => {
  'use strict'

  const apiBase = window.location.origin.replace(/\/$/, '')
  const locationOptions = { enableHighAccuracy: true, maximumAge: 0, timeout: 10000 }
  const storageKey = 'seuranta.tracker.session_id.v1'
  const state = {
    apiBase,
    config: null,
    sessionId: getSessionId(),
    watchId: null,
    socket: null,
    reconnectTimer: null,
    reconnectMs: 1000,
    active: false,
    devTimer: null,
    devStep: 0,
    latestPosition: null,
    updates: 0,
  }

  const $ = (id) => document.getElementById(id)
  const enableButton = $('enable-button')
  const sessionCard = $('session-card')
  const statusPill = $('status-pill')
  const permissionNote = $('permission-note')
  const trackerMessage = $('tracker-message')
  const calibrateButton = $('calibrate-button')
  const stopButton = $('stop-button')
  const devCard = $('dev-card')
  const devButton = $('dev-button')

  function getSessionId() {
    const existing = window.localStorage.getItem(storageKey)
    if (existing && /^session-[a-z0-9-]{4,64}$/.test(existing)) return existing
    const generated = `session-${crypto.randomUUID()}`.toLowerCase()
    window.localStorage.setItem(storageKey, generated)
    return generated
  }

  function shortSessionId() {
    return state.sessionId.replace(/^session-/, '').replace(/-/g, '').slice(0, 4).toUpperCase()
  }

  function scopeFields() {
    const config = state.config || {}
    return {
      run_id: config.run_id || 'vt-acb-floor1',
      deployment_id: config.deployment_id || 'vt-acb-pilot',
      building_id: config.building_id || 'vt-academic-classroom-building',
      floor_id: config.floor_id || 'floor-1',
    }
  }

  function setStatus(value, message) {
    const label = value === 'location-unavailable' ? 'Location unavailable' : value[0].toUpperCase() + value.slice(1)
    statusPill.className = `status-pill status-pill-${value}`
    statusPill.querySelector('b').textContent = label
    if (message) trackerMessage.textContent = message
  }

  function setMessage(message) {
    trackerMessage.textContent = message
  }

  function wsUrl() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}/api/v1/tracker`
  }

  function sendSocket(payload) {
    if (state.socket && state.socket.readyState === WebSocket.OPEN) {
      state.socket.send(JSON.stringify(payload))
      return true
    }
    return false
  }

  async function sendRest(path, payload) {
    const response = await fetch(`${state.apiBase}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const body = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(body?.error?.message || `Request returned ${response.status}`)
    return body.data || body
  }

  function connectSocket() {
    if (!state.active || state.socket) return
    setStatus('connecting', 'Connecting to the Seuranta live telemetry channel…')
    const socket = new WebSocket(wsUrl())
    state.socket = socket
    socket.onopen = () => {
      if (state.socket !== socket) return
      state.reconnectMs = 1000
      socket.send(JSON.stringify({ type: 'hello', session_id: state.sessionId, ...scopeFields() }))
      setStatus('connected', 'Connected. Waiting for the first browser location update…')
    }
    socket.onmessage = (event) => {
      let message
      try { message = JSON.parse(event.data) } catch { return }
      if (message.type === 'ack') {
        if (message.status === 'calibration_required') setMessage('Stand at the configured known point, then press Calibrate Position.')
        else if (message.status === 'live') setStatus('live', 'Live position is being shared with Seuranta.')
      } else if (message.type === 'calibrated') {
        setStatus(message.position ? 'live' : 'connected', message.position ? 'Calibration saved. Live position is being shared with Seuranta.' : 'Calibration saved. The next location update will appear on the map.')
        calibrateButton.disabled = !state.latestPosition
      } else if (message.type === 'error') {
        setMessage(message.message || 'The telemetry channel rejected that packet.')
      }
    }
    socket.onerror = () => socket.close()
    socket.onclose = () => {
      if (state.socket !== socket) return
      state.socket = null
      if (!state.active) return
      setStatus('reconnecting', 'Connection interrupted. Retrying; browser location remains local until delivery resumes…')
      const wait = state.reconnectMs
      state.reconnectMs = Math.min(15000, state.reconnectMs * 2)
      window.clearTimeout(state.reconnectTimer)
      state.reconnectTimer = window.setTimeout(connectSocket, wait)
    }
  }

  function positionPayload(position) {
    const coords = position.coords
    return {
      type: 'location',
      session_id: state.sessionId,
      captured_at: new Date(position.timestamp || Date.now()).toISOString(),
      latitude: coords.latitude,
      longitude: coords.longitude,
      altitude: Number.isFinite(coords.altitude) ? coords.altitude : null,
      accuracy_m: coords.accuracy,
      altitude_accuracy_m: Number.isFinite(coords.altitudeAccuracy) ? coords.altitudeAccuracy : null,
      heading_deg: Number.isFinite(coords.heading) ? coords.heading : null,
      speed_mps: Number.isFinite(coords.speed) && coords.speed >= 0 ? coords.speed : null,
      ...scopeFields(),
    }
  }

  async function deliverLocation(payload) {
    if (sendSocket(payload)) return
    try {
      const result = await sendRest('/api/v1/telemetry/location', payload)
      if (result.status === 'live') setStatus('live', 'Live position is being shared with Seuranta.')
      else if (result.status === 'calibration_required') setMessage('Location received. Calibrate at the known point to place this device on the floor map.')
    } catch (error) {
      setStatus('reconnecting', error.message || 'Backend unavailable. Retrying…')
    }
  }

  function onPosition(position) {
    if (!state.active) return
    state.latestPosition = position
    state.updates += 1
    const coords = position.coords
    $('accuracy-value').textContent = Number.isFinite(coords.accuracy) ? `${coords.accuracy.toFixed(1)} m` : '—'
    $('position-value').textContent = `${coords.latitude.toFixed(6)}, ${coords.longitude.toFixed(6)}`
    $('updates-value').textContent = String(state.updates)
    $('last-update-value').textContent = new Date(position.timestamp || Date.now()).toLocaleTimeString()
    calibrateButton.disabled = false
    void deliverLocation(positionPayload(position))
  }

  function onLocationError(error) {
    if (error.code === 1) {
      stopSharing(false)
      setStatus('permission-denied', 'Location permission was denied. Enable precise location in browser settings, then try again.')
    } else if (error.code === 2) {
      setStatus('location-unavailable', 'The browser could not determine a position. Keep the page open and try again outside.')
    } else if (error.code === 3) {
      setStatus('reconnecting', 'The location request timed out. The browser will continue watching for another fix.')
    } else {
      setMessage('The browser reported an unknown location error.')
    }
  }

  function startSharing() {
    if (!('geolocation' in navigator)) {
      setStatus('location-unavailable', 'This browser does not support geolocation.')
      return
    }
    state.active = true
    sessionCard.hidden = false
    enableButton.disabled = true
    stopButton.disabled = false
    $('session-short').textContent = shortSessionId()
    permissionNote.textContent = 'The browser location permission request was started by your button press.'
    setStatus('connecting', 'Connecting and requesting browser location permission…')
    connectSocket()
    state.watchId = navigator.geolocation.watchPosition(onPosition, onLocationError, locationOptions)
  }

  function stopSharing(showMessage = true) {
    state.active = false
    if (state.watchId !== null) navigator.geolocation.clearWatch(state.watchId)
    state.watchId = null
    window.clearTimeout(state.reconnectTimer)
    state.reconnectTimer = null
    if (state.socket) {
      const socket = state.socket
      state.socket = null
      socket.close()
    }
    if (state.devTimer) {
      window.clearInterval(state.devTimer)
      state.devTimer = null
      devButton.textContent = 'Start DEV SIMULATION'
    }
    enableButton.disabled = false
    stopButton.disabled = true
    calibrateButton.disabled = true
    setStatus('stopped', showMessage ? 'Sharing stopped. No more browser locations will be sent.' : 'Location permission is required before sharing can start.')
  }

  async function calibrate() {
    if (!state.latestPosition) return
    const coords = state.latestPosition.coords
    const payload = {
      type: 'calibrate',
      session_id: state.sessionId,
      calibration_id: state.config?.calibration?.calibration_id || 'demo-origin',
      latitude: coords.latitude,
      longitude: coords.longitude,
      ...scopeFields(),
    }
    setMessage('Saving this geographic point as the configured floor reference…')
    if (sendSocket(payload)) return
    try {
      await sendRest('/api/v1/tracker/calibrate', payload)
      setMessage('Calibration saved. Keep sharing and the next update will be placed on the floor map.')
    } catch (error) {
      setMessage(error.message || 'Calibration could not be saved.')
    }
  }

  function toggleDevSimulation() {
    if (state.devTimer) {
      window.clearInterval(state.devTimer)
      state.devTimer = null
      devButton.textContent = 'Start DEV SIMULATION'
      setMessage('Development simulation stopped.')
      return
    }
    sessionCard.hidden = false
    $('session-short').textContent = shortSessionId()
    devButton.textContent = 'Stop DEV SIMULATION'
    setStatus('live', 'DEV SIMULATION — these floor positions are not browser GPS.')
    state.devStep = 0
    const sendDev = async () => {
      const floor = state.config?.floor || { width_m: 76.9, depth_m: 44.6 }
      const x = 12 + (Math.sin(state.devStep / 8) + 1) * 0.25 * Math.max(20, floor.width_m - 24)
      const y = 14 + (Math.cos(state.devStep / 10) + 1) * 0.25 * Math.max(12, floor.depth_m - 24)
      state.devStep += 1
      try {
        const result = await sendRest('/api/v1/dev/position', { session_id: state.sessionId, x_m: x, y_m: y, accuracy_radius_m: 2, ...scopeFields() })
        state.updates += 1
        $('updates-value').textContent = String(state.updates)
        $('accuracy-value').textContent = '2.0 m'
        $('position-value').textContent = `${x.toFixed(2)} m, ${y.toFixed(2)} m`
        $('last-update-value').textContent = new Date().toLocaleTimeString()
        if (result?.position) setMessage('DEV SIMULATION — backend floor position received.')
      } catch (error) {
        setStatus('reconnecting', error.message || 'Development endpoint unavailable.')
      }
    }
    void sendDev()
    state.devTimer = window.setInterval(sendDev, 1200)
  }

  async function loadConfig() {
    try {
      const response = await fetch(`${state.apiBase}/api/v1/tracker/config`)
      if (!response.ok) return
      const body = await response.json()
      state.config = body.data || body
      $('deployment-label').textContent = `${state.config.deployment_id || 'Seuranta'} · ${state.config.floor_id || 'floor-1'}`
      if (state.config.dev_mode) devCard.hidden = false
    } catch {
      $('deployment-label').textContent = 'Backend configuration unavailable'
    }
  }

  enableButton.addEventListener('click', startSharing)
  stopButton.addEventListener('click', () => stopSharing(true))
  calibrateButton.addEventListener('click', () => { void calibrate() })
  devButton.addEventListener('click', toggleDevSimulation)
  $('session-short').textContent = shortSessionId()
  void loadConfig()
})()
