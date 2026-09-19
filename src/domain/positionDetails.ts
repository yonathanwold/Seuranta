import { positionSourceLabel } from './marker'
import type { PositionEstimate } from './types'

export interface PositionDetailField {
  key: string
  label: string
  value: string
}

const unavailable = 'Unavailable'
const numberValue = (value: number, digits = 2): string => Number.isFinite(value) ? value.toFixed(digits) : unavailable
const timestampValue = (value: string): string => {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? unavailable : date.toISOString()
}
const ageValue = (timestamp: string, reference: string): string => {
  const point = Date.parse(timestamp)
  const now = Date.parse(reference)
  if (!Number.isFinite(point) || !Number.isFinite(now)) return unavailable
  const seconds = Math.max(0, Math.round((now - point) / 1000))
  return seconds < 2 ? 'just now' : `${seconds}s old`
}

/**
 * Derive the complete safe operator detail view from the normalized position.
 * This intentionally has no geographic, network, radio, or personal fields;
 * those are not part of PositionEstimate and therefore cannot leak here.
 */
export function positionDetailFields(position: PositionEstimate, snapshotGeneratedAt: string, status?: string, zoneName?: string): PositionDetailField[] {
  return [
    { key: 'sessionId', label: 'Anonymous session ID', value: position.sessionId || unavailable },
    { key: 'positionId', label: 'Position update ID', value: position.positionId || unavailable },
    { key: 'status', label: 'Status', value: status ?? (position.isOutsideMap ? 'Outside map' : 'Active position') },
    { key: 'source', label: 'Position source', value: positionSourceLabel(position) },
    { key: 'mode', label: 'Mode', value: position.mode },
    { key: 'floorPosition', label: 'Live floor position (X, Y)', value: `${numberValue(position.xM)} m, ${numberValue(position.yM)} m` },
    { key: 'rawFloorPosition', label: 'Raw floor position (X, Y)', value: `${numberValue(position.rawXM)} m, ${numberValue(position.rawYM)} m` },
    { key: 'accuracy', label: 'Accuracy radius', value: `${numberValue(position.accuracyRadiusM)} m` },
    { key: 'confidence', label: 'Confidence', value: `${Math.round(position.confidence * 100)}%` },
    { key: 'zone', label: 'Zone / room', value: zoneName || position.zoneId || unavailable },
    { key: 'positionMethod', label: 'Position method', value: position.positionMethod || unavailable },
    { key: 'smoothingMethod', label: 'Smoothing method', value: position.smoothingMethod || unavailable },
    { key: 'anchors', label: 'Anchors used', value: position.anchorsUsed.length ? position.anchorsUsed.join(', ') : unavailable },
    { key: 'observationCount', label: 'Observation count', value: String(position.observationCount) },
    { key: 'sequenceNumber', label: 'Update sequence', value: String(position.sequenceNumber) },
    { key: 'calculatedAt', label: 'Calculated at', value: timestampValue(position.calculatedAt) },
    { key: 'window', label: 'Observation window', value: `${timestampValue(position.windowStart)} → ${timestampValue(position.windowEnd)}` },
    { key: 'age', label: 'Age at snapshot', value: ageValue(position.calculatedAt, snapshotGeneratedAt) },
    { key: 'runId', label: 'Run ID', value: position.runId || unavailable },
    { key: 'deploymentId', label: 'Deployment ID', value: position.deploymentId || unavailable },
    { key: 'buildingId', label: 'Building ID', value: position.buildingId || unavailable },
    { key: 'floorId', label: 'Floor ID', value: position.floorId || unavailable },
    { key: 'outsideMap', label: 'Outside map', value: position.isOutsideMap ? 'Yes' : 'No' },
    { key: 'schemaVersion', label: 'Schema version', value: position.schemaVersion || unavailable },
  ]
}
