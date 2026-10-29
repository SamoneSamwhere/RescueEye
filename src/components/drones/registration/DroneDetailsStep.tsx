import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { Field, Input } from '../../ui'
import type { DroneRegistrationData } from './types'
import { NAME_MAX_LENGTH, SERIAL_MAX_LENGTH, SERIAL_MIN_LENGTH, serialNumberProblem } from './validation'

interface DroneDetailsStepProps {
  data: DroneRegistrationData
  onChange: (patch: Partial<DroneRegistrationData>) => void
  existingSerialNumbers: string[]
  existingRegistrationNumbers: string[]
  /** Whether the optional fields are shown; the modal opens them when one of them has a problem. */
  showMore: boolean
  onShowMoreChange: (open: boolean) => void
  /** A line above the fields; omitted when editing. */
  intro?: string
}

const DRONE_TYPE_OPTIONS = [
  { value: 'QUADCOPTER', label: 'Quadcopter' },
  { value: 'FIXED_WING', label: 'Fixed Wing' },
  { value: 'HYBRID', label: 'Hybrid' },
  { value: 'OTHER', label: 'Other' },
] as const

const OPERATIONAL_STATUS_OPTIONS = [
  { value: 'ACTIVE', label: 'Active - Ready for operations' },
  { value: 'INACTIVE', label: 'Inactive - Not currently in service' },
  { value: 'MAINTENANCE', label: 'Under Maintenance - Scheduled service' },
] as const

const SELECT_CLASS =
  'h-9 w-full rounded-md border border-border-strong bg-surface-secondary px-2 text-sm text-foreground placeholder:text-foreground-muted transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-focus'

/**
 * Everything the registration (or an edit) asks for, on one screen. Only the name and the
 * serial number are needed up front; the rest is for the record, prefilled
 * where it can be, and tucked behind "More details" so the form stays short.
 */
export function DroneDetailsStep({
  data,
  onChange,
  existingSerialNumbers,
  existingRegistrationNumbers,
  showMore,
  onShowMoreChange,
  intro,
}: DroneDetailsStepProps) {
  // Format problems ("too short") would nag mid-typing, so they wait until the
  // field is left; a duplicate is worth knowing about at once.
  const [serialTouched, setSerialTouched] = useState(false)
  const serialProblem = data.serialNumber ? serialNumberProblem(data.serialNumber, existingSerialNumbers) : null
  const serialError =
    serialProblem && (serialTouched || serialProblem.includes('already registered')) ? serialProblem : undefined
  const regNumberError =
    data.registrationNumber && existingRegistrationNumbers.includes(data.registrationNumber.trim())
      ? 'This registration number is already in use'
      : undefined

  return (
    <div className="flex flex-col gap-5">
      {intro ? <p className="text-sm text-foreground-secondary">{intro}</p> : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Drone Name" htmlFor="drone-name" hint="Shown on the drone list and live feed">
          <Input
            id="drone-name"
            value={data.name}
            onChange={(e) => onChange({ name: e.target.value })}
            placeholder="e.g., Sentinel-1"
            maxLength={NAME_MAX_LENGTH}
          />
        </Field>

        <Field
          label="Serial Number"
          htmlFor="serial-number"
          error={serialError}
          hint={`${SERIAL_MIN_LENGTH}–${SERIAL_MAX_LENGTH} letters, numbers or hyphens; must be unique`}
        >
          <Input
            id="serial-number"
            value={data.serialNumber}
            onChange={(e) => onChange({ serialNumber: e.target.value.toUpperCase() })}
            onBlur={() => setSerialTouched(true)}
            placeholder="e.g., DRN-001"
            maxLength={SERIAL_MAX_LENGTH}
            autoComplete="off"
            spellCheck={false}
            className="font-mono"
            invalid={!!serialError}
          />
        </Field>
      </div>

      <details
        open={showMore}
        onToggle={(e) => onShowMoreChange(e.currentTarget.open)}
        className="group rounded-lg border border-border bg-surface-secondary/40"
      >
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-lg px-4 py-3 transition-colors hover:bg-surface-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus [&::-webkit-details-marker]:hidden">
          <span className="flex flex-col">
            <span className="text-sm font-medium text-foreground">More details</span>
            <span className="text-xs text-foreground-muted">Optional: manufacturer, model, type, status, dates, notes</span>
          </span>
          <ChevronDown className="size-4 shrink-0 text-foreground-muted transition-transform group-open:rotate-180" />
        </summary>

        <div className="grid gap-4 border-t border-border px-4 py-4 sm:grid-cols-2">
          <Field label="Manufacturer" htmlFor="manufacturer" hint="e.g., DJI, Freefly, Parrot">
            <Input
              id="manufacturer"
              value={data.manufacturer}
              onChange={(e) => onChange({ manufacturer: e.target.value })}
              placeholder="Enter manufacturer name"
            />
          </Field>

          <Field label="Model" htmlFor="model" hint="e.g., Matrice 350 RTK">
            <Input
              id="model"
              value={data.model}
              onChange={(e) => onChange({ model: e.target.value })}
              placeholder="Enter drone model"
            />
          </Field>

          <Field label="Drone Type" htmlFor="drone-type">
            <select
              id="drone-type"
              value={data.droneType}
              onChange={(e) => onChange({ droneType: e.target.value as typeof data.droneType })}
              className={SELECT_CLASS}
            >
              {DRONE_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Operational Status" htmlFor="operational-status">
            <select
              id="operational-status"
              value={data.operationalStatus}
              onChange={(e) => onChange({ operationalStatus: e.target.value as typeof data.operationalStatus })}
              className={SELECT_CLASS}
            >
              {OPERATIONAL_STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </Field>

          <Field
            label="Registration / License Number"
            htmlFor="registration-number"
            error={regNumberError}
            hint="Government or agency registration, if any"
          >
            <Input
              id="registration-number"
              value={data.registrationNumber || ''}
              onChange={(e) => onChange({ registrationNumber: e.target.value || undefined })}
              placeholder="e.g., REG-2025-0001"
              invalid={!!regNumberError}
            />
          </Field>

          <Field label="Date Acquired" htmlFor="date-acquired" hint="Defaults to today">
            <Input
              id="date-acquired"
              type="date"
              value={data.dateAcquired}
              onChange={(e) => onChange({ dateAcquired: e.target.value })}
            />
          </Field>

          <Field label="Last Inspection Date" htmlFor="last-inspection">
            <Input
              id="last-inspection"
              type="date"
              value={data.lastInspectionDate ? data.lastInspectionDate.split('T')[0] : ''}
              onChange={(e) => {
                const dateStr = e.target.value
                onChange({ lastInspectionDate: dateStr ? new Date(dateStr).toISOString() : undefined })
              }}
            />
          </Field>

          <div className="sm:col-span-2">
            <Field label="Notes" htmlFor="notes">
              <textarea
                id="notes"
                value={data.notes || ''}
                onChange={(e) => onChange({ notes: e.target.value || undefined })}
                placeholder="e.g., Special capabilities, known issues, maintenance schedule..."
                className="h-20 w-full resize-none rounded-md border border-border-strong bg-surface-secondary px-2 py-1.5 text-sm text-foreground placeholder:text-foreground-muted transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-focus"
              />
            </Field>
          </div>
        </div>
      </details>
    </div>
  )
}
