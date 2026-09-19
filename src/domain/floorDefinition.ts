export interface RectRoom {
  roomId: string
  name: string
  label: string
  xM: number
  yM: number
  widthM: number
  depthM: number
  zoneId: string
  tone: 'office' | 'meeting' | 'common' | 'restricted'
}

export interface WallSegment { xM: number; yM: number; lengthM: number; thicknessM: number; axis: 'x' | 'y' }
export interface AnchorDefinition { anchorId: string; label: string; xM: number; yM: number }
export interface ZoneDefinition { zoneId: string; name: string; color: string; polygon: Array<[number, number]> }

export interface FloorDefinition {
  definitionId: string
  buildingId: string
  floorId: string
  label: string
  widthM: number
  depthM: number
  slabThicknessM: number
  wallHeightM: number
  wallThicknessM: number
  rooms: RectRoom[]
  walls: WallSegment[]
  anchors: AnchorDefinition[]
  zones: ZoneDefinition[]
}

/** Estimated first-floor footprint from the supplied Virginia Tech model. */
export const demoFloor: FloorDefinition = {
  definitionId: 'vt-academic-classroom-floor-1-v1', buildingId: 'vt-academic-classroom-building', floorId: 'floor-1', label: 'Academic Classroom Building · Floor 1',
  widthM: 76.9195, depthM: 44.6473, slabThicknessM: 0.26, wallHeightM: 4.5, wallThicknessM: 0.2,
  rooms: [], walls: [],
  anchors: [
    { anchorId: 'vt-acb-01', label: 'West entry', xM: 3.6, yM: 25.3 },
    { anchorId: 'vt-acb-02', label: 'North classrooms', xM: 38.2, yM: 38 },
    { anchorId: 'vt-acb-03', label: 'East entry', xM: 70.8, yM: 24 },
    { anchorId: 'vt-acb-04', label: 'South learning wing', xM: 40, yM: 11.8 },
  ],
  zones: [
    { zoneId: 'main-circulation', name: 'Main circulation', color: '#dfecea', polygon: [[2.4, 30.7], [11.6, 30.7], [11.6, 31], [63.7, 31], [63.7, 33.2], [70.8, 33.2], [70.8, 26.5], [62, 25.6], [48, 24.2], [18, 21], [7.4, 20], [7.4, 24], [2.9, 23.2]] },
  ],
}
