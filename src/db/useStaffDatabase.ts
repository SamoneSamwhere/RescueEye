import { useState } from 'react'
import { supabase } from '../lib/supabase'
import { api, ApiError, apiErrorText } from '../lib/apiClient'

export type StaffRole = 'COMMAND_STAFF' | 'FIELD_RESPONDER'

export interface DbStaffUser {
  id: number
  email: string
  firstName: string | null
  lastName: string | null
  phone: string | null
  role: StaffRole
  agencyId: number
  active: boolean
  createdAt: string
}

export interface CreateStaffInput {
  agencyId: number
  firstName: string
  lastName: string
  email: string
  phone?: string
  password: string
  role: StaffRole
}

export type CreateStaffResult =
  | { ok: true; userId: number }
  | { ok: false; error: string; field?: 'email' }

export function useStaffDatabase() {
  const [isLoading, setIsLoading] = useState(false)

  const getAgencyStaff = async (agencyId: number): Promise<DbStaffUser[]> => {
    setIsLoading(true)
    try {
      const { data, error: dbError } = await supabase
        .from('user')
        .select('id, email, firstName, lastName, phone, role, agencyId, active, createdAt')
        .eq('agencyId', agencyId)
        .in('role', ['COMMAND_STAFF', 'FIELD_RESPONDER'])
        .order('createdAt', { ascending: false })

      if (dbError) throw dbError
      return (data as DbStaffUser[]) || []
    } catch (err) {
      console.error('Get agency staff error:', err)
      return []
    } finally {
      setIsLoading(false)
    }
  }

  const createStaffUser = async (input: CreateStaffInput): Promise<CreateStaffResult> => {
    setIsLoading(true)
    try {
      // The API hashes the password and always uses the admin's own agency
      // (api/routers/auth.py, POST /auth/users); input.agencyId is not sent.
      const res = await api.post<{ userId: number }>('/auth/users', {
        firstName: input.firstName.trim(),
        lastName: input.lastName.trim(),
        email: input.email.trim(),
        phone: input.phone?.trim() || null,
        password: input.password,
        role: input.role,
      })
      return { ok: true, userId: res.userId }
    } catch (err) {
      console.error('Create staff user error:', err)
      return {
        ok: false,
        error: apiErrorText(err),
        field: err instanceof ApiError && err.status === 409 ? 'email' : undefined,
      }
    } finally {
      setIsLoading(false)
    }
  }

  const setStaffActive = async (userId: number, active: boolean) => {
    const { error: dbError } = await supabase.from('user').update({ active }).eq('id', userId)
    if (dbError) console.error('Set staff active error:', dbError)
    return !dbError
  }

  return { getAgencyStaff, createStaffUser, setStaffActive, isLoading }
}
