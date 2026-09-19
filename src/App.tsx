import { useEffect, useMemo, useState } from 'react'
import { Building2, Check, ChevronRight, CircleHelp, Crosshair, Gauge, Layers3, Pause, Play, RefreshCw, RotateCcw, Search, Settings, Target, Wifi, X, ZoomIn } from 'lucide-react'
import { MapCanvas } from './components/MapCanvas'
import { cameraAfterSelection } from './domain/camera'
import { LivePositionProvider, type LiveScope } from './domain/liveProvider'
import { MockPositionProvider, type SimulationControls } from './domain/mockProvider'
import { demoFloor } from './domain/floorDefinition'
import { useAtlasStore } from './domain/store'
import { loadRoomConfig, roomDimensions, saveRoomConfig, validateRoomConfig, type RoomModelConfig } from './domain/roomModel'
import type { NormalizedMode, PositionEstimate, ProviderStatus } from './domain/types'
import type { SimulationScenario } from './domain/simulation'

const iconSize = 16
type LayerKey = 'entities' | 'anchors' | 'labels' | 'confidence' | 'zones'
const modeCopy: Record<NormalizedMode, string> = { SIMULATION: 'Simulation', LIVE: 'Live', REPLAY: 'Replay' }
const formatTime = (timestamp?: string) => timestamp ? new Intl.DateTimeFormat('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(timestamp)) : '—'
const formatAge = (timestamp?: string) => { if (!timestamp) return '—'; const seconds = Math.max(0, Math.round((Date.now() - new Date(timestamp).getTime()) / 1000)); return seconds < 2 ? 'just now' : `${seconds}s ago` }
const titleForSession = (sessionId: string) => `Device ${sessionId.replace(/^session-/, '').slice(0, 4).toUpperCase()}`
const zoneLabel = (zoneId?: string | null) => ({
  'main-circulation': 'Main circulation',
  'classroom-west': 'West active-learning classroom',
  'classroom-center': 'Central instructional classroom',
  'lecture-hall': 'Lecture / auditorium',
  'collaborative-classroom': 'Curved collaborative classroom',
  'south-social': 'Open collaboration area',
}[zoneId ?? ''] ?? 'Unassigned')

interface LiveSettings {
  apiUrl: string
  runId: string
  deploymentId: string
  buildingId: string
  floorId: string
}

const defaultLiveSettings: LiveSettings = { apiUrl: '', runId: 'vt-acb-floor1', deploymentId: 'vt-acb-pilot', buildingId: demoFloor.buildingId, floorId: demoFloor.floorId }
const liveSettingsKey = 'seuranta.vt-acb.live-settings.v1'
function loadLiveSettings(): LiveSettings {
  if (typeof localStorage === 'undefined') return defaultLiveSettings
  try {
    const value = JSON.parse(localStorage.getItem(liveSettingsKey) ?? '') as Partial<LiveSettings>
    return { ...defaultLiveSettings, ...Object.fromEntries(Object.keys(defaultLiveSettings).map((key) => [key, typeof value[key as keyof LiveSettings] === 'string' ? value[key as keyof LiveSettings] : defaultLiveSettings[key as keyof LiveSettings]])) } as LiveSettings
  } catch { return defaultLiveSettings }
}

function StatusDot({ status }: { status: ProviderStatus | 'online' | 'degraded' | 'offline' }) { return <span className={`status-dot status-${status}`} aria-hidden="true" /> }

function Navigation({ mode, status, onMode, onOpenSetup }: { mode: NormalizedMode; status: ProviderStatus; onMode: (mode: NormalizedMode) => void; onOpenSetup: () => void }) {
  return <aside className="navigation">
    <div className="brand" aria-label="Seuranta Spatial Operations"><img className="brand-logo" src="/brand/seuranta-logo.png" alt="Seuranta Spatial Operations" /><img className="brand-logo-mark" src="/brand/seuranta-mark.png" alt="" aria-hidden="true" /></div>
    <p className="nav-caption">TRACKING</p>
    <nav aria-label="Primary navigation"><div className="nav-item is-active" aria-current="page"><Target size={iconSize} /> <span>Live map</span></div></nav>
    <div className="nav-divider" />
    <div className="nav-mode"><div className="nav-mode-heading"><StatusDot status={mode === 'SIMULATION' ? 'online' : status === 'live' ? 'online' : status === 'reconnecting' ? 'degraded' : 'offline'} /><span>{modeCopy[mode]}</span><ChevronRight size={15} /></div><span>{mode === 'SIMULATION' ? 'VT first-floor walkthrough' : status === 'error' ? 'Source unavailable' : 'Scoped API source'}</span><div className="mode-options" role="group" aria-label="Data mode"><button className={mode === 'SIMULATION' ? 'is-selected' : ''} onClick={() => onMode('SIMULATION')}>Demo</button><button className={mode === 'LIVE' ? 'is-selected' : ''} onClick={() => onMode('LIVE')}>Live</button></div></div>
    <button className="setup-link" onClick={onOpenSetup}><Settings size={15} /><span>Floor setup</span><ChevronRight size={14} /></button>
    <div className="nav-footer"><div className="privacy-note"><CircleHelp size={14} /><span>Anonymous IDs only</span></div><div className="profile"><div className="avatar">VT</div><div><strong>VT ACB · Floor 1</strong><span>Local workspace</span></div></div></div>
  </aside>
}

function Explorer({ state, roomConfig, search, onSearch, selectedId, onSelect, showLayers, onToggle }: { state: ReturnType<typeof useAtlasStore.getState>['snapshot']; roomConfig: RoomModelConfig; search: string; onSearch: (value: string) => void; selectedId: string | null; onSelect: (id: string) => void; showLayers: Record<LayerKey, boolean>; onToggle: (key: LayerKey) => void }) {
  const term = search.trim().toLowerCase()
  const positions = state.positions.filter((position) => `${position.sessionId} ${zoneLabel(position.zoneId)}`.toLowerCase().includes(term))
  const nodeMap = new Map(state.nodes.map((node) => [node.anchorId, node]))
  return <aside className="explorer">
    <div className="explorer-tabs"><span className="is-active">Entities</span><button onClick={() => document.getElementById('map-layers')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })}>Map layers</button></div>
    <label className="search-box"><Search size={16} /><input value={search} onChange={(event) => onSearch(event.target.value)} placeholder="Search devices..." aria-label="Search devices" />{search && <button onClick={() => onSearch('')} aria-label="Clear search"><X size={14} /></button>}</label>
    <section className="explorer-section"><div className="section-heading"><span>Devices <strong>{positions.length}</strong></span></div><div className="entity-list">{positions.map((position) => <button key={position.sessionId} className={`entity-row ${selectedId === position.sessionId ? 'is-selected' : ''}`} onClick={() => onSelect(position.sessionId)}><span className="entity-dot" /><span><strong>{titleForSession(position.sessionId)}</strong><small>Last seen {formatAge(position.calculatedAt)}</small></span><em>{Math.round(position.confidence * 100)}%</em><ChevronRight size={14} /></button>)}</div>{!positions.length && <p className="empty-note">No anonymous sessions match this search.</p>}</section>
    <section className="explorer-section anchors-section"><div className="section-heading"><span><Wifi size={15} /> Anchors <strong>{roomConfig.anchors.length}</strong></span></div>{roomConfig.anchors.map((anchor) => { const node = nodeMap.get(anchor.anchorId); return <button key={anchor.anchorId} className={`anchor-row ${selectedId === anchor.anchorId ? 'is-selected' : ''}`} onClick={() => onSelect(anchor.anchorId)}><span className="anchor-glyph" /><span><strong>{anchor.label}</strong><small>{node?.status ?? (modeCopy[state.mode] === 'Live' ? 'offline' : 'planned')}</small></span><StatusDot status={node?.status ?? 'offline'} /><ChevronRight size={14} /></button> })}</section>
    <section className="layer-section" id="map-layers"><div className="section-heading"><span><Layers3 size={15} /> Map layers</span></div>{([['entities', 'Devices'], ['anchors', 'Anchors'], ['labels', 'Labels'], ['confidence', 'Uncertainty'], ['zones', 'Floor overlay']] as Array<[LayerKey, string]>).map(([key, label]) => <label className="toggle-row" key={key}><span>{label}</span><input type="checkbox" checked={showLayers[key]} onChange={() => onToggle(key)} /><i /></label>)}</section>
  </aside>
}

