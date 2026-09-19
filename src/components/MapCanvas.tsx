import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Html, OrbitControls, useGLTF } from '@react-three/drei'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import { Suspense, useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import * as THREE from 'three'
import { PHOTO_ROOM_ASSET, roomAssetScaleXY, roomDimensions, type RoomModelConfig } from '../domain/roomModel'
import { mapToRoomAsset, roomAssetToMap } from '../domain/coordinates'
import { moveWithinFloor, walkthroughStart } from '../domain/walkthrough'
import { entityMarkerStyle, positionSourceLabel } from '../domain/marker'
import type { NodeHeartbeat, NormalizedState, PositionEstimate } from '../domain/types'

interface MapCanvasProps {
  state: NormalizedState
  roomConfig: RoomModelConfig
  selectedId: string | null
  onSelect: (id: string) => void
  showEntities: boolean
  showAnchors: boolean
  showLabels: boolean
  showConfidence: boolean
  showZones: boolean
  cameraPreset: 'overview' | 'top' | 'focus'
  cameraRequest: number
  buildingView: 'all' | 'floor-1'
  walkthrough: boolean
  staticPreview: boolean
  onExitWalkthrough: () => void
}

const statusColor: Record<NodeHeartbeat['status'], string> = { online: '#12a772', degraded: '#a76212', offline: '#b94747' }
const displaySession = (sessionId: string) => sessionId.replace(/^session-/, '').slice(0, 4).toUpperCase()

function PhotoRoom({ roomConfig, showAllFloors }: { roomConfig: RoomModelConfig; showAllFloors: boolean }) {
  const { scene } = useGLTF(PHOTO_ROOM_ASSET.path)
  const model = useMemo(() => {
    const clone = scene.clone(true)
    if (!showAllFloors) for (const hiddenGroup of ['Floor_02', 'Floor_03', 'Roof']) clone.getObjectByName(hiddenGroup)?.removeFromParent()
    clone.traverse((object) => {
      if (!(object instanceof THREE.Mesh)) return
      object.castShadow = true
      object.receiveShadow = true
      object.frustumCulled = true
    })
    return clone
  }, [scene, showAllFloors])
  const scale = roomAssetScaleXY(roomConfig)
  return <primitive object={model} scale={[scale.x, 1, scale.z]} rotation={[0, roomConfig.yawDeg * Math.PI / 180, 0]} />
}

function ZoneOverlay({ config, visible }: { config: RoomModelConfig; visible: boolean }) {
  if (!visible) return null
  const { widthM, depthM } = roomDimensions(config)
  return <group rotation={[0, config.yawDeg * Math.PI / 180, 0]}><mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.035, 0]}>
    <planeGeometry args={[Math.max(0, widthM - 0.35), Math.max(0, depthM - 0.35)]} />
    <meshBasicMaterial color="#dfecea" transparent opacity={0.18} depthWrite={false} />
  </mesh></group>
}

function AnchorMarker({ anchor, node, showLabels, onSelect, config }: { anchor: RoomModelConfig['anchors'][number]; node?: NodeHeartbeat; showLabels: boolean; onSelect: () => void; config: RoomModelConfig }) {
  const point = mapToRoomAsset(anchor, config, 0.42)
  const status = node?.status ?? 'offline'
  return <group position={[point.x, point.y, point.z]} rotation={[0, Math.PI / 4, 0]} onClick={(event) => { event.stopPropagation(); onSelect() }}>
    <mesh castShadow>
      <boxGeometry args={[0.22, 0.2, 0.22]} />
      <meshStandardMaterial color={statusColor[status]} roughness={0.56} />
    </mesh>
    <mesh position={[0, 0.13, 0]}>
      <boxGeometry args={[0.1, 0.06, 0.1]} />
      <meshStandardMaterial color="#f8fbfa" roughness={0.65} />
    </mesh>
    {showLabels && <Html position={[0.3, 0.2, 0]} center zIndexRange={[1, 5]}>
      <div className="scene-anchor-label"><span className="scene-anchor-status" style={{ background: statusColor[status] }} />{anchor.label}<small>{status}</small></div>
    </Html>}
  </group>
}

