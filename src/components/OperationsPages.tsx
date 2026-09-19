import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { AlertTriangle, Check, Download, FileText, MapPin, Monitor, Plus, Search, Wifi, X } from 'lucide-react'
import type { RoomModelConfig } from '../domain/roomModel'
import type { NormalizedState, SpatialEvent } from '../domain/types'
import { buildWorkspace, type WorkspaceDevice, type WorkspaceEvent, type WorkspaceModel } from '../domain/workspace'
import { positionDetailFields } from '../domain/positionDetails'

export type OperationsPage = 'devices' | 'events' | 'reports'
interface OperationsPagesProps {
  page: OperationsPage
  snapshot: NormalizedState
  roomConfig: RoomModelConfig
  resolved: ReadonlySet<string>
  onResolve: (event: SpatialEvent) => void
  onSelectOnMap: (id: string) => void
}

function useNotice() {
  const [notice, setNotice] = useState('')
  const timer = useRef<ReturnType<typeof setTimeout>>()
  useEffect(() => () => clearTimeout(timer.current), [])
  const announce = (message: string) => {
    clearTimeout(timer.current)
    setNotice(message)
    timer.current = setTimeout(() => setNotice(''), 6000)
  }
  return [notice, announce] as const
}
function StatusPill({ status }: { status: string }) {
  return <span className={`status-pill status-pill-${status}`}><span className="status-pill-dot" />{status[0].toUpperCase() + status.slice(1)}</span>
}
function MetricCard({ icon, label, value, detail }: { icon: ReactNode; label: string; value: string | number; detail: string }) {
  return <article className="ops-metric"><span className="ops-metric-icon">{icon}</span><div><span className="ops-metric-label">{label}</span><strong>{value}</strong><small>{detail}</small></div></article>
}
function PageHeading({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <div className="ops-page-heading"><div><h1>{title}</h1><p>{description}</p></div>{action}</div>
}
function SearchField({ value, onChange, placeholder }: { value: string; onChange: (value: string) => void; placeholder: string }) {
  return <label className="ops-search"><Search size={16} /><input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} aria-label={placeholder} />{value && <button onClick={() => onChange('')} aria-label="Clear search"><X size={14} /></button>}</label>
}
function DevicesPage({ workspace, onSelectOnMap }: { workspace: WorkspaceModel; onSelectOnMap: (id: string) => void }) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<'all' | WorkspaceDevice['status']>('all')
  const [zone, setZone] = useState('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [notice, announce] = useNotice()
  const filtered = workspace.devices.filter((device) => (filter === 'all' || device.status === filter) && (zone === 'all' || device.spaceId === zone) && `${device.sessionId} ${device.spaceName}`.toLowerCase().includes(query.trim().toLowerCase()))
  const selected = filtered.find((device) => device.sessionId === selectedId) ?? filtered[0]
  return <section className="operations-page devices-page">
    <PageHeading title="Devices" description="Anonymous positioning sessions from the current snapshot. Health uses position age and confidence; battery and radio strength are not reported." action={<button className="button-quiet" onClick={() => announce('Demo only: enrollment needs the live ingest service. No device was added.')}><Plus size={15} /> Add device · demo</button>} />
    <div className="ops-metrics-grid">
      <MetricCard icon={<Monitor size={19} />} label="Online devices" value={workspace.onlineDevices} detail="Fresh position · confidence at least 72%" />
      <MetricCard icon={<AlertTriangle size={19} />} label="Needs attention" value={workspace.degradedDevices + workspace.offlineDevices} detail={`${workspace.degradedDevices} degraded · ${workspace.offlineDevices} stale`} />
      <MetricCard icon={<Wifi size={19} />} label="Planned anchors" value={workspace.anchors.length} detail={`${workspace.anchors.filter(({ node }) => node?.status === 'online').length} report online`} />
      <MetricCard icon={<Monitor size={19} />} label="Tracked devices" value={workspace.devices.length} detail="Same sessions as the map" />
    </div>
    <div className="ops-toolbar"><SearchField value={query} onChange={setQuery} placeholder="Search anonymous IDs or rooms..." /><div className="ops-filter-row">
      {(['all', 'online', 'degraded', 'offline'] as const).map((status) => <button key={status} aria-pressed={filter === status} className={`filter-chip ${filter === status ? 'is-active' : ''}`} onClick={() => setFilter(status)}>{status === 'all' ? 'All devices' : status[0].toUpperCase() + status.slice(1)} ({status === 'all' ? workspace.devices.length : workspace.devices.filter((device) => device.status === status).length})</button>)}
      <select className="filter-select" aria-label="Filter devices by room" value={zone} onChange={(event) => setZone(event.target.value)}><option value="all">All rooms</option>{workspace.spaces.map((space) => <option key={space.id} value={space.id}>{space.name}</option>)}<option value="unassigned">Unassigned</option></select>
    </div></div>
    <div className="ops-content-grid devices-content"><section className="ops-table-card" aria-label="Device inventory"><div className="ops-table-scroll" tabIndex={0} role="region" aria-label="Scrollable device table"><div className="ops-table-head device-grid"><span>ID</span><span>Health</span><span>Confidence</span><span>Last position</span><span>Room</span></div>
      {filtered.map((device) => <button key={device.sessionId} aria-pressed={selected?.sessionId === device.sessionId} className={`ops-table-row device-grid ${selected?.sessionId === device.sessionId ? 'is-selected' : ''}`} onClick={() => setSelectedId(device.sessionId)}><span className="cell-id">{device.id}</span><span><StatusPill status={device.status} /></span><span>{Math.round(device.confidence * 100)}%</span><span>{device.lastSeen}</span><span title={device.spaceName}>{device.spaceName}</span></button>)}
    </div>{!filtered.length && <p className="ops-empty">No devices match these filters.</p>}<div className="ops-table-footer">Showing {filtered.length} of {workspace.devices.length} devices · complete snapshot</div></section>
    {selected && <aside className="ops-inspector"><div className="inspector-header"><div><h2>Device {selected.id}</h2><p>{selected.sessionId}</p></div><StatusPill status={selected.status} /></div><dl className="inspector-list">
      {positionDetailFields(selected.position, new Date().toISOString(), selected.status, selected.spaceName).map((field) => <div key={field.key}><dt>{field.label}</dt><dd title={field.value}>{field.value}</dd></div>)}
    </dl><div className="inspector-section"><h3>How to read health</h3><p className="muted-copy">Offline means the position is at least 30 seconds older than the snapshot. Degraded means it is 10–30 seconds old, below 72% confidence, or outside the map. It is not a hardware heartbeat.</p></div><div className="inspector-actions"><button className="button-quiet" onClick={() => onSelectOnMap(selected.sessionId)}><MapPin size={15} /> Locate in map</button></div></aside>}</div>
    {notice && <div className="ops-toast" role="status">{notice}</div>}
  </section>
}

