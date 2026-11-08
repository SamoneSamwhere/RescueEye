import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Loader2, UserPlus } from 'lucide-react'
import { Button, Modal } from '../ui'
import { PersonnelInfoStep, RoleStep, AccountDetailsStep, ROLE_OPTIONS } from './user-creation'
import type { PersonnelInfoValues, AccountValues } from './user-creation'
import { useAgencyAdminData } from '../../features/agency-admin'
import type { CreatableUserRole } from '../../features/agency-admin'
import { useToast } from '../../features/toast'
import { cn } from '../../lib/cn'
import { formatPhPhone, parsePhPhone } from '../../lib/phone'

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const EMPTY_PERSONNEL: PersonnelInfoValues = { firstName: '', lastName: '', email: '', phone: '' }
const EMPTY_ACCOUNT: AccountValues = { password: '', confirmPassword: '' }

function validate(personnel: PersonnelInfoValues, role: CreatableUserRole | null, account: AccountValues): string | null {
  if (!personnel.firstName.trim() || !personnel.lastName.trim() || !personnel.email.trim() || !personnel.phone.trim()) {
    return 'Please fill in all personnel fields.'
  }
  if (!EMAIL_PATTERN.test(personnel.email)) return 'Enter a valid email address.'
  const phone = parsePhPhone(personnel.phone, ['mobile'])
  if (!phone.ok) return phone.error
  if (!role) return 'Choose a role.'
  if (!account.password || !account.confirmPassword) return 'Please set and confirm a password.'
  if (account.password.length < 8) return 'Password must be at least 8 characters.'
  if (account.password !== account.confirmPassword) return 'Passwords do not match.'
  return null
}

interface AddStaffModalProps {
  open: boolean
  onClose: () => void
  /** Called with the new account's id once it exists, so the list can show it. */
  onCreated: (userId: string) => void
}

/**
 * Add Staff in one dialog: personnel details, role and password in a single
 * scrolling form. Creating the account closes it straight away - the new
 * person appears at the top of the personnel list, highlighted.
 */
export function AddStaffModal({ open, onClose, onCreated }: AddStaffModalProps) {
  const { createUser } = useAgencyAdminData()
  const toast = useToast()
  const [personnel, setPersonnel] = useState<PersonnelInfoValues>(EMPTY_PERSONNEL)
  const [role, setRole] = useState<CreatableUserRole | null>(null)
  const [account, setAccount] = useState<AccountValues>(EMPTY_ACCOUNT)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const errorRef = useRef<HTMLParagraphElement>(null)
  // The message sits under the last field; bring it into view in the scrolling form.
  useEffect(() => {
    if (error) errorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [error])

  function reset() {
    setPersonnel(EMPTY_PERSONNEL)
    setRole(null)
    setAccount(EMPTY_ACCOUNT)
    setError(null)
  }

  function handleClose() {
    if (submitting) return
    reset()
    onClose()
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const problem = validate(personnel, role, account)
    if (problem || !role) {
      setError(problem)
      return
    }
    setError(null)
    setSubmitting(true)
    let result: Awaited<ReturnType<typeof createUser>>
    try {
      result = await createUser({
        firstName: personnel.firstName,
        lastName: personnel.lastName,
        email: personnel.email,
        phone: formatPhPhone(personnel.phone, ['mobile']),
        password: account.password,
        role,
      })
    } catch (err) {
      console.error('Create user failed unexpectedly:', err)
      setError('The user could not be created. Please try again.')
      return
    } finally {
      setSubmitting(false)
    }
    if (!result.ok) {
      setError(result.error)
      return
    }
    const name = `${personnel.firstName} ${personnel.lastName}`.trim()
    const roleLabel = ROLE_OPTIONS.find((option) => option.role === role)?.title ?? role
    toast.success(`${name} was added as ${roleLabel}.`, 'Staff added')
    reset()
    onCreated(result.userId)
    onClose()
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Add Staff"
      className="max-w-2xl"
      footer={
        <>
          <Button variant="outline" onClick={handleClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" form="add-staff-form" disabled={submitting} className={cn(submitting && 'cursor-wait')}>
            {submitting ? (
              <>
                <Loader2 className="size-3.5 animate-spin" />
                Creating…
              </>
            ) : (
              <>
                <UserPlus className="size-3.5" />
                Create User
              </>
            )}
          </Button>
        </>
      }
    >
      <form
        id="add-staff-form"
        onSubmit={handleSubmit}
        className="-mx-4 -my-3 flex max-h-[65vh] flex-col gap-5 overflow-y-auto px-4 py-3"
      >
        <PersonnelInfoStep values={personnel} onChange={(patch) => setPersonnel((prev) => ({ ...prev, ...patch }))} />
        <RoleStep selectedRole={role} onSelect={setRole} />
        <AccountDetailsStep values={account} onChange={(patch) => setAccount((prev) => ({ ...prev, ...patch }))} />
        {error ? (
          <p
            ref={errorRef}
            role="alert"
            className="rounded-md border border-danger-border bg-danger-bg px-3 py-2 text-sm text-danger-fg motion-safe:animate-shake"
          >
            {error}
          </p>
        ) : null}
      </form>
    </Modal>
  )
}
