import { useState } from 'react'
import { supabase, handleDatabaseError } from '../lib/supabase'

export interface DroneRecord {
  id: number
  callsign: string
  manufacturer: string
  model: string
  droneType: 'QUADCOPTER' | 'FIXED_WING' | 'HYBRID' | 'OTHER'
  serialNumber: string
  registrationNumber: string | null
  operationalStatus: 'ACTIVE' | 'INACTIVE' | 'MAINTENANCE'
  dateAcquired: string
  lastInspectionDate: string | null
  notes: string | null
  assignedOperatorId: number | null
  status: 'ACTIVE' | 'IDLE' | 'OFFLINE'
  agencyId: number
  addedBy: number
  lastLat: number | null
  lastLng: number | null
  lastFeedAt: string | null
  createdAt: string
  updatedAt: string
}

/** A write that failed carries its reason as a sentence the form can show (see handleDatabaseError). */
export type DbResult<T> = { data: T; error: null } | { data: null; error: string }

export function useDroneDatabase() {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  /**
   * Get all drones for an agency
   */
  const getDronesByAgency = async (agencyId: number): Promise<DroneRecord[]> => {
    setIsLoading(true)
    setError(null)
    try {
      const { data, error: dbError } = await supabase
        .from('drone')
        .select('*')
        .eq('agencyId', agencyId)
        .order('createdAt', { ascending: false })

      if (dbError) {
        throw dbError
      }

      return data || []
    } catch (err) {
      const errorMsg = handleDatabaseError(err)
      setError(errorMsg)
      return []
    } finally {
      setIsLoading(false)
    }
  }

  /**
   * Get a single drone by ID
   */
  const getDroneById = async (droneId: number): Promise<DroneRecord | null> => {
    setIsLoading(true)
    setError(null)
    try {
      const { data, error: dbError } = await supabase
        .from('drone')
        .select('*')
        .eq('id', droneId)
        .single()

      if (dbError) {
        if (dbError.code === 'PGRST116') {
          return null // Not found
        }
        throw dbError
      }

      return data
    } catch (err) {
      const errorMsg = handleDatabaseError(err)
      setError(errorMsg)
      return null
    } finally {
      setIsLoading(false)
    }
  }

  /**
   * Check if serial number already exists
   */
  const checkSerialNumberExists = async (serialNumber: string): Promise<boolean> => {
    try {
      const { data, error: dbError } = await supabase
        .from('drone')
        .select('id')
        .eq('serialNumber', serialNumber.trim())
        .single()

      if (dbError && dbError.code !== 'PGRST116') {
        throw dbError
      }

      return !!data
    } catch (err) {
      console.error('Error checking serial number:', err)
      return false
    }
  }

  /**
   * Check if registration number already exists
   */
  const checkRegistrationNumberExists = async (registrationNumber: string): Promise<boolean> => {
    if (!registrationNumber) return false

    try {
      const { data, error: dbError } = await supabase
        .from('drone')
        .select('id')
        .eq('registrationNumber', registrationNumber.trim())
        .single()

      if (dbError && dbError.code !== 'PGRST116') {
        throw dbError
      }

      return !!data
    } catch (err) {
      console.error('Error checking registration number:', err)
      return false
    }
  }

  /**
   * Create a new drone
   */
  const createDrone = async (droneData: {
    callsign: string
    manufacturer: string
    model: string
    droneType: 'QUADCOPTER' | 'FIXED_WING' | 'HYBRID' | 'OTHER'
    serialNumber: string
    registrationNumber?: string
    operationalStatus?: 'ACTIVE' | 'INACTIVE' | 'MAINTENANCE'
    dateAcquired: string
    lastInspectionDate?: string
    notes?: string
    assignedOperatorId?: number
    agencyId: number
    addedBy: number
  }): Promise<DbResult<DroneRecord>> => {
    setIsLoading(true)
    setError(null)

    try {
      // Validate uniqueness
      const serialExists = await checkSerialNumberExists(droneData.serialNumber)
      if (serialExists) {
        throw new Error('This serial number is already registered.')
      }

      if (droneData.registrationNumber) {
        const regExists = await checkRegistrationNumberExists(droneData.registrationNumber)
        if (regExists) {
          throw new Error('This registration number is already in use.')
        }
      }

      const { data, error: dbError } = await supabase
        .from('drone')
        .insert([
          {
            callsign: droneData.callsign,
            manufacturer: droneData.manufacturer,
            model: droneData.model,
            droneType: droneData.droneType,
            serialNumber: droneData.serialNumber.trim(),
            registrationNumber: droneData.registrationNumber?.trim() || null,
            operationalStatus: droneData.operationalStatus || 'ACTIVE',
            dateAcquired: droneData.dateAcquired,
            lastInspectionDate: droneData.lastInspectionDate || null,
            notes: droneData.notes || null,
            assignedOperatorId: droneData.assignedOperatorId || null,
            status: 'IDLE',
            agencyId: droneData.agencyId,
            addedBy: droneData.addedBy,
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
          },
        ])
        .select()
        .single()

      if (dbError) {
        throw dbError
      }

      return { data, error: null }
    } catch (err) {
      const errorMsg = handleDatabaseError(err)
      setError(errorMsg)
      return { data: null, error: errorMsg }
    } finally {
      setIsLoading(false)
    }
  }

  /**
   * Update a drone
   */
  const updateDrone = async (
    droneId: number,
    updates: Partial<DroneRecord>,
  ): Promise<DbResult<DroneRecord>> => {
    setIsLoading(true)
    setError(null)

    try {
      const { data, error: dbError } = await supabase
        .from('drone')
        .update({ ...updates, updatedAt: new Date().toISOString() })
        .eq('id', droneId)
        .select()
        .single()

      if (dbError) {
        throw dbError
      }

      return { data, error: null }
    } catch (err) {
      const errorMsg = handleDatabaseError(err)
      setError(errorMsg)
      return { data: null, error: errorMsg }
    } finally {
      setIsLoading(false)
    }
  }

  /**
   * Delete a drone. Its detections stay, unlinked (detection.droneId is set to NULL, see migration 09).
   */
  const deleteDrone = async (droneId: number): Promise<DbResult<true>> => {
    setIsLoading(true)
    setError(null)

    try {
      const { data, error: dbError } = await supabase.from('drone').delete().eq('id', droneId).select('id')

      if (dbError) {
        throw dbError
      }
      // Row-level security hides rows rather than refusing, so a blocked delete "succeeds" on nothing.
      if (!data || data.length === 0) {
        throw new Error("This drone couldn't be removed. It may already be gone, or you may not have permission.")
      }

      return { data: true, error: null }
    } catch (err) {
      const errorMsg = handleDatabaseError(err)
      setError(errorMsg)
      return { data: null, error: errorMsg }
    } finally {
      setIsLoading(false)
    }
  }

  return {
    isLoading,
    error,
    getDronesByAgency,
    getDroneById,
    checkSerialNumberExists,
    checkRegistrationNumberExists,
    createDrone,
    updateDrone,
    deleteDrone,
  }
}