function EventsPage({ workspace, onResolve }: { workspace: WorkspaceModel; onResolve: (event: SpatialEvent) => void }) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<'all' | WorkspaceEvent['severity']>('all')
  const [reviewState, setReviewState] = useState('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [notice, announce] = useNotice()
  const filtered = workspace.events.filter((event) => (filter === 'all' || event.severity === filter) && (reviewState === 'all' || event.status === reviewState) && `${event.title} ${event.sourceLabel} ${event.spaceName}`.toLowerCase().includes(query.trim().toLowerCase()))
  const selected = filtered.find((event) => event.id === selectedId)
  return <section className="operations-page events-page">
    <PageHeading title="Events" description="Review the current event window. Resolve is a local demo acknowledgment, kept while navigating this workspace and cleared on reload or source changes." />
    <div className="ops-metrics-grid">
      <MetricCard icon={<FileText size={19} />} label="Events in window" value={workspace.events.length} detail="Records in the current snapshot" />
      <MetricCard icon={<AlertTriangle size={19} />} label="Warnings" value={workspace.events.filter((event) => event.severity === 'warning').length} detail="Based on the event’s reported confidence" />
      <MetricCard icon={<Check size={19} />} label="Resolved locally" value={workspace.events.filter((event) => event.status === 'resolved').length} detail="Demo acknowledgments · no API write" />
      <MetricCard icon={<FileText size={19} />} label="Unreviewed" value={workspace.events.filter((event) => event.status === 'active').length} detail="Not necessarily an alert" />
    </div>
    <div className="ops-toolbar"><SearchField value={query} onChange={setQuery} placeholder="Search events, anonymous IDs, or rooms..." /><div className="ops-filter-row">
      {(['all', 'critical', 'warning', 'info'] as const).map((severity) => <button key={severity} aria-pressed={filter === severity} className={`filter-chip ${filter === severity ? 'is-active' : ''}`} onClick={() => setFilter(severity)}>{severity === 'all' ? 'All events' : severity[0].toUpperCase() + severity.slice(1)} ({severity === 'all' ? workspace.events.length : workspace.events.filter((event) => event.severity === severity).length})</button>)}
      <select className="filter-select" aria-label="Filter event review state" value={reviewState} onChange={(event) => setReviewState(event.target.value)}><option value="all">All review states</option><option value="active">Unreviewed</option><option value="resolved">Resolved locally</option></select>
    </div></div>
    <div className="ops-content-grid events-content"><section className="ops-table-card" aria-label="Event history"><div className="ops-table-scroll" tabIndex={0} role="region" aria-label="Scrollable event table"><div className="ops-table-head event-grid"><span>Time</span><span>Event / room</span><span>Severity</span><span>Source</span><span>Review</span></div>
      {filtered.map((event) => <button key={event.id} aria-pressed={selected?.id === event.id} className={`ops-table-row event-grid ${selected?.id === event.id ? 'is-selected' : ''}`} onClick={() => setSelectedId(event.id)}><span>{event.occurredAt}</span><span className="event-cell">{event.title}<small>{event.spaceName}</small></span><span><StatusPill status={event.severity} /></span><span>{event.sourceLabel}</span><span><StatusPill status={event.status} /></span></button>)}
    </div>{!filtered.length && <p className="ops-empty">No events match these filters.</p>}<div className="ops-table-footer">Showing {filtered.length} of {workspace.events.length} events</div></section>
    {selected ? <aside className="ops-inspector event-inspector"><div className="inspector-header"><div><h2>{selected.title}</h2><p>Event ID · {selected.id}</p></div><button className="icon-button" aria-label="Close event" onClick={() => setSelectedId(null)}><X size={18} /></button></div><div className="inspector-badges"><StatusPill status={selected.severity} /><StatusPill status={selected.status} /></div><dl className="inspector-list"><div><dt>Occurred</dt><dd>{selected.occurredAt}</dd></div><div><dt>Source</dt><dd>{selected.sourceLabel}</dd></div><div><dt>Room at event time</dt><dd>{selected.spaceName}</dd></div></dl><div className="event-description"><strong>Description</strong><p>{selected.description}</p></div><div className="inspector-actions"><button className="button-quiet" disabled={selected.status === 'resolved'} onClick={() => { onResolve(selected.event); announce('Resolved locally for this demo. No backend event was changed.') }}><Check size={15} />{selected.status === 'resolved' ? 'Resolved locally' : 'Resolve · demo'}</button></div></aside> : <aside className="ops-inspector"><p className="ops-empty">Select an event to inspect its source and resolve it locally.</p></aside>}</div>
    {notice && <div className="ops-toast" role="status">{notice}</div>}
  </section>
}

