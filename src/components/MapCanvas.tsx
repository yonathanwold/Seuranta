import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Html, OrbitControls, useGLTF } from '@react-three/drei'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { PHOTO_ROOM_ASSET, roomAssetScaleXY, roomDimensions, type RoomModelConfig } from '../domain/roomModel'
import { mapToRoomAsset } from '../domain/coordinates'
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
}

const statusColor: Record<NodeHeartbeat['status'], string> = { online: '#12a772', degraded: '#a76212', offline: '#b94747' }
const displaySession = (sessionId: string) => sessionId.replace(/^session-/, '').slice(0, 4).toUpperCase()

function PhotoRoom({ roomConfig }: { roomConfig: RoomModelConfig }) {
  const { scene } = useGLTF(PHOTO_ROOM_ASSET.path)
  const model = useMemo(() => scene.clone(true), [scene])
  const scale = roomAssetScaleXY(roomConfig)
  useEffect(() => {
    model.visible = true
    // The operational view represents the first floor. Keep the supplied
    // upper stories in the source asset, but remove them from this scene.
    for (const hiddenGroup of ['Floor_02', 'Floor_03', 'Roof']) model.getObjectByName(hiddenGroup)?.removeFromParent()
    model.traverse((object) => {
      if (!(object instanceof THREE.Mesh)) return
      object.castShadow = true
      object.receiveShadow = true
      object.frustumCulled = true
    })
  }, [model])
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
  const [hovered, setHovered] = useState(false)
  const targetRef = useRef(new THREE.Vector3(target.x, target.y, target.z))
  useEffect(() => { targetRef.current.set(target.x, target.y, target.z) }, [target.x, target.y, target.z])
  useFrame((_state, delta) => {
    if (!group.current) return
    group.current.position.lerp(targetRef.current, Math.min(1, delta * 5.5))
  })
  const radius = Math.max(0.25, position.accuracyRadiusM)
  return <group ref={group} position={[target.x, target.y, target.z]} onClick={(event) => { event.stopPropagation(); onSelect() }} onPointerOver={() => setHovered(true)} onPointerOut={() => setHovered(false)}>
    {showConfidence && (selected || hovered) && <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.44, 0]}>
      <circleGeometry args={[radius, 48]} />
      <meshBasicMaterial color="#087f78" transparent opacity={selected ? 0.16 : 0.07} depthWrite={false} />
    </mesh>}
    <mesh castShadow>
      <sphereGeometry args={[selected ? 0.16 : 0.12, 20, 14]} />
      <meshStandardMaterial color="#087f78" emissive="#075e59" emissiveIntensity={selected ? 0.2 : 0.03} roughness={0.45} />
    </mesh>
    {(showLabels && (hovered || selected)) && <Html position={[0, 0.65, 0]} center zIndexRange={[1, 5]}>
      <div className={`scene-label ${selected ? 'is-selected' : ''}`}><span className="scene-label-dot" /><span><strong>Device {displaySession(position.sessionId)}</strong><small>{Math.round(position.confidence * 100)}% confidence · {position.accuracyRadiusM.toFixed(1)} m radius</small></span></div>
    </Html>}
  </group>
}

function CameraController({ preset, selected, cameraRequest, config }: { preset: MapCanvasProps['cameraPreset']; selected?: PositionEstimate; cameraRequest: number; config: RoomModelConfig }) {
  const { camera, size } = useThree()
  const controls = useRef<OrbitControlsImpl>(null)
  const transitionActive = useRef(false)
  const selectedRef = useRef(selected)
  selectedRef.current = selected
  const destination = useMemo(() => {
    void cameraRequest
    const { widthM, depthM } = roomDimensions(config)
    const span = Math.max(widthM, depthM)
    if (preset === 'top') return new THREE.Vector3(0, span * 1.8, 0.01)
    if (preset === 'focus' && selectedRef.current) {
      const point = mapToRoomAsset(selectedRef.current, config, 0)
      return new THREE.Vector3(point.x + span * 0.28, span * 0.38, point.z + span * 0.28)
    }
    return new THREE.Vector3(span * 0.82, span * 0.72, span * 0.82)
  // Selection coordinates are sampled only when an explicit camera request is
  // made. Telemetry ticks replace the selected object every 700 ms; they must
  // not reassert a preset or override a user's orbit.
  }, [config, preset, cameraRequest])
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
    camera.zoom = preset === 'focus' ? focusZoom : preset === 'top' ? topZoom : overviewZoom
    camera.updateProjectionMatrix()
    transitionActive.current = true
  }, [camera, cameraRequest, config, destination, preset, size.height, size.width])
  useFrame((_state, delta) => {
    if (!transitionActive.current) return
    const amount = Math.min(1, delta * 5.5)
    camera.position.lerp(destination, amount)
    controls.current?.target.lerp(lookTarget, amount)
    if (camera.position.distanceTo(destination) < 0.06) transitionActive.current = false
  })
  return <OrbitControls ref={controls} makeDefault enableDamping dampingFactor={0.08} minZoom={1} maxZoom={60} minPolarAngle={0.18} maxPolarAngle={Math.PI / 2.01} onStart={() => { transitionActive.current = false }} />
}

