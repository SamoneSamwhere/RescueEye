import { Field, Input } from '../../ui'
import type { DroneRegistrationData } from './types'

interface AssignmentStepProps {
  data: DroneRegistrationData
  onChange: (patch: Partial<DroneRegistrationData>) => void
}

const OPERATIONAL_STATUS_OPTIONS = [
  { value: 'ACTIVE', label: 'Active - Ready for operations' },
  { value: 'INACTIVE', label: 'Inactive - Not currently in service' },
  { value: 'MAINTENANCE', label: 'Under Maintenance - Scheduled service' },
] as const

export function AssignmentStep({ data, onChange }: AssignmentStepProps) {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h3 className="text-lg font-semibold text-foreground">Operations</h3>
        <p className="text-sm text-foreground-secondary">Operational status, inspection and notes</p>
      </div>

      <Field label="Operational Status" htmlFor="operational-status" hint="Current operational readiness">
        <select
          id="operational-status"
          value={data.operationalStatus}
          onChange={(e) => onChange({ operationalStatus: e.target.value as typeof data.operationalStatus })}
          className="h-9 w-full rounded-md border border-border-strong bg-surface-secondary px-2 text-sm text-foreground placeholder:text-foreground-muted transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-focus"
        >
          {OPERATIONAL_STATUS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </Field>

      <Field
        label="Last Inspection Date (Optional)"
        htmlFor="last-inspection"
        hint="Most recent maintenance or inspection date"
      >
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

      <Field label="Notes (Optional)" htmlFor="notes" hint="Any additional information about the drone">
        <textarea
          id="notes"
          value={data.notes || ''}
          onChange={(e) => onChange({ notes: e.target.value || undefined })}
          placeholder="e.g., Special capabilities, known issues, maintenance schedule..."
          className="h-24 w-full rounded-md border border-border-strong bg-surface-secondary px-2 py-1.5 text-sm text-foreground placeholder:text-foreground-muted transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-focus resize-none"
        />
      </Field>
    </div>
  )
}
