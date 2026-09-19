import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Html, OrbitControls, Text } from '@react-three/drei'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { demoFloor, type AnchorDefinition, type RectRoom } from '../domain/floorDefinition'
import { mapToWorld, positionToWorld } from '../domain/coordinates'
import type { NodeHeartbeat, NormalizedState, PositionEstimate } from '../domain/types'

interface MapCanvasProps {
  state: NormalizedState
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

const origin = { xM: demoFloor.widthM / 2, yM: demoFloor.depthM / 2 }
const toneColor: Record<RectRoom['tone'], string> = { office: '#e8f0ee', meeting: '#e3f1ea', common: '#f5ecda', restricted: '#f5dfdf' }
const statusColor: Record<NodeHeartbeat['status'], string> = { online: '#087f78', degraded: '#a76212', offline: '#b94747' }

function RoomSurface({ room, showLabels }: { room: RectRoom; showLabels: boolean }) {
  const center = mapToWorld({ xM: room.xM + room.widthM / 2, yM: room.yM + room.depthM / 2 }, origin, 0.015)
  return <group>
    <mesh position={[center.x, center.y, center.z]} receiveShadow>
      <boxGeometry args={[room.widthM - 0.2, 0.035, room.depthM - 0.2]} />
      <meshStandardMaterial color={toneColor[room.tone]} roughness={0.95} />
    </mesh>
    {showLabels && <Text position={[center.x, 0.08, center.z]} rotation={[-Math.PI / 2, 0, 0]} fontSize={0.44} color="#596c72" anchorX="center" anchorY="middle" lineHeight={1.25}>
      {room.label}
    </Text>}
  </group>
}

function Wall({ xM, yM, lengthM, thicknessM, axis }: { xM: number; yM: number; lengthM: number; thicknessM: number; axis: 'x' | 'y' }) {
  const point = mapToWorld({ xM: xM + (axis === 'x' ? lengthM / 2 : 0), yM: yM + (axis === 'y' ? lengthM / 2 : 0) }, origin, demoFloor.wallHeightM / 2)
  return <mesh position={[point.x, point.y, point.z]} castShadow receiveShadow>
    <boxGeometry args={axis === 'x' ? [lengthM, demoFloor.wallHeightM, thicknessM] : [thicknessM, demoFloor.wallHeightM, lengthM]} />
    <meshStandardMaterial color="#dce4e1" roughness={0.85} />
  </mesh>
}

function AnchorMarker({ anchor, node, showLabels, onSelect }: { anchor: AnchorDefinition; node?: NodeHeartbeat; showLabels: boolean; onSelect: () => void }) {
  const point = mapToWorld(anchor, origin, 0.5)
  const status = node?.status ?? 'offline'
  return <group position={[point.x, point.y, point.z]} rotation={[0, Math.PI / 4, 0]} onClick={(event) => { event.stopPropagation(); onSelect() }}>
    <mesh castShadow>
      <boxGeometry args={[0.55, 0.22, 0.55]} />
      <meshStandardMaterial color={statusColor[status]} roughness={0.5} />
    </mesh>
    <mesh position={[0, 0.14, 0]}>
      <boxGeometry args={[0.2, 0.08, 0.2]} />
      <meshStandardMaterial color="#f3f5f4" />
    </mesh>
    {showLabels && <Text position={[0.55, 0.22, 0]} rotation={[-Math.PI / 2, 0, 0]} fontSize={0.32} color={statusColor[status]} anchorX="left" anchorY="middle">
      {`${anchor.label}  ${status.toUpperCase()}`}
    </Text>}
  </group>
}

function EntityMarker({ position, selected, showConfidence, showLabels, onSelect }: { position: PositionEstimate; selected: boolean; showConfidence: boolean; showLabels: boolean; onSelect: () => void }) {
  const target = positionToWorld(position, origin, 0.52)
  const group = useRef<THREE.Group>(null)
  const [hovered, setHovered] = useState(false)
  useFrame((_state, delta) => {
    if (!group.current) return
    const speed = Math.min(1, delta * 4.5)
    group.current.position.lerp(new THREE.Vector3(target.x, target.y, target.z), speed)
  })
  const radius = Math.max(0.3, position.accuracyRadiusM)
  return <group ref={group} position={[target.x, target.y, target.z]} onClick={(event) => { event.stopPropagation(); onSelect() }} onPointerOver={() => setHovered(true)} onPointerOut={() => setHovered(false)}>
    {showConfidence && (selected || hovered) && <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.48, 0]}>
      <circleGeometry args={[radius, 48]} />
      <meshBasicMaterial color="#087f78" transparent opacity={selected ? 0.13 : 0.07} depthWrite={false} />
    </mesh>}
    <mesh castShadow>
      <sphereGeometry args={[selected ? 0.22 : 0.17, 20, 14]} />
      <meshStandardMaterial color="#087f78" emissive="#075e59" emissiveIntensity={selected ? 0.18 : 0.04} roughness={0.45} />
    </mesh>
    {(showLabels && (hovered || selected)) && <Html position={[0, 0.8, 0]} center zIndexRange={[1, 5]}>
      <div className={`scene-label ${selected ? 'is-selected' : ''}`}>
        <span className="scene-label-dot" />
        <span><strong>{displaySession(position.sessionId)}</strong><small>{position.zoneId ? zoneName(position.zoneId) : 'Transit corridor'} · ±{position.accuracyRadiusM.toFixed(1)} m</small></span>
      </div>
    </Html>}
  </group>
}