function TopBar({ mode, status, snapshot, onMode, onRefresh, onOpenSetup }: { mode: NormalizedMode; status: ProviderStatus; snapshot: ReturnType<typeof useAtlasStore.getState>['snapshot']; onMode: (mode: NormalizedMode) => void; onRefresh: () => void; onOpenSetup: () => void }) {
  const freshness = mode === 'SIMULATION' ? `Updated ${formatAge(snapshot.generatedAt)}` : status === 'live' ? `Updated ${formatAge(snapshot.generatedAt)}` : status === 'reconnecting' ? 'Reconnecting…' : status === 'error' ? 'Live source unavailable' : 'Waiting for data'
  const confidence = snapshot.positions.length ? Math.round(snapshot.positions.reduce((sum, position) => sum + position.confidence, 0) / snapshot.positions.length * 100) : 0
  return <header className="topbar"><div className="top-context"><div className="context-name"><Building2 size={17} /><strong>VT Academic Classroom Building</strong><span>/</span><span>Floor 1</span></div><div className={`context-status ${mode === 'SIMULATION' ? 'is-simulation' : ''}`}><StatusDot status={mode === 'SIMULATION' ? 'online' : status === 'live' ? 'online' : status === 'reconnecting' ? 'degraded' : 'offline'} /><strong>{modeCopy[mode]}</strong><span>· {freshness}</span></div></div><div className="top-metrics"><div><span>Tracked devices</span><strong>{snapshot.counts.activeSessions}</strong></div><div><span>Anchors online</span><strong>{snapshot.counts.anchorsOnline} / {snapshot.nodes.length || 4}</strong></div><div><span>Average confidence</span><strong>{confidence}%</strong></div><button className={`mode-switch ${mode === 'SIMULATION' ? 'is-sim' : ''}`} onClick={() => onMode(mode === 'SIMULATION' ? 'LIVE' : 'SIMULATION')} aria-label="Switch data mode"><span>Simulation</span><span>Live</span></button></div><div className="top-actions"><button className="button-quiet outline" onClick={onOpenSetup}><Settings size={15} /> Setup</button><button className="button-quiet" onClick={onRefresh}><RefreshCw size={15} /> Refresh</button></div></header>
}

