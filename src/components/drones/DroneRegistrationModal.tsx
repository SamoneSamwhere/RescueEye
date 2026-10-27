import { useState } from 'react'
import { CheckCircle2, Loader2 } from 'lucide-react'
import { Modal, Button } from '../ui'
import { RegistrationStepper } from '../landing/registration'
import {
  DroneInfoStep,
  RegistrationDetailsStep,
  AssignmentStep,
  ReviewStep,
  EMPTY_REGISTRATION_DATA,
} from './registration'
import type { DroneRegistrationData } from './registration'

const STEP_LABELS = ['Drone Info', 'Registration', 'Operations', 'Review']
const LAST_STEP = STEP_LABELS.length - 1

export interface DroneRegistrationModalProps {
  open: boolean
  onClose: () => void
  existingSerialNumbers: string[]
  existingRegistrationNumbers: string[]
  onRegister: (data: DroneRegistrationData) => Promise<{ ok: boolean; error?: string }>
}

function validateDroneInfo(data: DroneRegistrationData): string | null {
  if (!data.name.trim()) return 'Drone name is required.'
  if (!data.manufacturer.trim()) return 'Manufacturer is required.'
  if (!data.model.trim()) return 'Model is required.'
  if (!data.droneType) return 'Drone type is required.'
  return null
}

function validateRegistration(
  data: DroneRegistrationData,
  existingSerials: string[],
  existingRegNums: string[],
): string | null {
  if (!data.serialNumber.trim()) return 'Serial number is required.'
  if (existingSerials.includes(data.serialNumber.trim())) return 'This serial number is already registered.'
  if (data.registrationNumber && existingRegNums.includes(data.registrationNumber.trim())) {
    return 'This registration number is already in use.'
  }
  if (!data.dateAcquired) return 'Date acquired is required.'
  return null
}

/**
 * The four-step drone registration, in a window over the Drones page so
 * registering never takes the operator away from the fleet list. Mounted only
 * while open (the parent renders it conditionally), so each opening starts
 * from step one with an empty form.
 */
export function DroneRegistrationModal({
  open,
  onClose,
  existingSerialNumbers,
  existingRegistrationNumbers,
  onRegister,
}: DroneRegistrationModalProps) {
  const [step, setStep] = useState(0)
  const [data, setData] = useState<DroneRegistrationData>(EMPTY_REGISTRATION_DATA)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [registeredName, setRegisteredName] = useState<string | null>(null)

  const patch = (change: Partial<DroneRegistrationData>) => setData((prev) => ({ ...prev, ...change }))

  function handleClose() {
    // Closing mid-request would leave a registration finishing behind a form that is gone.
    if (submitting) return
    onClose()
  }

  function next() {
    const problem =
      step === 0
        ? validateDroneInfo(data)
        : step === 1
          ? validateRegistration(data, existingSerialNumbers, existingRegistrationNumbers)
          : null
    if (problem) {
      setError(problem)
      return
    }
    setError(null)
    setStep((s) => s + 1)
  }

  function back() {
    setError(null)
    setStep((s) => Math.max(0, s - 1))
  }

  async function submit() {
    setError(null)
    setSubmitting(true)
    const result = await onRegister(data)
    setSubmitting(false)
    if (!result.ok) {
      setError(result.error || 'Failed to register drone. Please try again.')
      return
    }
    setRegisteredName(data.name)
  }

  if (registeredName) {
    return (
      <Modal
        open={open}
        onClose={onClose}
        title="Drone Registered"
        footer={<Button onClick={onClose}>Done</Button>}
      >
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
    <Modal
      open={open}
      onClose={handleClose}
      title="Register New Drone"
      className="max-w-2xl"
      footer={
        <>
          {step > 0 ? (
            <Button variant="outline" onClick={back} disabled={submitting}>
              Previous
            </Button>
          ) : (
            <Button variant="outline" onClick={handleClose}>
              Cancel
            </Button>
          )}
          {step === LAST_STEP ? (
            <Button onClick={submit} disabled={submitting}>
              {submitting ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  Registering…
                </>
              ) : (
                'Register Drone'
              )}
            </Button>
          ) : (
            <Button onClick={next}>Next</Button>
          )}
        </>
      }
    >
      <div className="flex max-h-[75vh] flex-col gap-4 overflow-y-auto">
        <RegistrationStepper currentStep={step} steps={STEP_LABELS} />

        {step === 0 && <DroneInfoStep data={data} onChange={patch} />}
        {step === 1 && (
          <RegistrationDetailsStep
            data={data}
            onChange={patch}
            existingSerialNumbers={existingSerialNumbers}
            existingRegistrationNumbers={existingRegistrationNumbers}
          />
        )}
        {step === 2 && <AssignmentStep data={data} onChange={patch} />}
        {step === 3 && <ReviewStep data={data} />}

        {error ? (
          <div className="rounded-md bg-danger-subtle px-3 py-2 text-sm text-danger-fg" role="alert">
            {error}
          </div>
        ) : null}
      </div>
    </Modal>
  )
}
