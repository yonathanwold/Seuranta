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

export const demoFloor: FloorDefinition = {
  definitionId: 'riverside-f2', buildingId: 'riverside-office', floorId: 'floor-2', label: 'Floor 2',
  widthM: 32, depthM: 22, slabThicknessM: 0.25, wallHeightM: 0.65, wallThicknessM: 0.16,
  rooms: [
    { roomId: 'conference-21', name: 'Conference 2.1', label: 'Conference\n2.1', xM: 2, yM: 15.5, widthM: 7.5, depthM: 4.5, zoneId: 'meeting', tone: 'meeting' },
    { roomId: 'office-22', name: 'Office 2.2', label: 'Office\n2.2', xM: 10, yM: 15.5, widthM: 5, depthM: 4.5, zoneId: 'office', tone: 'office' },
    { roomId: 'office-23', name: 'Office 2.3', label: 'Office\n2.3', xM: 22, yM: 15.5, widthM: 7.5, depthM: 4.5, zoneId: 'office', tone: 'office' },
    { roomId: 'meeting-24', name: 'Meeting 2.4', label: 'Meeting\n2.4', xM: 2, yM: 3, widthM: 7.5, depthM: 6, zoneId: 'meeting', tone: 'meeting' },
    { roomId: 'office-25', name: 'Office 2.5', label: 'Office\n2.5', xM: 10, yM: 3, widthM: 5.5, depthM: 6, zoneId: 'office', tone: 'office' },
    { roomId: 'kitchen-26', name: 'Kitchen 2.6', label: 'Kitchen\n2.6', xM: 16, yM: 3, widthM: 6, depthM: 6, zoneId: 'common', tone: 'common' },
    { roomId: 'storage-27', name: 'Storage 2.7', label: 'Storage\n2.7', xM: 23, yM: 3, widthM: 5.5, depthM: 6, zoneId: 'restricted', tone: 'restricted' },
  ],
  walls: [
    { xM: 0, yM: 0, lengthM: 32, thicknessM: 0.2, axis: 'x' }, { xM: 0, yM: 22, lengthM: 32, thicknessM: 0.2, axis: 'x' },
    { xM: 0, yM: 0, lengthM: 22, thicknessM: 0.2, axis: 'y' }, { xM: 32, yM: 0, lengthM: 22, thicknessM: 0.2, axis: 'y' },
    { xM: 9.7, yM: 3, lengthM: 6, thicknessM: 0.16, axis: 'y' }, { xM: 15.7, yM: 3, lengthM: 6, thicknessM: 0.16, axis: 'y' },
    { xM: 22.3, yM: 3, lengthM: 6, thicknessM: 0.16, axis: 'y' }, { xM: 9.7, yM: 15.5, lengthM: 4.5, thicknessM: 0.16, axis: 'y' },
    { xM: 15.7, yM: 15.5, lengthM: 4.5, thicknessM: 0.16, axis: 'y' }, { xM: 22.3, yM: 15.5, lengthM: 4.5, thicknessM: 0.16, axis: 'y' },
    { xM: 2, yM: 9.2, lengthM: 26.5, thicknessM: 0.16, axis: 'x' }, { xM: 2, yM: 15.2, lengthM: 26.5, thicknessM: 0.16, axis: 'x' },
  ],
  anchors: [
    { anchorId: 'a-01', label: 'A01', xM: 3.2, yM: 12 }, { anchorId: 'a-02', label: 'A02', xM: 28.5, yM: 11 },
    { anchorId: 'a-03', label: 'A03', xM: 4, yM: 2.2 }, { anchorId: 'a-04', label: 'A04', xM: 25.5, yM: 2.2 },
  ],
  zones: [
    { zoneId: 'office', name: 'Offices', color: '#dbeeee', polygon: [[10, 3], [15.5, 3], [15.5, 9], [10, 9]] },
    { zoneId: 'meeting', name: 'Meeting rooms', color: '#e1f0e9', polygon: [[2, 3], [9.5, 3], [9.5, 9], [2, 9]] },
    { zoneId: 'common', name: 'Common areas', color: '#f8ead2', polygon: [[16, 3], [22, 3], [22, 9], [16, 9]] },
    { zoneId: 'restricted', name: 'Restricted', color: '#f6dddd', polygon: [[22.5, 3], [28.5, 3], [28.5, 9], [22.5, 9]] },
  ],
}