function CameraToolbar({ preset, onPreset }: { preset: 'overview' | 'top' | 'focus'; onPreset: (preset: 'overview' | 'top' | 'focus') => void }) {
  return <div className="camera-toolbar" role="group" aria-label="Camera controls"><button className={preset === 'overview' ? 'is-active' : ''} onClick={() => onPreset('overview')}><Crosshair size={15} /> Overview</button><button className={preset === 'top' ? 'is-active' : ''} onClick={() => onPreset('top')}><Layers3 size={15} /> Top</button><button className={preset === 'focus' ? 'is-active' : ''} onClick={() => onPreset('focus')}><ZoomIn size={15} /> Focus</button><button onClick={() => onPreset('overview')}><RotateCcw size={15} /> Reset</button></div>
}

function ActivityFeed({ state, selected }: { state: ReturnType<typeof useAtlasStore.getState>['snapshot']; selected?: PositionEstimate }) {
  const events = state.recentEvents.filter((event) => !selected || !event.sessionId || event.sessionId === selected.sessionId).slice(0, 8)
  return <div className="activity-feed">{events.length ? events.map((event) => <div className="activity-row" key={event.eventId}><span className="activity-line" /><span className="activity-time">{formatTime(event.occurredAt)}</span><span>{event.eventType.replaceAll('_', ' ').toLowerCase().replace(/^./, (letter) => letter.toUpperCase())}{event.toZoneId ? ` · ${zoneLabel(event.toZoneId)}` : ''}</span></div>) : <p className="muted-copy">{selected ? 'No recent transitions for this device.' : 'Events will appear here when the source reports them.'}</p>}</div>
}

