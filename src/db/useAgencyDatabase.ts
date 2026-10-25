import { useState } from 'react'
import { supabase } from '../lib/supabase'
import { api, ApiError, apiErrorText } from '../lib/apiClient'

interface CreateAgencyInput {
  agencyName: string
  agencyType: string
  agencyAddress: string
  /** PSGC codes for the office address — see supabase/migrations/04_address_psgc_codes.sql. */
  agencyAddressRegionCode?: string
  agencyAddressProvinceCode?: string
  agencyAddressCityCode?: string
  agencyAddressBarangayCode?: string
  agencyPhone: string
  agencyEmail: string
  agencyWebsite?: string
  adminFirstName: string
  adminMiddleName: string
  adminLastName: string
  adminPosition: string
  adminEmail: string
  adminPhone: string
  adminPassword: string
}

export interface DbAgency {
  id: number
  name: string
  agencyType: string | null
  address: string | null
  addressRegionCode?: string | null
  addressProvinceCode?: string | null
  addressCityCode?: string | null
  addressBarangayCode?: string | null
  website: string | null
  contactEmail: string | null
  contactPhone: string | null
  registrationStatus: 'PENDING' | 'APPROVED' | 'REJECTED'
  accountStatus: 'ACTIVE' | 'INACTIVE' | null
  subscriptionStatus: 'ACTIVE' | 'EXPIRED' | 'SUSPENDED'
  createdBy: number
  createdAt: string
  validatedBy: number | null
  validatedAt: string | null
  reviewNotes: string | null
}

export function useAgencyDatabase() {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const createAgency = async (
    input: CreateAgencyInput,
  ): Promise<
    | { success: true; agencyId: number; userId: number }
    | { success: false; error: string; field?: 'adminEmail' }
  > => {
    setIsLoading(true)
    setError(null)

    // The API creates the inactive Agency Admin and the pending agency together,
    // hashing the password server side (api/routers/auth.py, POST /auth/register).
    try {
      const res = await api.post<{ agencyId: number; userId: number }>('/auth/register', input)
      return { agencyId: res.agencyId, userId: res.userId, success: true }
    } catch (err) {
      console.error('Agency creation error:', err)
      const errorMessage = apiErrorText(err)
      setError(errorMessage)
      return {
        success: false,
        error: errorMessage,
        field: err instanceof ApiError && err.status === 409 ? 'adminEmail' : undefined,
      }
    } finally {
      setIsLoading(false)
    }
  }

  const getAgencies = async (): Promise<DbAgency[]> => {
    setIsLoading(true)
    setError(null)
    try {
      const { data, error: dbError } = await supabase
        .from('agency')
        .select('*')
        .order('createdAt', { ascending: false })

      if (dbError) throw dbError
      return data || []
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load agencies'
      setError(errorMessage)
      console.error('Get agencies error:', err)
      return []
    } finally {
      setIsLoading(false)
    }
  }

  /** Looks up who created an agency, so approve/reject can also flip that admin's active flag. */
  const getAgencyCreator = async (agencyId: number): Promise<number | null> => {
    const { data, error: dbError } = await supabase.from('agency').select('createdBy').eq('id', agencyId).single()
    if (dbError || !data) return null
    return data.createdBy
  }

  const approveAgency = async (agencyId: number, reviewedByUserId: number | null) => {
    const { error: dbError } = await supabase
      .from('agency')
      .update({
        registrationStatus: 'APPROVED',
        accountStatus: 'ACTIVE',
        validatedBy: reviewedByUserId,
        validatedAt: new Date().toISOString(),
        reviewNotes: null,
      })
      .eq('id', agencyId)

    if (dbError) {
      console.error('Approve agency error:', dbError)
      return false
    }

    const creatorId = await getAgencyCreator(agencyId)
    if (creatorId) {
      const { error: userError } = await supabase.from('user').update({ active: true }).eq('id', creatorId)
      if (userError) console.error('Activate agency admin error:', userError)
    }

    return true
  }

  const rejectAgency = async (agencyId: number, reviewedByUserId: number | null, reason: string) => {
    const { error: dbError } = await supabase
      .from('agency')
      .update({
        registrationStatus: 'REJECTED',
        accountStatus: 'INACTIVE',
        validatedBy: reviewedByUserId,
        validatedAt: new Date().toISOString(),
        reviewNotes: reason,
      })
      .eq('id', agencyId)

    if (dbError) {
      console.error('Reject agency error:', dbError)
      return false
    }

    const creatorId = await getAgencyCreator(agencyId)
    if (creatorId) {
      const { error: userError } = await supabase.from('user').update({ active: false }).eq('id', creatorId)
      if (userError) console.error('Deactivate agency admin error:', userError)
    }

    return true
  }

  const requestResubmission = async (agencyId: number, reviewedByUserId: number | null, notes: string) => {
    const { error: dbError } = await supabase
      .from('agency')
      .update({
        registrationStatus: 'PENDING',
        accountStatus: 'INACTIVE',
        validatedBy: reviewedByUserId,
        validatedAt: new Date().toISOString(),
        reviewNotes: notes,
      })
      .eq('id', agencyId)

    if (dbError) console.error('Request resubmission error:', dbError)
    return !dbError
  }

  const resubmitAgency = async (agencyId: number) => {
    const { error: dbError } = await supabase
      .from('agency')
      .update({
        registrationStatus: 'PENDING',
        validatedBy: null,
        validatedAt: null,
        reviewNotes: null,
      })
      .eq('id', agencyId)

    if (dbError) console.error('Resubmit agency error:', dbError)
    return !dbError
  }

  const setAgencyAccountStatus = async (agencyId: number, status: 'ACTIVE' | 'INACTIVE') => {
    const { error: dbError } = await supabase.from('agency').update({ accountStatus: status }).eq('id', agencyId)

    if (dbError) console.error('Set agency account status error:', dbError)
    return !dbError
  }

  return {
    createAgency,
    getAgencies,
    approveAgency,
    rejectAgency,
    requestResubmission,
    resubmitAgency,
    setAgencyAccountStatus,
    isLoading,
    error,
  }
}
