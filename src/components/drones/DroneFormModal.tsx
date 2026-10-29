import { useState } from 'react'
import { CheckCircle2, Loader2 } from 'lucide-react'
import { Modal, Button } from '../ui'
import {
  DroneDetailsStep,
  emptyRegistrationData,
  normalizeSerialNumber,
  registrationDataFromDrone,
  validateDetails,
} from './registration'
import type { DroneRegistrationData } from './registration'
import type { Drone } from '../../types/drone'

export interface DroneFormModalProps {
  open: boolean
  onClose: () => void
  /** The drone being edited; omitted to register a new one. */
  drone?: Drone
  /** Serial and registration numbers already taken in the agency, the edited drone's own excluded. */
  existingSerialNumbers: string[]
  existingRegistrationNumbers: string[]
  onSubmit: (data: DroneRegistrationData) => Promise<{ ok: boolean; error?: string }>
  /** Called after an edit is saved (a registration shows its own success screen instead). */
  onSaved?: (name: string) => void
}

/**
 * Registers a drone, or edits one, in a window over the Drones page so the
 * operator never leaves the fleet list. Registering asks for a small
 * confirmation on top of the form; an edit saves straight away. Mounted only
 * while open (the parent renders it conditionally), so each opening starts
 * from a fresh form.
 */
export function DroneFormModal({
  open,
  onClose,
  drone,
  existingSerialNumbers,
  existingRegistrationNumbers,
  onSubmit,
  onSaved,
}: DroneFormModalProps) {
  const editing = !!drone
  const [data, setData] = useState<DroneRegistrationData>(() =>
    drone ? registrationDataFromDrone(drone) : emptyRegistrationData(),
  )
  const [error, setError] = useState<string | null>(null)
  const [showMore, setShowMore] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [registeredName, setRegisteredName] = useState<string | null>(null)

  const patch = (change: Partial<DroneRegistrationData>) => setData((prev) => ({ ...prev, ...change }))

  function handleClose() {
    // Closing mid-request would leave a save finishing behind a form that is gone.
    if (submitting) return
    // Escape reaches both dialogs; while confirming it should only dismiss the confirmation.
    if (confirming) {
      setConfirming(false)
      return
    }
    onClose()
  }

  function cancelConfirm() {
    if (!submitting) setConfirming(false)
  }

  function requestSubmit() {
    const problem = validateDetails(data, existingSerialNumbers, existingRegistrationNumbers)
    if (problem) {
      setError(problem.message)
      if (problem.inMore) setShowMore(true)
      return
    }
    setError(null)
    if (editing) void submit()
    else setConfirming(true)
  }

  async function submit() {
    setSubmitting(true)
    const result = await onSubmit({
      ...data,
      name: data.name.trim(),
      serialNumber: normalizeSerialNumber(data.serialNumber),
    })
    setSubmitting(false)
    setConfirming(false)
    if (!result.ok) {
      setError(result.error || (editing ? 'Failed to save changes. Please try again.' : 'Failed to register drone. Please try again.'))
      return
    }
    if (editing) {
      onSaved?.(data.name.trim())
      onClose()
    } else {
      setRegisteredName(data.name.trim())
    }
  }

  if (registeredName) {
    return (
      <Modal open={open} onClose={onClose} title="Drone Registered" footer={<Button onClick={onClose}>Done</Button>}>
        <div className="flex flex-col items-center gap-3 py-4 text-center">
          <span className="flex size-14 items-center justify-center rounded-full bg-success-bg text-success-fg">
            <CheckCircle2 className="size-8" />
          </span>
          <div>
            <p className="text-base font-semibold text-foreground">{registeredName}</p>
            <p className="mt-1 text-sm text-foreground-secondary">
              is registered. Connect it from the drone list to start a live feed.
            </p>
          </div>
        </div>
      </Modal>
    )
  }

  return (
    <>
      <Modal
        open={open}
        onClose={handleClose}
        title={editing ? `Edit ${drone.name}` : 'Register New Drone'}
        className="max-w-lg"
        footer={
          <>
            <Button variant="outline" onClick={handleClose} disabled={editing && submitting}>
              Cancel
            </Button>
            <Button onClick={requestSubmit} disabled={editing && submitting}>
              {editing && submitting ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  Saving…
                </>
              ) : editing ? (
                'Save Changes'
              ) : (
                'Register Drone'
              )}
            </Button>
          </>
        }
      >
        <div className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto py-1">
          <DroneDetailsStep
            data={data}
            onChange={patch}
            existingSerialNumbers={existingSerialNumbers}
            existingRegistrationNumbers={existingRegistrationNumbers}
            showMore={showMore}
            onShowMoreChange={setShowMore}
            intro={editing ? undefined : 'A name and serial number are all you need to register a drone.'}
          />

          {error ? (
            <div className="rounded-md bg-danger-subtle px-3 py-2 text-sm text-danger-fg" role="alert">
              {error}
            </div>
          ) : null}
        </div>
      </Modal>

      <Modal
        open={confirming}
        onClose={cancelConfirm}
        title="Confirm Registration"
        footer={
          <>
            <Button variant="outline" onClick={cancelConfirm} disabled={submitting}>
              Back
            </Button>
            <Button onClick={submit} disabled={submitting}>
              {submitting ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  Registering…
                </>
              ) : (
                'Confirm'
              )}
            </Button>
          </>
        }
      >
        <p>
          Register <strong>{data.name.trim()}</strong> (serial{' '}
          <span className="font-mono">{normalizeSerialNumber(data.serialNumber)}</span>) to your agency's fleet? You
          can connect it from the drone list afterwards.
        </p>
      </Modal>
    </>
  )
}