function FloorScene({ state, roomConfig, selectedId, onSelect, showEntities, showAnchors, showLabels, showConfidence, showZones, cameraPreset, cameraRequest }: MapCanvasProps) {
  const selected = state.positions.find((position) => position.sessionId === selectedId)
  const nodes = new Map(state.nodes.map((node) => [node.anchorId, node]))
  return <>
    <hemisphereLight args={['#ffffff', '#a7b6b2', 1.1]} />
    <directionalLight position={[50, 75, 50]} intensity={1.3} castShadow shadow-mapSize={[2048, 2048]} shadow-camera-left={-55} shadow-camera-right={55} shadow-camera-top={55} shadow-camera-bottom={-55} />
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.3, 0]} receiveShadow><planeGeometry args={[110, 75]} /><meshStandardMaterial color="#e7ecea" roughness={1} /></mesh>
    <PhotoRoom roomConfig={roomConfig} />
    <ZoneOverlay config={roomConfig} visible={showZones} />
    {showAnchors && roomConfig.anchors.map((anchor) => <AnchorMarker key={anchor.anchorId} anchor={anchor} node={nodes.get(anchor.anchorId)} showLabels={showLabels} config={roomConfig} onSelect={() => onSelect(anchor.anchorId)} />)}
    {showEntities && state.positions.map((position) => <EntityMarker key={position.sessionId} position={position} selected={selectedId === position.sessionId} showConfidence={showConfidence} showLabels={showLabels} config={roomConfig} onSelect={() => onSelect(position.sessionId)} />)}
    <CameraController preset={cameraPreset} selected={selected} cameraRequest={cameraRequest} config={roomConfig} />
  </>
}

export function MapCanvas(props: MapCanvasProps) {
  const [webglReady, setWebglReady] = useState(false)
  return <div className="map-canvas" aria-label="Interactive Virginia Tech first-floor map">
    {!webglReady && <div className="room-dom-fallback" aria-label="Room model fallback"><div className="room-fallback-shell"><div className="room-fallback-wall wall-north" /><div className="room-fallback-wall wall-west" /><div className="room-fallback-wall wall-east" /><div className="room-fallback-wall wall-south" /><div className="room-fallback-table" /><div className="room-fallback-sideboard" /><span>3D room view unavailable</span><small>Use the lists to inspect telemetry</small></div></div>}
    <Canvas onCreated={({ gl }) => setWebglReady(Boolean(gl.getContext?.()?.drawingBufferWidth))} shadows fallback={<div className="map-fallback-message"><strong>3D floor view unavailable</strong><span>Use the device and anchor lists to inspect the last known state. The model is still available for calibration in Floor setup.</span></div>} orthographic camera={{ position: [65, 58, 65], zoom: 5, near: 0.1, far: 300 }} gl={{ antialias: true }}>
      <Suspense fallback={<Html center><div className="model-loading">Loading Virginia Tech floor…</div></Html>}><FloorScene {...props} /></Suspense>
    </Canvas>
    <div className="map-scale" aria-hidden="true"><span>0</span><i /><span>1</span><i /><span>2 m</span></div>
    <div className="north-marker" aria-label="North orientation"><span>N</span><b /></div>
  </div>
}

useGLTF.preload(PHOTO_ROOM_ASSET.path)
