import { useState } from 'react'
import { supabase } from '../lib/supabase'
import { api, apiErrorText } from '../lib/apiClient'

export interface DbProfileUser {
  id: number
  email: string
  firstName: string | null
  lastName: string | null
  phone: string | null
  role: 'AGENCY_ADMIN' | 'COMMAND_STAFF' | 'FIELD_RESPONDER'
  agencyId: number | null
  active: boolean
  createdAt: string
}

export type ChangePasswordResult = { ok: true } | { ok: false; error: string }

/** Real-account counterpart to the mock UserStore, for any logged-in Agency Admin / Command Staff / Field Responder. */
export function useProfileDatabase() {
  const [isLoading, setIsLoading] = useState(false)

  const getUserById = async (userId: number): Promise<DbProfileUser | null> => {
    const { data, error } = await supabase
      .from('user')
      .select('id, email, firstName, lastName, phone, role, agencyId, active, createdAt')
      .eq('id', userId)
      .single()
    if (error || !data) return null
    return data
  }

  const updateProfile = async (
    userId: number,
    patch: { firstName: string; lastName: string; email: string; phone?: string },
  ): Promise<boolean> => {
    setIsLoading(true)
    const { error } = await supabase
      .from('user')
      .update({
        firstName: patch.firstName,
        lastName: patch.lastName,
        email: patch.email,
        phone: patch.phone || null,
      })
      .eq('id', userId)
    setIsLoading(false)
    return !error
  }

  const changePassword = async (
    _userId: number,
    currentPassword: string,
    newPassword: string,
  ): Promise<ChangePasswordResult> => {
    setIsLoading(true)
    try {
      // The signed-in user is taken from the session token, not the id passed in.
      await api.post('/auth/password', { currentPassword, newPassword })
      return { ok: true }
    } catch (err) {
      return { ok: false, error: apiErrorText(err) }
    } finally {
      setIsLoading(false)
    }
  }

  return { getUserById, updateProfile, changePassword, isLoading }
}
