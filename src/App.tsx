import { useEffect, useMemo, useState } from 'react'
import { BarChart3, Building2, ChevronDown, ChevronRight, CircleHelp, Crosshair, Layers3, Map as MapIcon, Menu, Radio, Search, Settings2, Sparkles, Target, Users, Wifi, X, ZoomIn } from 'lucide-react'
import { MapCanvas } from './components/MapCanvas'
import { LivePositionProvider } from './domain/liveProvider'
import { MockPositionProvider } from './domain/mockProvider'
import { demoFloor } from './domain/floorDefinition'
import { useAtlasStore } from './domain/store'
import type { NormalizedMode, PositionEstimate, ProviderStatus } from './domain/types'

const iconSize = 17
const modeCopy: Record<NormalizedMode, string> = { SIMULATION: 'Simulation', LIVE: 'Live', REPLAY: 'Replay' }
const formatTime = (timestamp?: string) => timestamp ? new Intl.DateTimeFormat('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(timestamp)) : '—'
const formatAge = (timestamp: string) => { const seconds = Math.max(0, Math.round((Date.now() - new Date(timestamp).getTime()) / 1000)); return seconds < 2 ? 'just now' : `${seconds}s ago` }
const titleForSession = (sessionId: string) => `Device ${sessionId.replace(/^session-/, '').slice(0, 4).toUpperCase()}`
const zoneLabel = (zoneId?: string | null) => ({ office: 'Office zone', meeting: 'Meeting rooms', common: 'Common area', restricted: 'Restricted', corridor: 'Transit corridor' }[zoneId ?? ''] ?? 'Unassigned')

function StatusDot({ status }: { status: ProviderStatus | 'online' | 'degraded' | 'offline' }) { return <span className={`status-dot status-${status}`} aria-hidden="true" /> }

function Navigation({ mode, onMode }: { mode: NormalizedMode; onMode: (mode: NormalizedMode) => void }) {
  return <aside className="navigation">
    <div className="brand"><div className="brand-mark"><span /><span /><span /></div><div><strong>Seuranta</strong><small>Atlas</small></div></div>
    <p className="nav-caption">OPERATIONS</p>
    <nav aria-label="Primary navigation">
      <button className="nav-item"><MapIcon size={iconSize} /> <span>Overview</span></button>
      <button className="nav-item is-active"><Target size={iconSize} /> <span>Live map</span></button>
      <button className="nav-item"><BarChart3 size={iconSize} /> <span>Analytics</span></button>
      <button className="nav-item"><Settings2 size={iconSize} /> <span>Settings</span></button>
    </nav>
    <div className="nav-divider" />
    <div className="nav-mode">
      <div className="nav-mode-heading"><StatusDot status={mode === 'SIMULATION' ? 'online' : 'degraded'} /><span>{modeCopy[mode]}</span><ChevronRight size={15} /></div>
      <span>{mode === 'SIMULATION' ? 'Running · 5 devices' : 'Connected workspace'}</span>
      <div className="mode-options" role="group" aria-label="Data mode">
        {(['SIMULATION', 'LIVE', 'REPLAY'] as NormalizedMode[]).map((option) => <button key={option} className={mode === option ? 'is-selected' : ''} onClick={() => onMode(option)}>{modeCopy[option]}</button>)}
      </div>
    </div>
    <div className="nav-footer"><button className="nav-item"><CircleHelp size={iconSize} /><span>Help & support</span></button><div className="profile"><div className="avatar">SA</div><div><strong>Seuranta Admin</strong><span>Operations</span></div><ChevronDown size={15} /></div></div>
  </aside>
}

function Explorer({ state, search, onSearch, selectedId, onSelect, showLayers, onToggle }: { state: ReturnType<typeof useAtlasStore.getState>['snapshot']; search: string; onSearch: (value: string) => void; selectedId: string | null; onSelect: (id: string) => void; showLayers: { entities: boolean; anchors: boolean; labels: boolean; confidence: boolean; zones: boolean }; onToggle: (key: keyof typeof showLayers) => void }) {
  const visiblePositions = state.positions.filter((position) => `${position.sessionId} ${zoneLabel(position.zoneId)}`.toLowerCase().includes(search.toLowerCase()))
  const nodeMap = new Map(state.nodes.map((node) => [node.anchorId, node]))
  return <aside className="explorer">
    <div className="explorer-tabs"><button className="is-active">Entities</button><button>Map layers</button></div>
    <label className="search-box"><Search size={16} /><input value={search} onChange={(event) => onSearch(event.target.value)} placeholder="Search devices..." aria-label="Search devices" />{search && <button onClick={() => onSearch('')} aria-label="Clear search"><X size={14} /></button>}</label>
    <section className="explorer-section"><div className="section-heading"><span><Users size={15} /> Devices</span><strong>{visiblePositions.length}</strong></div>
      <div className="entity-list">{visiblePositions.map((position) => <button key={position.sessionId} className={`entity-row ${selectedId === position.sessionId ? 'is-selected' : ''}`} onClick={() => onSelect(position.sessionId)}><StatusDot status="online" /><span><strong>{titleForSession(position.sessionId)}</strong><small>{zoneLabel(position.zoneId)}</small></span><ChevronRight size={15} /></button>)}</div>
      {!visiblePositions.length && <p className="empty-note">No anonymous sessions match this search.</p>}
    </section>
    <section className="explorer-section anchors-section"><div className="section-heading"><span><Wifi size={15} /> Anchors</span><strong>{state.nodes.length}</strong></div>
      {demoFloor.anchors.map((anchor) => { const node = nodeMap.get(anchor.anchorId); return <button key={anchor.anchorId} className={`anchor-row ${selectedId === anchor.anchorId ? 'is-selected' : ''}`} onClick={() => onSelect(anchor.anchorId)}><span className="anchor-glyph" /><span>{anchor.label}</span><StatusDot status={node?.status ?? 'offline'} /><em>{node?.status ?? 'offline'}</em></button> })}
    </section>
    <section className="layer-section"><div className="section-heading"><span><Layers3 size={15} /> Map layers</span></div>
      {([['entities', 'Entities'], ['anchors', 'Anchors'], ['labels', 'Labels'], ['confidence', 'Confidence'], ['zones', 'Zones']] as Array<[keyof typeof showLayers, string]>).map(([key, label]) => <label className="toggle-row" key={key}><span>{label}</span><input type="checkbox" checked={showLayers[key]} onChange={() => onToggle(key)} /><i /></label>)}
    </section>
  </aside>
}

function TopBar({ mode, status, cameraPreset, onCameraPreset, onMode, onRefresh }: { mode: NormalizedMode; status: ProviderStatus; cameraPreset: 'overview' | 'top' | 'focus'; onCameraPreset: (preset: 'overview' | 'top' | 'focus') => void; onMode: (mode: NormalizedMode) => void; onRefresh: () => void }) {
  const freshness = status === 'live' ? 'Updated just now' : status === 'reconnecting' ? 'Reconnecting…' : status === 'error' ? 'Live source unavailable' : 'Waiting for data'
  return <header className="topbar"><div className="mobile-menu"><Menu size={18} /></div><button className="select-control"><Building2 size={16} /><span>Riverside Office</span><ChevronDown size={15} /></button><button className="select-control floor-control"><Layers3 size={16} /><span>Floor 2</span><ChevronDown size={15} /></button><div className="top-status"><StatusDot status={status === 'live' ? 'online' : status === 'reconnecting' ? 'degraded' : 'offline'} /><button onClick={() => onMode(mode === 'SIMULATION' ? 'LIVE' : 'SIMULATION')}>{modeCopy[mode]}</button><span className="freshness">{freshness}</span></div><div className="top-actions"><div className="camera-pills" role="group" aria-label="Camera preset"><button className={cameraPreset === 'overview' ? 'is-active' : ''} onClick={() => onCameraPreset('overview')}><Crosshair size={15} /> Overview</button><button className={cameraPreset === 'top' ? 'is-active' : ''} onClick={() => onCameraPreset('top')}><Layers3 size={15} /> Top</button><button className={cameraPreset === 'focus' ? 'is-active' : ''} onClick={() => onCameraPreset('focus')}><ZoomIn size={15} /> Focus</button></div><button className="button-quiet" onClick={onRefresh}><Radio size={15} /> Refresh</button></div></header>
}

function DetailPanel({ state, selectedId, onClose, onSelect }: { state: ReturnType<typeof useAtlasStore.getState>['snapshot']; selectedId: string | null; onClose: () => void; onSelect: (id: string) => void }) {
  const selected = state.positions.find((position) => position.sessionId === selectedId)
  const selectedNode = state.nodes.find((node) => node.anchorId === selectedId)
  if (selectedNode) return <aside className="detail-panel"><div className="detail-heading"><div className="detail-title"><span className="anchor-glyph large" /><div><h2>Anchor {selectedNode.anchorId.replace('a-', '')}</h2><p>Infrastructure node · {selectedNode.mode}</p></div></div><button className="icon-button" onClick={onClose} aria-label="Close details"><X size={18} /></button></div><div className="detail-body"><div className="status-callout"><StatusDot status={selectedNode.status} /><span>{selectedNode.status === 'online' ? 'Operating normally' : 'Needs attention'}</span></div><dl className="detail-list"><div><dt>Status</dt><dd className={`text-${selectedNode.status}`}>{selectedNode.status}</dd></div><div><dt>Buffer depth</dt><dd>{selectedNode.bufferDepth} batches</dd></div><div><dt>Observations sent</dt><dd>{selectedNode.observationsSentTotal.toLocaleString()}</dd></div><div><dt>Last observation</dt><dd>{selectedNode.lastObservationAt ? formatAge(selectedNode.lastObservationAt) : 'No signal'}</dd></div></dl><h3>Node diagnostics</h3>{selectedNode.errorCodes.length ? <ul className="diagnostic-list">{selectedNode.errorCodes.map((code) => <li key={code}><span className="warning-mark">!</span>{code.replaceAll('_', ' ')}</li>)}</ul> : <p className="muted-copy">No diagnostic codes reported.</p>}<h3>Anchor coverage</h3><div className="anchor-coverage">{state.nodes.map((node) => <button key={node.anchorId} className={node.anchorId === selectedId ? 'is-current' : ''} onClick={() => onSelect(node.anchorId)}><span className="anchor-glyph" /><span>{node.anchorId.replace('a-', 'Anchor ')}</span><StatusDot status={node.status} /></button>)}</div></div></aside>
  return <aside className="detail-panel"><div className="detail-heading"><div className="detail-title"><StatusDot status="online" /><div><h2>{selected ? titleForSession(selected.sessionId) : 'Select an entity'}</h2><p>{selected ? `Anonymous device · ${selected.sessionId.slice(-5).toUpperCase()}` : 'Choose a device or anchor on the map'}</p></div></div>{selected && <button className="icon-button" onClick={onClose} aria-label="Close details"><X size={18} /></button>}</div>{selected ? <div className="detail-body"><div className="detail-tabs"><button className="is-active">Details</button><button>Live trail</button><button>Zone history</button></div><div className="status-callout"><StatusDot status="online" /><span>Active ({modeCopy[selected.mode].toLowerCase()})</span></div><dl className="detail-list"><div><dt>Confidence</dt><dd>{Math.round(selected.confidence * 100)}%</dd></div><div><dt>Estimated accuracy</dt><dd>± {selected.accuracyRadiusM.toFixed(1)} m</dd></div><div><dt>Current zone</dt><dd>{zoneLabel(selected.zoneId)}</dd></div><div><dt>Coordinates (local)</dt><dd>X {selected.xM.toFixed(1)} m · Y {selected.yM.toFixed(1)} m</dd></div><div><dt>Last seen</dt><dd>{formatAge(selected.calculatedAt)}</dd></div></dl><div className="metric-line"><span>Signal confidence</span><strong>{Math.round(selected.confidence * 100)}%</strong><i><b style={{ width: `${selected.confidence * 100}%` }} /></i></div><h3>Anchors used ({selected.anchorsUsed.length})</h3><div className="anchor-coverage">{selected.anchorsUsed.map((anchorId) => <button key={anchorId}><span className="anchor-glyph" /><span>Anchor {anchorId.replace('a-', '')}</span><StatusDot status={state.nodes.find((node) => node.anchorId === anchorId)?.status ?? 'online'} /><BarChart3 size={14} /></button>)}</div><h3>Recent activity <button className="link-button">See all</button></h3><ActivityFeed state={state} selected={selected} /></div> : <div className="detail-empty"><Sparkles size={22} /><p>Click an anonymous device or anchor to inspect live telemetry.</p></div>}</aside>
}

function ActivityFeed({ state, selected }: { state: ReturnType<typeof useAtlasStore.getState>['snapshot']; selected: PositionEstimate }) {
  const events = state.recentEvents.filter((event) => !event.sessionId || event.sessionId === selected.sessionId).slice(0, 4)
  return <div className="activity-feed">{events.length ? events.map((event) => <div className="activity-row" key={event.eventId}><span className="activity-line" /><span className="activity-time">{formatTime(event.occurredAt)}</span><span>{event.eventType.replaceAll('_', ' ').toLowerCase().replace(/^./, (letter) => letter.toUpperCase())}{event.toZoneId ? ` · ${zoneLabel(event.toZoneId)}` : ''}</span></div>) : <p className="muted-copy">No recent transitions for this session.</p>}</div>
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
  const toggleLayer = useAtlasStore((store) => store.toggleLayer)
  const [cameraPreset, setCameraPreset] = useState<'overview' | 'top' | 'focus'>('overview')
  const [showLayers, setShowLayers] = useState({ entities: true, anchors: true, labels: true, confidence: true, zones: true })
  const provider = useMemo(() => mode === 'LIVE' ? new LivePositionProvider() : new MockPositionProvider(), [mode])
  useEffect(() => { provider.start(applySnapshot); return () => provider.stop() }, [provider, applySnapshot])
  const onMode = (nextMode: NormalizedMode) => { setMode(nextMode); setSearch(''); if (nextMode !== 'SIMULATION') setSelectedId(null) }
  const onSelect = (id: string) => { setSelectedId(id); if (id.startsWith('session-')) setCameraPreset((current) => current === 'focus' ? current : 'overview') }
  const onRefresh = () => { void provider.refresh() }
  return <div className="app-shell"><Navigation mode={mode} onMode={onMode} /><div className="app-content"><TopBar mode={mode} status={providerStatus} cameraPreset={cameraPreset} onCameraPreset={setCameraPreset} onMode={onMode} onRefresh={onRefresh} /><main className="main-grid"><Explorer state={snapshot} search={search} onSearch={setSearch} selectedId={selectedId} onSelect={onSelect} showLayers={showLayers} onToggle={(key) => { setShowLayers((current) => ({ ...current, [key]: !current[key] })); toggleLayer(`show${key.charAt(0).toUpperCase()}${key.slice(1)}` as 'showEntities' | 'showAnchors' | 'showLabels' | 'showConfidence' | 'showZones') }} /><section className="map-region"><div className="map-header"><div><h1>{demoFloor.label}</h1><span>{modeCopy[mode]} workspace · {snapshot.counts.activeSessions} active sessions</span></div><div className="map-revision"><span>Revision {snapshot.stateRevision}</span><span>{snapshot.generatedAt ? formatAge(snapshot.generatedAt) : '—'}</span></div></div><MapCanvas state={snapshot} selectedId={selectedId} onSelect={onSelect} showEntities={showLayers.entities} showAnchors={showLayers.anchors} showLabels={showLayers.labels} showConfidence={showLayers.confidence} showZones={showLayers.zones} cameraPreset={cameraPreset} /><div className="map-legend"><span><i className="legend-dot entity" /> Sessions</span><span><i className="legend-diamond" /> Anchors</span><span><i className="legend-ring" /> Uncertainty</span></div></section><DetailPanel state={snapshot} selectedId={selectedId} onClose={() => setSelectedId(null)} onSelect={onSelect} /></main></div></div>
}

export default App