function EntityMarker({ position, selected, showConfidence, showLabels, onSelect, config }: { position: PositionEstimate; selected: boolean; showConfidence: boolean; showLabels: boolean; onSelect: () => void; config: RoomModelConfig }) {
  const target = mapToRoomAsset(position, config, 0.48)
  const group = useRef<THREE.Group>(null)
  const initial = useRef([target.x, target.y, target.z] as [number, number, number])
  const [hovered, setHovered] = useState(false)
  const targetRef = useRef(new THREE.Vector3(target.x, target.y, target.z))
  useEffect(() => { targetRef.current.set(target.x, target.y, target.z) }, [target.x, target.y, target.z])
  useFrame((_state, delta) => {
    if (!group.current) return
    group.current.position.lerp(targetRef.current, Math.min(1, delta * 5.5))
  })
  const radius = Math.max(0.25, position.accuracyRadiusM)
  return <group ref={group} position={initial.current} onClick={(event) => { event.stopPropagation(); onSelect() }} onPointerOver={() => setHovered(true)} onPointerOut={() => setHovered(false)}>
    {showConfidence && (selected || hovered) && <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.44, 0]}>
      <circleGeometry args={[radius, 48]} />
      <meshBasicMaterial color="#151515" transparent opacity={selected ? 0.12 : 0.05} depthWrite={false} />
    </mesh>}
    {selected && <mesh renderOrder={11}>
      <torusGeometry args={[0.68, entityMarkerStyle.selectedOutlineWidth, 12, 40]} />
      <meshBasicMaterial color={entityMarkerStyle.selectedOutline} depthTest={false} depthWrite={false} />
    </mesh>}
    <mesh renderOrder={10}>
      <sphereGeometry args={[selected ? 0.65 : 0.5, 16, 12]} />
      <meshBasicMaterial color={entityMarkerStyle.color} depthTest={false} depthWrite={false} />
    </mesh>
    {(showLabels && (hovered || selected)) && <Html position={[0, 0.65, 0]} center zIndexRange={[1, 5]}>
      <div className={`scene-label ${selected ? 'is-selected' : ''}`}><span className="scene-label-dot" /><span><strong>Device {displaySession(position.sessionId)}</strong><small>{positionSourceLabel(position)} · {Math.round(position.confidence * 100)}% confidence · {position.accuracyRadiusM.toFixed(1)} m radius</small></span></div>
    </Html>}
  </group>
}

function CameraController({ preset, selected, cameraRequest, config, buildingView }: { preset: MapCanvasProps['cameraPreset']; selected?: PositionEstimate; cameraRequest: number; config: RoomModelConfig; buildingView: MapCanvasProps['buildingView'] }) {
  const { camera, size } = useThree()
  const controls = useRef<OrbitControlsImpl>(null)
  const transitionActive = useRef(false)
  const selectedRef = useRef(selected)
  selectedRef.current = selected
  const destination = useMemo(() => {
    void cameraRequest
    const { widthM, depthM } = roomDimensions(config)
    const span = Math.max(widthM, depthM)
    const halfFov = 42 * Math.PI / 360
    const limitingAngle = Math.min(halfFov, Math.atan(Math.tan(halfFov) * size.width / Math.max(1, size.height)))
    const radius = Math.hypot(widthM, depthM, buildingView === 'all' ? PHOTO_ROOM_ASSET.nativeHeightM : 5) / 2
    const distance = radius / Math.sin(limitingAngle) * 1.15
    if (preset === 'top') return new THREE.Vector3(0, distance, 0.01)
    if (preset === 'focus' && selectedRef.current) {
      const point = mapToRoomAsset(selectedRef.current, config, 0)
      return new THREE.Vector3(point.x + span * 0.28, span * 0.38, point.z + span * 0.28)
    }
    return new THREE.Vector3(0.82, buildingView === 'all' ? 0.95 : 0.9, 0.82).normalize().multiplyScalar(distance)
  // Selection coordinates are sampled only when an explicit camera request is
  // made. Telemetry ticks replace the selected object every 700 ms; they must
  // not reassert a preset or override a user's orbit.
  }, [buildingView, config, preset, cameraRequest, size.width, size.height])
  const lookTarget = useMemo(() => {
    void cameraRequest
    if (preset === 'focus' && selectedRef.current) { const point = mapToRoomAsset(selectedRef.current, config, 0); return new THREE.Vector3(point.x, 0, point.z) }
    return new THREE.Vector3(0, 0, 0)
  }, [config, preset, cameraRequest])
  useEffect(() => {
    const { widthM, depthM } = roomDimensions(config)
    const span = Math.max(widthM, depthM)
    // R3F sizes its orthographic frustum in viewport pixels. Fit the calibrated
    // room to the available canvas instead of using a fixed zoom across screens.
    const overviewZoom = Math.min(size.width / Math.max(1, widthM * 1.42), size.height / Math.max(1, depthM * 1.85))
    const topZoom = Math.min(size.width / Math.max(1, widthM * 1.18), size.height / Math.max(1, depthM * 1.22))
    const focusZoom = Math.min(60, size.width / Math.max(1.8, span * 0.48))
    if (camera instanceof THREE.OrthographicCamera) {
      camera.zoom = preset === 'focus' ? focusZoom : preset === 'top' ? topZoom : overviewZoom
    } else if (camera instanceof THREE.PerspectiveCamera) {
      camera.fov = preset === 'focus' ? 34 : 42
    }
    camera.updateProjectionMatrix()
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      camera.position.copy(destination)
      controls.current?.target.copy(lookTarget)
      transitionActive.current = false
    } else transitionActive.current = true
  }, [camera, cameraRequest, config, destination, lookTarget, preset, size.height, size.width])
  useFrame((_state, delta) => {
    if (!transitionActive.current) return
    const amount = Math.min(1, delta * 5.5)
    camera.position.lerp(destination, amount)
    controls.current?.target.lerp(lookTarget, amount)
    if (camera.position.distanceTo(destination) < 0.06) transitionActive.current = false
  })
  return <OrbitControls ref={controls} makeDefault enableDamping dampingFactor={0.08} minZoom={1} maxZoom={60} minPolarAngle={0.18} maxPolarAngle={Math.PI / 2.01} onStart={() => { transitionActive.current = false }} />
}