function SimulationControlsPanel({ controls, onPlaying, onRestart, onSpeed, onScenario }: { controls: SimulationControls; onPlaying: (playing: boolean) => void; onRestart: () => void; onSpeed: (speed: number) => void; onScenario: (scenario: SimulationScenario) => void }) {
  return <section className="simulation-controls"><div className="panel-heading"><span><Gauge size={15} /> Simulation controls</span><span className="sim-badge">SIMULATION</span></div><div className="sim-actions"><button className="sim-primary" onClick={() => onPlaying(!controls.playing)}>{controls.playing ? <Pause size={15} /> : <Play size={15} />}{controls.playing ? 'Pause' : 'Play'}</button><button className="sim-secondary" onClick={onRestart}><RotateCcw size={15} /> Restart</button></div><label className="field-label">Scenario<select value={controls.scenario} onChange={(event) => onScenario(event.target.value as SimulationScenario)}><option value="walkthrough">Walkthrough (normal)</option><option value="weak-signal">Weak signal</option></select></label><label className="field-label speed-label"><span>Simulation speed <strong>{controls.speed}×</strong></span><input type="range" min="0.25" max="2" step="0.25" value={controls.speed} onChange={(event) => onSpeed(Number(event.target.value))} /></label></section>
}

function DetailPanel({ state, roomConfig, selectedId, mode, providerStatus, simulation, onClose, onSelect, onSimulation, onOpenSetup }: { state: ReturnType<typeof useAtlasStore.getState>['snapshot']; roomConfig: RoomModelConfig; selectedId: string | null; mode: NormalizedMode; providerStatus: ProviderStatus; simulation: SimulationControls; onClose: () => void; onSelect: (id: string) => void; onSimulation: { onPlaying: (playing: boolean) => void; onRestart: () => void; onSpeed: (speed: number) => void; onScenario: (scenario: SimulationScenario) => void }; onOpenSetup: () => void }) {
  const selected = state.positions.find((position) => position.sessionId === selectedId)
  const selectedNode = state.nodes.find((node) => node.anchorId === selectedId)
  const dimensions = roomDimensions(roomConfig)
  return <aside className="detail-panel"><div className="detail-heading"><div><h2>{selectedNode ? selectedNode.anchorId : selected ? titleForSession(selected.sessionId) : 'Floor status'}</h2><p>{selectedNode ? 'Planned infrastructure node' : selected ? 'Anonymous device' : 'Reference-derived first-floor model'}</p></div>{(selected || selectedNode) && <button className="icon-button" onClick={onClose} aria-label="Close details"><X size={18} /></button>}</div>{selectedNode ? <div className="detail-body"><div className="status-callout"><StatusDot status={selectedNode.status} /><span>{selectedNode.status === 'online' ? 'Online' : selectedNode.status === 'degraded' ? 'Degraded signal' : 'Offline'}</span></div><dl className="detail-list"><div><dt>Status</dt><dd className={`text-${selectedNode.status}`}>{selectedNode.status}</dd></div><div><dt>Buffer depth</dt><dd>{selectedNode.bufferDepth} batches</dd></div><div><dt>Observations sent</dt><dd>{selectedNode.observationsSentTotal.toLocaleString()}</dd></div><div><dt>Last heartbeat</dt><dd>{formatAge(selectedNode.emittedAt)}</dd></div></dl><h3>Anchor diagnostics</h3>{selectedNode.errorCodes.length ? <ul className="diagnostic-list">{selectedNode.errorCodes.map((code) => <li key={code}>{code.replaceAll('_', ' ')}</li>)}</ul> : <p className="muted-copy">No diagnostic codes reported.</p>}<h3>Other anchors</h3><div className="anchor-coverage">{roomConfig.anchors.map((anchor) => <button key={anchor.anchorId} className={anchor.anchorId === selectedId ? 'is-current' : ''} onClick={() => onSelect(anchor.anchorId)}><span className="anchor-glyph" /><span>{anchor.label}</span><StatusDot status={state.nodes.find((node) => node.anchorId === anchor.anchorId)?.status ?? 'offline'} /></button>)}</div></div> : <div className="detail-body">{selected ? <><div className="status-callout"><StatusDot status="online" /><span>Active · {modeCopy[selected.mode]}</span></div><dl className="detail-list"><div><dt>Position (X, Y)</dt><dd>{selected.xM.toFixed(2)}, {selected.yM.toFixed(2)} m</dd></div><div><dt>Confidence</dt><dd>{Math.round(selected.confidence * 100)}%</dd></div><div><dt>Uncertainty radius</dt><dd>{selected.accuracyRadiusM.toFixed(2)} m</dd></div><div><dt>Floor zone</dt><dd>{zoneLabel(selected.zoneId)}</dd></div><div><dt>Last update</dt><dd>{formatAge(selected.calculatedAt)}</dd></div></dl><h3>Recent events</h3><ActivityFeed state={state} selected={selected} /></> : <><div className="room-summary"><span className="room-summary-icon"><Building2 size={20} /></span><div><strong>Academic Classroom Building · Floor 1</strong><span>{dimensions.widthM.toFixed(1)} m × {dimensions.depthM.toFixed(1)} m estimated footprint</span></div></div><div className="status-callout"><StatusDot status={mode === 'SIMULATION' ? 'online' : providerStatus === 'live' ? 'online' : providerStatus === 'reconnecting' ? 'degraded' : 'offline'} /><span>{mode === 'SIMULATION' ? 'Simulation ready' : providerStatus === 'live' ? 'Live source connected' : providerStatus === 'error' ? 'Live source unavailable' : 'Waiting for live source'}</span></div><p className="muted-copy">Select a device or anchor to inspect its telemetry. The supplied model is an estimated reference reconstruction; surveyed dimensions and installed anchor coordinates can be entered in Floor setup.</p><button className="setup-cta" onClick={onOpenSetup}><Settings size={15} /> Open Floor setup</button><h3>Recent events</h3><ActivityFeed state={state} /></>}</div>}{mode === 'SIMULATION' && <SimulationControlsPanel controls={simulation} onPlaying={onSimulation.onPlaying} onRestart={onSimulation.onRestart} onSpeed={onSimulation.onSpeed} onScenario={onSimulation.onScenario} />}</aside>
}