function ReportsPage({ workspace, snapshot }: { workspace: WorkspaceModel; snapshot: NormalizedState }) {
  const [notice, announce] = useNotice()
  const assigned = workspace.spaces.reduce((sum, space) => sum + space.occupancy, 0)
  const exportSnapshot = () => {
    const report = { mode: snapshot.mode, generatedAt: snapshot.generatedAt, revision: snapshot.stateRevision, scope: { runId: snapshot.runId, deploymentId: snapshot.deploymentId, buildingId: snapshot.buildingId, floorId: snapshot.floorId }, devices: workspace.devices.map(({ sessionId, status, xM, yM, confidence, spaceName }) => ({ sessionId, status, xM, yM, confidence, room: spaceName })), rooms: workspace.spaces.map(({ name, occupancy }) => ({ name, occupancy })), events: workspace.events.map(({ id, title, severity, status, occurredAt }) => ({ id, title, severity, localReview: status, occurredAt })) }
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `seuranta-${snapshot.mode.toLowerCase()}-snapshot-${snapshot.stateRevision}.json`
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    announce('Downloaded the current snapshot as JSON. This is a local export, not a historical report.')
  }
  return <section className="operations-page reports-page">
    <PageHeading title="Reports" description="A current-snapshot summary of the same anonymous sessions, rooms, anchors, and events shown elsewhere. Historical analytics are not connected." action={<button className="button-quiet" onClick={exportSnapshot}><Download size={15} /> Download snapshot JSON</button>} />
    <div className="ops-metrics-grid">
      <MetricCard icon={<Monitor size={19} />} label="Tracked devices" value={workspace.devices.length} detail={`${assigned} assigned to modeled rooms · ${workspace.devices.length - assigned} unassigned`} />
      <MetricCard icon={<Monitor size={19} />} label="Average confidence" value={`${Math.round(workspace.averageConfidence * 100)}%`} detail="Position confidence · not measured accuracy" />
      <MetricCard icon={<FileText size={19} />} label="Events in window" value={workspace.events.length} detail={`${workspace.eventsLastHour} in last hour reported by provider`} />
      <MetricCard icon={<Check size={19} />} label="Resolved locally" value={workspace.events.filter((event) => event.status === 'resolved').length} detail="Same local review state as Events" />
    </div>
    <div className="reports-grid snapshot-reports">
      <section className="report-chart-card"><div className="report-card-heading"><div><h2>Current room occupancy</h2><p>Anonymous devices by reported zone · counts, not people or capacity</p></div></div><div className="bar-list">{workspace.spaces.map((space) => <div className="bar-row" key={space.id}><span>{space.name}</span><i aria-hidden="true"><b style={{ width: `${workspace.devices.length ? space.occupancy / workspace.devices.length * 100 : 0}%` }} /></i><strong>{space.occupancy}</strong></div>)}</div></section>
      <section className="report-chart-card"><div className="report-card-heading"><div><h2>Position health</h2><p>Current records · no uptime history</p></div></div><dl className="report-values"><div><dt>Online</dt><dd>{workspace.onlineDevices}</dd></div><div><dt>Degraded</dt><dd>{workspace.degradedDevices}</dd></div><div><dt>Offline / stale</dt><dd>{workspace.offlineDevices}</dd></div></dl><p className="muted-copy">Health is relative to the snapshot timestamp. Paused simulation keeps its last values.</p></section>
      <section className="report-chart-card"><div className="report-card-heading"><div><h2>Planned anchors</h2><p>Configuration and heartbeats used by the map</p></div></div><dl className="report-values">{workspace.anchors.map(({ anchor, node }) => <div key={anchor.anchorId}><dt>{anchor.label}<small>{anchor.anchorId} · {anchor.xM.toFixed(1)}, {anchor.yM.toFixed(1)} m</small></dt><dd><StatusPill status={node?.status ?? 'offline'} /></dd></div>)}</dl></section>
      <section className="report-chart-card"><div className="report-card-heading"><div><h2>Event summary</h2><p>Severity comes from each event, not the device’s current state</p></div></div><dl className="report-values">{(['critical', 'warning', 'info'] as const).map((severity) => <div key={severity}><dt><StatusPill status={severity} /></dt><dd>{workspace.events.filter((event) => event.severity === severity).length}</dd></div>)}</dl></section>
    </div>
    <p className="report-provenance">{snapshot.mode === 'SIMULATION' ? 'Simulation data' : 'Live source data'} · Revision {snapshot.stateRevision} · {new Date(snapshot.generatedAt).toLocaleString()}. Geometry and planned anchors are estimates. Scheduled exports and historical reports are not available.</p>
    {notice && <div className="ops-toast" role="status">{notice}</div>}
  </section>
}

export function OperationsPages({ page, snapshot, roomConfig, resolved, onResolve, onSelectOnMap }: OperationsPagesProps) {
  useEffect(() => { document.querySelector('.operations-main')?.scrollTo({ top: 0, left: 0 }) }, [page])
  const workspace = useMemo(() => buildWorkspace(snapshot, roomConfig, resolved), [roomConfig, snapshot, resolved])
  if (page === 'devices') return <DevicesPage workspace={workspace} onSelectOnMap={onSelectOnMap} />
  if (page === 'events') return <EventsPage workspace={workspace} onResolve={onResolve} />
  return <ReportsPage workspace={workspace} snapshot={snapshot} />
}