const displaySession = (sessionId: string) => sessionId.replace(/^session-/, '').slice(0, 4).toUpperCase()
const zoneName = (zoneId: string) => ({ office: 'Office zone', meeting: 'Meeting room', common: 'Common area', restricted: 'Restricted', corridor: 'Corridor' }[zoneId] ?? zoneId)

function CameraController({ preset, selected, cameraRequest }: { preset: MapCanvasProps['cameraPreset']; selected?: PositionEstimate; cameraRequest: number }) {
  const { camera } = useThree()
  const controls = useRef<OrbitControlsImpl>(null)
  const cameraTarget = useRef(new THREE.Vector3(27, 25, 27))
  const lookTarget = useRef(new THREE.Vector3(0, 0, 0))
  const transitionActive = useRef(false)
  const selectedRef = useRef(selected)
  selectedRef.current = selected
  const destination = useMemo(() => {
    const requestedSelection = cameraRequest >= 0 ? selectedRef.current : undefined
    return preset === 'top' ? new THREE.Vector3(0, 42, 0.01) : preset === 'focus' && requestedSelection ? (() => { const point = positionToWorld(requestedSelection, origin); return new THREE.Vector3(point.x + 13, 20, point.z + 13) })() : new THREE.Vector3(27, 25, 27)
  }, [preset, cameraRequest])
  useEffect(() => {
    cameraTarget.current.copy(destination)
    camera.zoom = preset === 'focus' ? 19 : preset === 'top' ? 13 : 11
    const target = preset === 'focus' && selectedRef.current ? positionToWorld(selectedRef.current, origin) : { x: 0, z: 0 }
    lookTarget.current.set(target.x, 0, target.z)
    transitionActive.current = true
    camera.updateProjectionMatrix()
  }, [camera, cameraRequest, destination, preset])
  useFrame((_state, delta) => {
    if (transitionActive.current) {
      const amount = Math.min(1, delta * 5.2)
      camera.position.lerp(cameraTarget.current, amount)
      controls.current?.target.lerp(lookTarget.current, amount)
      camera.lookAt(controls.current?.target ?? lookTarget.current)
      if (camera.position.distanceTo(cameraTarget.current) < 0.06) transitionActive.current = false
    }
  })
  return <OrbitControls ref={controls} makeDefault enableDamping dampingFactor={0.08} minZoom={8} maxZoom={30} minPolarAngle={0.45} maxPolarAngle={Math.PI / 2.08} onStart={() => { transitionActive.current = false }} />
}

function FloorScene({ state, selectedId, onSelect, showEntities, showAnchors, showLabels, showConfidence, showZones, cameraPreset, cameraRequest }: MapCanvasProps) {
  const selected = state.positions.find((position) => position.sessionId === selectedId)
  const nodes = new Map(state.nodes.map((node) => [node.anchorId, node]))
  return <>
    <hemisphereLight args={['#ffffff', '#a7b6b2', 0.9]} />
    <directionalLight position={[8, 28, 10]} intensity={1.25} castShadow shadow-mapSize={[2048, 2048]} shadow-camera-left={-25} shadow-camera-right={25} shadow-camera-top={25} shadow-camera-bottom={-25} />
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.28, 0]} receiveShadow>
      <planeGeometry args={[demoFloor.widthM + 5, demoFloor.depthM + 5]} />
      <meshStandardMaterial color="#f3f5f4" roughness={1} />
    </mesh>
    <mesh position={[0, -0.13, 0]} receiveShadow>
      <boxGeometry args={[demoFloor.widthM, demoFloor.slabThicknessM, demoFloor.depthM]} />
      <meshStandardMaterial color="#f9faf9" roughness={0.92} />
    </mesh>
    {showZones && demoFloor.rooms.map((room) => <RoomSurface key={room.roomId} room={room} showLabels={showLabels} />)}
    {demoFloor.walls.map((wall, index) => <Wall key={`${wall.axis}-${wall.xM}-${wall.yM}-${index}`} {...wall} />)}
    {showAnchors && demoFloor.anchors.map((anchor) => <AnchorMarker key={anchor.anchorId} anchor={anchor} node={nodes.get(anchor.anchorId)} showLabels={showLabels} onSelect={() => onSelect(anchor.anchorId)} />)}
    {showEntities && state.positions.map((position) => <EntityMarker key={position.sessionId} position={position} selected={selectedId === position.sessionId} showConfidence={showConfidence} showLabels={showLabels} onSelect={() => onSelect(position.sessionId)} />)}
    <CameraController preset={cameraPreset} selected={selected} cameraRequest={cameraRequest} />
  </>
}

export function MapCanvas(props: MapCanvasProps) {
  return <div className="map-canvas" aria-label="Interactive 3D floor map">
    <Canvas shadows fallback={<div className="map-fallback-message"><strong>3D map unavailable</strong><span>Use the entity and anchor lists to inspect the last known state.</span></div>} orthographic camera={{ position: [27, 25, 27], zoom: 11, near: 0.1, far: 200 }} gl={{ antialias: true }}>
      <FloorScene {...props} />
    </Canvas>
    <div className="map-scale" aria-hidden="true"><span>0</span><i /><span>5</span><i /><span>10 m</span></div>
    <div className="north-marker" aria-label="North orientation"><span>N</span><b /></div>
  </div>
}