function SetupModal({ roomConfig, liveSettings, onClose, onSave }: { roomConfig: RoomModelConfig; liveSettings: LiveSettings; onClose: () => void; onSave: (room: RoomModelConfig, live: LiveSettings) => void }) {
  const [room, setRoom] = useState<RoomModelConfig>(() => ({ ...roomConfig, anchors: roomConfig.anchors.map((anchor) => ({ ...anchor })) }))
  const [live, setLive] = useState<LiveSettings>(liveSettings)
  const [errors, setErrors] = useState<string[]>([])
  useEffect(() => { const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }; window.addEventListener('keydown', onKey); return () => window.removeEventListener('keydown', onKey) }, [onClose])
  const updateAnchor = (index: number, field: 'anchorId' | 'xM' | 'yM', value: string) => setRoom((current) => ({ ...current, anchors: current.anchors.map((anchor, anchorIndex) => anchorIndex === index ? { ...anchor, [field]: field === 'anchorId' ? value : Number(value) } : anchor) }))
  const submit = () => { const nextErrors = validateRoomConfig(room).concat(Object.entries(live).filter(([key, value]) => key !== 'apiUrl' && !value.trim()).map(([key]) => `${key} is required for Live mode.`)); if (nextErrors.length) { setErrors(nextErrors); return } ; saveRoomConfig(room); localStorage.setItem(liveSettingsKey, JSON.stringify(live)); onSave(room, live) }
  return <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}><section className="setup-modal" role="dialog" aria-modal="true" aria-labelledby="setup-title"><div className="modal-heading"><div><h2 id="setup-title">Floor setup</h2><p>Calibrate the Virginia Tech model and configure the future live source.</p></div><button className="icon-button" onClick={onClose} aria-label="Close Floor setup"><X size={19} /></button></div><div className="setup-body"><div className="setup-column"><h3>Floor calibration</h3><p className="setup-note">The supplied model is reference-derived, not a measured survey. Its current 76.9 × 44.6 m footprint has about ±15% scale uncertainty; replace these values after a site measurement.</p><div className="field-grid"><label className="field-label">Floor width (m)<input type="number" min="10" max="300" step="0.001" value={room.measuredWidthM} onChange={(event) => setRoom({ ...room, measuredWidthM: Number(event.target.value) })} /></label><label className="field-label">Floor depth (m)<input type="number" min="10" max="300" step="0.001" value={room.measuredDepthM} onChange={(event) => setRoom({ ...room, measuredDepthM: Number(event.target.value) })} /></label><label className="field-label">Model yaw (°)<input type="number" min="-180" max="180" step="1" value={room.yawDeg} onChange={(event) => setRoom({ ...room, yawDeg: Number(event.target.value) })} /></label><label className="field-label">Origin X (m)<input type="number" step="0.01" value={room.originXM} onChange={(event) => setRoom({ ...room, originXM: Number(event.target.value) })} /></label><label className="field-label">Origin Y (m)<input type="number" step="0.01" value={room.originYM} onChange={(event) => setRoom({ ...room, originYM: Number(event.target.value) })} /></label></div><h3>Planned anchors</h3><div className="anchor-inputs">{room.anchors.map((anchor, index) => <div className="anchor-input-row" key={`${index}-${anchor.anchorId}`}><strong>{index + 1}</strong><input aria-label={`Anchor ${index + 1} ID`} value={anchor.anchorId} onChange={(event) => updateAnchor(index, 'anchorId', event.target.value)} /><input aria-label={`Anchor ${index + 1} X`} type="number" step="0.01" value={anchor.xM} onChange={(event) => updateAnchor(index, 'xM', event.target.value)} /><input aria-label={`Anchor ${index + 1} Y`} type="number" step="0.01" value={anchor.yM} onChange={(event) => updateAnchor(index, 'yM', event.target.value)} /></div>)}</div></div><div className="setup-column"><h3>Live API connection</h3><p className="setup-note">Saved locally in this browser. No secrets are stored here. Live mode does not fall back to Simulation when the source fails.</p><label className="field-label">API base URL (optional)<input placeholder="http://localhost:8000" value={live.apiUrl} onChange={(event) => setLive({ ...live, apiUrl: event.target.value })} /></label>{(['runId', 'deploymentId', 'buildingId', 'floorId'] as Array<keyof Omit<LiveSettings, 'apiUrl'>>).map((key) => <label className="field-label" key={key}>{key.replace(/Id$/, ' ID')}<input value={live[key]} onChange={(event) => setLive({ ...live, [key]: event.target.value })} /></label>)}<div className="contract-note"><Check size={15} /><span>REST and WebSocket scopes use these exact IDs. Mode is sent as <code>real</code>.</span></div></div></div>{errors.length > 0 && <div className="setup-errors" role="alert">{errors.map((error) => <span key={error}>{error}</span>)}</div>}<div className="modal-actions"><button className="button-quiet outline" onClick={onClose}>Cancel</button><button className="button-quiet" onClick={submit}>Save setup</button></div></section></div>
}