function WalkthroughController({ config, onExit, readout }: { config: RoomModelConfig; onExit: () => void; readout: RefObject<HTMLOutputElement> }) {
  const { camera, gl } = useThree()
  const keys = useRef(new Set<string>())
  const taps = useRef(new Set<string>())
  const angles = useRef({ yaw: config.yawDeg * Math.PI / 180, pitch: 0 })
  const direction = useMemo(() => new THREE.Vector3(), [])
  const orientation = useMemo(() => new THREE.Euler(0, 0, 0, 'YXZ'), [])
  const elapsed = useRef(0)
  const exitRef = useRef(onExit)
  exitRef.current = onExit
  useEffect(() => {
    const start = mapToRoomAsset(walkthroughStart(config), config, 1.7)
    camera.position.set(start.x, start.y, start.z)
    angles.current = { yaw: config.yawDeg * Math.PI / 180, pitch: 0 }
    if (camera instanceof THREE.PerspectiveCamera) camera.fov = 65
    camera.updateProjectionMatrix()
    const canvas = gl.domElement
    canvas.tabIndex = 0
    canvas.setAttribute('aria-label', 'Walkthrough: WASD to move, drag to look, arrow keys to turn, Escape to exit')
    canvas.focus({ preventScroll: true })
    let dragging = false
    const down = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); exitRef.current(); return }
      if (['KeyW', 'KeyA', 'KeyS', 'KeyD', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.code)) { event.preventDefault(); keys.current.add(event.code); taps.current.add(event.code) }
    }
    const up = (event: KeyboardEvent) => keys.current.delete(event.code)
    const clear = () => { keys.current.clear(); taps.current.clear(); dragging = false }
    const pointerDown = (event: PointerEvent) => { if (event.button !== 0) return; canvas.focus(); dragging = true; canvas.setPointerCapture(event.pointerId) }
    const pointerUp = () => { dragging = false }
    const move = (event: PointerEvent) => {
      if (!dragging) return
      angles.current.yaw -= event.movementX * 0.004
      angles.current.pitch = Math.max(-1.2, Math.min(1.2, angles.current.pitch - event.movementY * 0.004))
    }
    canvas.addEventListener('keydown', down)
    canvas.addEventListener('keyup', up)
    canvas.addEventListener('blur', clear)
    window.addEventListener('blur', clear)
    canvas.addEventListener('pointerdown', pointerDown)
    canvas.addEventListener('pointerup', pointerUp)
    canvas.addEventListener('pointercancel', clear)
    canvas.addEventListener('pointermove', move)
    return () => {
      clear()
      canvas.removeEventListener('keydown', down)
      canvas.removeEventListener('keyup', up)
      canvas.removeEventListener('blur', clear)
      window.removeEventListener('blur', clear)
      canvas.removeEventListener('pointerdown', pointerDown)
      canvas.removeEventListener('pointerup', pointerUp)
      canvas.removeEventListener('pointercancel', clear)
      canvas.removeEventListener('pointermove', move)
      canvas.removeAttribute('tabindex')
      canvas.removeAttribute('aria-label')
    }
  }, [camera, config, gl])
  useFrame((_state, frameDelta) => {
    const delta = Math.min(frameDelta, 0.05)
    const has = (code: string) => keys.current.has(code) || taps.current.has(code)
    angles.current.yaw += (Number(has('ArrowLeft')) - Number(has('ArrowRight'))) * delta * 1.5
    angles.current.pitch = Math.max(-1.2, Math.min(1.2, angles.current.pitch + (Number(has('ArrowUp')) - Number(has('ArrowDown'))) * delta))
    orientation.set(angles.current.pitch, angles.current.yaw, 0)
    camera.quaternion.setFromEuler(orientation)
    const forward = Number(has('KeyW')) - Number(has('KeyS'))
    const right = Number(has('KeyD')) - Number(has('KeyA'))
    taps.current.clear()
    direction.set(right, 0, -forward).normalize().applyAxisAngle(THREE.Object3D.DEFAULT_UP, angles.current.yaw).multiplyScalar(delta * 4.2)
    const from = roomAssetToMap(camera.position, config)
    const to = roomAssetToMap({ x: camera.position.x + direction.x, y: 1.7, z: camera.position.z + direction.z }, config)
    const safe = mapToRoomAsset(moveWithinFloor(from, to, config), config, 1.7)
    camera.position.set(safe.x, safe.y, safe.z)
    elapsed.current += delta
    if (elapsed.current > 0.15 && readout.current) {
      readout.current.textContent = `Camera: ${from.xM.toFixed(1)}, ${from.yM.toFixed(1)} m · eye height 1.7 m`
      elapsed.current = 0
    }
  })
  return null
}

