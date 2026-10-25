import { createContext, useContext, useState } from 'react'
import type { ReactNode } from 'react'
import { mockMediaAssets } from '../data/mockMediaAssets'
import { demoSeed } from '../lib/demoMode'
import type { MediaAsset } from '../types/media'

interface MediaAssetStoreContextValue {
  mediaAssets: MediaAsset[]
  addMediaAsset: (asset: MediaAsset) => void
}

const MediaAssetStoreContext = createContext<MediaAssetStoreContextValue | undefined>(undefined)

/**
 * Single shared source of truth for MediaAsset records, mounted at the app
 * root. Detections reference a mediaAssetId to resolve their source label
 * and agency scope — if this lived as local state inside
 * CommandStaffDataProvider it would reset every time that provider
 * remounts (e.g. a Command Staff session round-tripping through a role
 * switch), silently orphaning any detection created since the last mount.
 */
export function MediaAssetStoreProvider({ children }: { children: ReactNode }) {
  const [mediaAssets, setMediaAssets] = useState<MediaAsset[]>(() => demoSeed(mockMediaAssets))

  function addMediaAsset(asset: MediaAsset) {
    setMediaAssets((prev) => [asset, ...prev])
  }

  return (
    <MediaAssetStoreContext.Provider value={{ mediaAssets, addMediaAsset }}>
      {children}
    </MediaAssetStoreContext.Provider>
  )
}

export function useMediaAssetStore() {
  const ctx = useContext(MediaAssetStoreContext)
  if (!ctx) {
    throw new Error('useMediaAssetStore must be used within a MediaAssetStoreProvider')
  }
  return ctx
}