function App() {
  const mode = useAtlasStore((store) => store.mode)
  const snapshot = useAtlasStore((store) => store.snapshot)
  const providerStatus = useAtlasStore((store) => store.providerStatus)
  const selectedId = useAtlasStore((store) => store.selectedId)
  const search = useAtlasStore((store) => store.search)
  const setMode = useAtlasStore((store) => store.setMode)
  const applySnapshot = useAtlasStore((store) => store.applySnapshot)
  const setSelectedId = useAtlasStore((store) => store.setSelectedId)
  const setSearch = useAtlasStore((store) => store.setSearch)
  const [roomConfig, setRoomConfig] = useState<RoomModelConfig>(() => loadRoomConfig())
  const [liveSettings, setLiveSettings] = useState<LiveSettings>(() => loadLiveSettings())
  const [setupOpen, setSetupOpen] = useState(false)
  const [cameraPreset, setCameraPreset] = useState<'overview' | 'top' | 'focus'>('overview')
  const [cameraRequest, setCameraRequest] = useState(0)
  const [showLayers, setShowLayers] = useState({ entities: true, anchors: true, labels: true, confidence: true, zones: true })
  const [simulation, setSimulation] = useState<SimulationControls>({ playing: true, speed: 1, scenario: 'walkthrough' })
  const provider = useMemo(() => mode === 'LIVE' ? new LivePositionProvider({ ...liveSettings, mode: 'LIVE' } as LiveScope) : new MockPositionProvider(roomConfig), [liveSettings, mode, roomConfig])
  useEffect(() => { provider.start((payload) => { applySnapshot(payload); if (provider instanceof MockPositionProvider) setSimulation(provider.getSimulationControls()) }); return () => provider.stop() }, [applySnapshot, provider])
  const onMode = (nextMode: NormalizedMode) => { if (nextMode === 'REPLAY') return; setMode(nextMode); setSearch(''); setSelectedId(null); setCameraPreset('overview'); setCameraRequest((request) => request + 1) }
  const onSelect = (id: string) => { const nextCamera = cameraAfterSelection({ preset: cameraPreset, selectedId, request: cameraRequest }, id); setSelectedId(id); setCameraPreset(nextCamera.preset); setCameraRequest(nextCamera.request) }
  const onCameraPreset = (preset: 'overview' | 'top' | 'focus') => { setCameraPreset(preset); setCameraRequest((request) => request + 1) }
  const onRefresh = () => { void provider.refresh() }
  const onSaveSetup = (nextRoom: RoomModelConfig, nextLive: LiveSettings) => { setRoomConfig(nextRoom); setLiveSettings(nextLive); setSetupOpen(false); setCameraPreset('overview'); setCameraRequest((request) => request + 1) }
  const simulationProvider = provider instanceof MockPositionProvider ? provider : undefined
  const updateSimulation = (action: () => void) => { action(); if (simulationProvider) setSimulation(simulationProvider.getSimulationControls()) }
  return <div className="app-shell"><Navigation mode={mode} status={providerStatus} onMode={onMode} onOpenSetup={() => setSetupOpen(true)} /><div className="app-content"><TopBar mode={mode} status={providerStatus} snapshot={snapshot} onMode={onMode} onRefresh={onRefresh} onOpenSetup={() => setSetupOpen(true)} /><main className="main-grid"><Explorer state={snapshot} roomConfig={roomConfig} search={search} onSearch={setSearch} selectedId={selectedId} onSelect={onSelect} showLayers={showLayers} onToggle={(key) => setShowLayers((current) => ({ ...current, [key]: !current[key] }))} /><section className="map-region"><div className="map-header"><div><h1>Virginia Tech · Academic Classroom Building</h1><span>First-floor {modeCopy[mode].toLowerCase()} · {snapshot.counts.activeSessions} tracked devices</span></div><div className="map-revision"><span>Revision {snapshot.stateRevision}</span><span>{formatAge(snapshot.generatedAt)}</span></div></div><div className="map-stage"><CameraToolbar preset={cameraPreset} onPreset={onCameraPreset} /><MapCanvas state={snapshot} roomConfig={roomConfig} selectedId={selectedId} onSelect={onSelect} showEntities={showLayers.entities} showAnchors={showLayers.anchors} showLabels={showLayers.labels} showConfidence={showLayers.confidence} showZones={showLayers.zones} cameraPreset={cameraPreset} cameraRequest={cameraRequest} /><div className="map-legend"><span><i className="legend-dot entity" /> Devices</span><span><i className="legend-diamond" /> Anchors</span><span><i className="legend-ring" /> Uncertainty radius</span></div><div className="map-help">Drag to orbit or pan · scroll to zoom</div></div></section><DetailPanel state={snapshot} roomConfig={roomConfig} selectedId={selectedId} mode={mode} providerStatus={providerStatus} simulation={simulation} onClose={() => setSelectedId(null)} onSelect={onSelect} onSimulation={{ onPlaying: (playing) => updateSimulation(() => simulationProvider?.setPlaying(playing)), onRestart: () => updateSimulation(() => simulationProvider?.restart()), onSpeed: (speed) => updateSimulation(() => simulationProvider?.setSpeed(speed)), onScenario: (scenario) => updateSimulation(() => simulationProvider?.setScenario(scenario)) }} onOpenSetup={() => setSetupOpen(true)} /></main></div>{setupOpen && <SetupModal roomConfig={roomConfig} liveSettings={liveSettings} onClose={() => setSetupOpen(false)} onSave={onSaveSetup} />}</div>
}

export default App