function FloorScene({ state, roomConfig, selectedId, onSelect, showEntities, showAnchors, showLabels, showConfidence, showZones, cameraPreset, cameraRequest, buildingView, walkthrough, onExitWalkthrough, readout }: MapCanvasProps & { readout: RefObject<HTMLOutputElement> }) {
  const selected = state.positions.find((position) => position.sessionId === selectedId)
  const nodes = new Map(state.nodes.map((node) => [node.anchorId, node]))
  return <>
    <hemisphereLight args={['#ffffff', '#a7b6b2', 1.1]} />
    <directionalLight position={[50, 75, 50]} intensity={1.3} castShadow shadow-mapSize={[2048, 2048]} shadow-camera-left={-55} shadow-camera-right={55} shadow-camera-top={55} shadow-camera-bottom={-55} />
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.3, 0]} receiveShadow><planeGeometry args={[110, 75]} /><meshStandardMaterial color="#e7ecea" roughness={1} /></mesh>
    <PhotoRoom roomConfig={roomConfig} showAllFloors={buildingView === 'all'} />
    <ZoneOverlay config={roomConfig} visible={showZones} />
    {showAnchors && roomConfig.anchors.map((anchor) => <AnchorMarker key={anchor.anchorId} anchor={anchor} node={nodes.get(anchor.anchorId)} showLabels={showLabels} config={roomConfig} onSelect={() => { if (!walkthrough) onSelect(anchor.anchorId) }} />)}
    {showEntities && state.positions.map((position) => <EntityMarker key={position.sessionId} position={position} selected={selectedId === position.sessionId} showConfidence={showConfidence} showLabels={showLabels} config={roomConfig} onSelect={() => { if (!walkthrough) onSelect(position.sessionId) }} />)}
    {walkthrough ? <WalkthroughController config={roomConfig} readout={readout} onExit={onExitWalkthrough} /> : <CameraController preset={cameraPreset} selected={selected} cameraRequest={cameraRequest} config={roomConfig} buildingView={buildingView} />}
  </>
}

