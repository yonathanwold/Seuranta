import { create } from 'zustand'
import type { NormalizedMode, NormalizedState, PositionProvider, ProviderSnapshot, ProviderStatus } from './types'

interface AtlasStore {
  mode: NormalizedMode
  snapshot: NormalizedState
  providerStatus: ProviderStatus
  selectedId: string | null
  search: string
  showEntities: boolean
  showAnchors: boolean
  showLabels: boolean
  showConfidence: boolean
  showZones: boolean
  setMode: (mode: NormalizedMode) => void
  applySnapshot: (snapshot: ProviderSnapshot) => void
  setSelectedId: (id: string | null) => void
  setSearch: (search: string) => void
  toggleLayer: (key: 'showEntities' | 'showAnchors' | 'showLabels' | 'showConfidence' | 'showZones') => void
}

const emptyState: NormalizedState = { stateRevision: 0, generatedAt: new Date().toISOString(), deploymentId: '', buildingId: 'vt-academic-classroom-building', floorId: 'floor-1', runId: '', mode: 'SIMULATION', counts: { activeSessions: 0, anchorsOnline: 0, anchorsDegraded: 0, eventsLastHour: 0 }, sessions: [], positions: [], nodes: [], zones: [], recentEvents: [], isPartial: true }

export const useAtlasStore = create<AtlasStore>((set) => ({
  mode: 'SIMULATION', snapshot: emptyState, providerStatus: 'connecting', selectedId: 'session-a7f3', search: '', showEntities: true, showAnchors: true, showLabels: true, showConfidence: true, showZones: true,
  setMode: (mode) => set({ mode }), applySnapshot: (payload) => set({ snapshot: payload.state, providerStatus: payload.providerStatus }), setSelectedId: (selectedId) => set({ selectedId }), setSearch: (search) => set({ search }), toggleLayer: (key) => set((state) => ({ [key]: !state[key] })),
}))

export const startProvider = (provider: PositionProvider, applySnapshot: (snapshot: ProviderSnapshot) => void): (() => void) => { provider.start(applySnapshot); return () => provider.stop() }
