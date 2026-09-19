import type { AnchorDefinition } from './floorDefinition'

/** Virginia Tech Academic Classroom Building reference model. */
export const PHOTO_ROOM_ASSET = {
  path: '/models/vt-academic-classroom.glb',
  compressedPath: '/models/vt-academic-classroom.meshopt.glb',
  metadataPath: '/models/vt-academic-classroom.metadata.json',
  sha256: '9834679914E770DE52F2040B2C75E2F84671AB8762E602222C938A99D24A9605',
  compressedSha256: '58A9D14074CB1CB94EBF55E86C8FCF02233EF134327F15773F1FA014FE562D87',
  nativeWidthM: 76.91949950158596,
  nativeDepthM: 44.64731623977423,
  nativeHeightM: 21.55943062901497,
  nominalInnerWidthM: 76.91949950158596,
  nominalInnerDepthM: 44.64731623977423,
  scaleUncertaintyFraction: 0.15,
  measured: false,
} as const

export interface RoomModelConfig {
  measuredWidthM: number
  measuredDepthM: number
  yawDeg: number
  originXM: number
  originYM: number
  anchors: AnchorDefinition[]
}

export const defaultRoomConfig: RoomModelConfig = {
  measuredWidthM: PHOTO_ROOM_ASSET.nativeWidthM,
  measuredDepthM: PHOTO_ROOM_ASSET.nativeDepthM,
  yawDeg: 0,
  originXM: 0,
  originYM: 0,
  anchors: [
    { anchorId: 'vt-acb-01', label: 'West entry', xM: 3.6, yM: 25.3 },
    { anchorId: 'vt-acb-02', label: 'North classrooms', xM: 38.2, yM: 38.0 },
    { anchorId: 'vt-acb-03', label: 'East entry', xM: 70.8, yM: 24.0 },
    { anchorId: 'vt-acb-04', label: 'South learning wing', xM: 40.0, yM: 11.8 },
  ],
}

export function roomScale(config: RoomModelConfig): number {
  return config.measuredWidthM / PHOTO_ROOM_ASSET.nativeWidthM
}

export function roomDimensions(config: RoomModelConfig): { widthM: number; depthM: number } {
  return { widthM: config.measuredWidthM, depthM: config.measuredDepthM }
}

export function roomAssetScaleXY(config: RoomModelConfig): { x: number; z: number } {
  return { x: config.measuredWidthM / PHOTO_ROOM_ASSET.nativeWidthM, z: config.measuredDepthM / PHOTO_ROOM_ASSET.nativeDepthM }
}

export function validateRoomConfig(config: RoomModelConfig): string[] {
  const errors: string[] = []
  const dimensions = roomDimensions(config)
  if (!Number.isFinite(config.measuredWidthM) || config.measuredWidthM < 10 || config.measuredWidthM > 300) errors.push('Floor width must be between 10 and 300 metres.')
  if (!Number.isFinite(config.measuredDepthM) || config.measuredDepthM < 10 || config.measuredDepthM > 300) errors.push('Floor depth must be between 10 and 300 metres.')
  if (!Number.isFinite(config.yawDeg) || config.yawDeg < -180 || config.yawDeg > 180) errors.push('Yaw must be between -180° and 180°.')
  if (!Number.isFinite(config.originXM) || !Number.isFinite(config.originYM)) errors.push('The coordinate origin must be finite.')
  if (config.anchors.length < 3) errors.push('Plan at least three anchors for floor positioning.')
  const ids = new Set<string>()
  for (const anchor of config.anchors) {
    if (!anchor.anchorId.trim()) errors.push('Every anchor needs an ID.')
    if (ids.has(anchor.anchorId)) errors.push(`Anchor ID ${anchor.anchorId} is duplicated.`)
    ids.add(anchor.anchorId)
    if (![anchor.xM, anchor.yM].every(Number.isFinite)) errors.push(`${anchor.label || anchor.anchorId} needs finite coordinates.`)
    else if (anchor.xM < config.originXM || anchor.xM > config.originXM + dimensions.widthM || anchor.yM < config.originYM || anchor.yM > config.originYM + dimensions.depthM) errors.push(`${anchor.label || anchor.anchorId} is outside the calibrated floor.`)
  }
  return errors
}

const storageKey = 'seuranta.vt-academic-floor.v1'

export function loadRoomConfig(): RoomModelConfig {
  if (typeof localStorage === 'undefined') return defaultRoomConfig
  try {
    const parsed = JSON.parse(localStorage.getItem(storageKey) ?? '') as Partial<RoomModelConfig>
    if (!parsed || !Array.isArray(parsed.anchors)) return defaultRoomConfig
    const candidate: RoomModelConfig = {
      measuredWidthM: Number(parsed.measuredWidthM), measuredDepthM: Number(parsed.measuredDepthM), yawDeg: Number(parsed.yawDeg), originXM: Number(parsed.originXM), originYM: Number(parsed.originYM),
      anchors: parsed.anchors.map((anchor) => ({ anchorId: String(anchor.anchorId ?? ''), label: String(anchor.label ?? ''), xM: Number(anchor.xM), yM: Number(anchor.yM) })),
    }
    return validateRoomConfig(candidate).length ? defaultRoomConfig : candidate
  } catch {
    return defaultRoomConfig
  }
}

export function saveRoomConfig(config: RoomModelConfig): void {
  if (typeof localStorage !== 'undefined') localStorage.setItem(storageKey, JSON.stringify(config))
}

export function resetRoomConfig(): RoomModelConfig {
  if (typeof localStorage !== 'undefined') localStorage.removeItem(storageKey)
  return defaultRoomConfig
}