function FloorFallback({ state, roomConfig, selectedId, onSelect, showEntities, showAnchors, showLabels, buildingView }: Pick<MapCanvasProps, 'state' | 'roomConfig' | 'selectedId' | 'onSelect' | 'showEntities' | 'showAnchors' | 'showLabels' | 'buildingView'>) {
  const { widthM, depthM } = roomDimensions(roomConfig)
  const point = (xM: number, yM: number) => ({ left: `${Math.max(2, Math.min(98, (xM - roomConfig.originXM) / widthM * 100))}%`, top: `${Math.max(2, Math.min(98, (1 - (yM - roomConfig.originYM) / depthM) * 100))}%` })
  return <div className="room-dom-fallback" aria-label={buildingView === 'all' ? 'Full building preview' : 'Static floor plan preview'}>
    <div className={`floor-plan-fallback ${buildingView === 'all' ? 'is-building-overview' : ''}`}>
      <div className="floor-plan-heading"><strong>{buildingView === 'all' ? 'VT ACB · Full building' : 'VT ACB · Floor 1'}</strong><span>2D floor preview · estimated geometry</span></div>
      {buildingView === 'all' && <div className="building-story-stack"><span>Floor 3</span><span>Floor 2</span><span>Floor 1 · tracked telemetry</span></div>}
      <div className="floor-plan-corridor" />
      <div className="floor-plan-room room-north"><span>North classrooms</span></div>
      <div className="floor-plan-room room-west"><span>West learning wing</span></div>
      <div className="floor-plan-room room-east"><span>East learning wing</span></div>
      <div className="floor-plan-room room-south"><span>South collaboration</span></div>
      {showAnchors && roomConfig.anchors.map((anchor) => <button key={anchor.anchorId} className="fallback-anchor" style={point(anchor.xM, anchor.yM)} onClick={() => onSelect(anchor.anchorId)} aria-label={`Select ${anchor.label}`}><span />{showLabels && <small>{anchor.label}</small>}</button>)}
      {showEntities && state.positions.map((position) => <button key={position.sessionId} className={`fallback-entity ${selectedId === position.sessionId ? 'is-selected' : ''}`} style={point(position.xM, position.yM)} onClick={() => onSelect(position.sessionId)} aria-label={`Select Device ${displaySession(position.sessionId)}`}><span />{showLabels && (selectedId === position.sessionId) && <small>Device {displaySession(position.sessionId)}</small>}</button>)}
      <div className="floor-plan-note">Select a device or anchor to inspect telemetry.</div>
    </div>
  </div>
}

export function MapCanvas(props: MapCanvasProps) {
  const [webglReady, setWebglReady] = useState(false)
  const readout = useRef<HTMLOutputElement>(null)
  return <div className={`map-canvas ${props.walkthrough ? 'is-walkthrough' : ''}`} aria-label={props.walkthrough ? 'First-person Virginia Tech building walkthrough' : 'Interactive Virginia Tech building map'}>
    {(!webglReady || props.staticPreview) && <FloorFallback {...props} />}
    {!props.staticPreview && <Canvas onCreated={({ gl }) => setWebglReady(Boolean(gl.getContext?.()?.drawingBufferWidth))} shadows fallback={null} camera={{ position: [65, 58, 65], fov: 42, near: 0.1, far: 2000 }} gl={{ antialias: true }}>
      <Suspense fallback={<Html center><div className="model-loading">Loading Virginia Tech floor…</div></Html>}><FloorScene {...props} readout={readout} /></Suspense>
    </Canvas>}
    {props.walkthrough && !props.staticPreview && webglReady && <div className="walkthrough-hud"><strong>Walkthrough mode</strong><span>W A S D to move · drag to look · arrow keys to turn · Escape to exit. Movement stays inside an approximate floor envelope.</span><output ref={readout} aria-live="off" /></div>}
    {(!webglReady || props.staticPreview) && <div className="map-fallback-note" role="status">{props.staticPreview ? '2D preview selected. Choose 3D map to use camera controls.' : 'Loading 3D. If WebGL is unavailable, use this selectable floor preview.'}</div>}
  </div>
}

useGLTF.preload(PHOTO_ROOM_ASSET.path)
