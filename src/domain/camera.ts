export type CameraPreset = 'overview' | 'top' | 'focus'

export interface SelectionCameraState {
  preset: CameraPreset
  selectedId: string | null
  request: number
}

/** Apply one selection change without coupling camera requests to telemetry updates. */
export function cameraAfterSelection(current: SelectionCameraState, nextId: string): SelectionCameraState {
  if (!nextId.startsWith('session-')) return { ...current, selectedId: nextId }
  if (current.preset === 'focus' && current.selectedId !== nextId) return { ...current, selectedId: nextId, request: current.request + 1 }
  if (current.preset !== 'focus') return { ...current, selectedId: nextId, preset: 'overview' }
  return { ...current, selectedId: nextId }
}
