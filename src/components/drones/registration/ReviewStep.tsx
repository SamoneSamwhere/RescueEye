import { Card } from '../../ui'
import type { DroneRegistrationData } from './types'

function formatDate(date: Date): string {
  const formatter = new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
  return formatter.format(date)
}

interface ReviewStepProps {
  data: DroneRegistrationData
}

export function ReviewStep({ data }: ReviewStepProps) {
  const DRONE_TYPE_MAP = {
    QUADCOPTER: 'Quadcopter',
    FIXED_WING: 'Fixed Wing',
    HYBRID: 'Hybrid',
    OTHER: 'Other',
  }
  const STATUS_MAP = {
    ACTIVE: 'Active',
    INACTIVE: 'Inactive',
    MAINTENANCE: 'Under Maintenance',
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h3 className="text-lg font-semibold text-foreground">Review Registration</h3>
        <p className="text-sm text-foreground-secondary">Confirm the drone information before registration</p>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <Card className="flex flex-col gap-2 px-4 py-3">
          <p className="text-xs font-medium uppercase tracking-wide text-foreground-muted">Drone Name</p>
          <p className="text-sm font-semibold text-foreground">{data.name}</p>
        </Card>

        <Card className="flex flex-col gap-2 px-4 py-3">
          <p className="text-xs font-medium uppercase tracking-wide text-foreground-muted">Manufacturer</p>
          <p className="text-sm font-semibold text-foreground">{data.manufacturer}</p>
        </Card>

        <Card className="flex flex-col gap-2 px-4 py-3">
          <p className="text-xs font-medium uppercase tracking-wide text-foreground-muted">Model</p>
          <p className="text-sm font-semibold text-foreground">{data.model}</p>
        </Card>

        <Card className="flex flex-col gap-2 px-4 py-3">
          <p className="text-xs font-medium uppercase tracking-wide text-foreground-muted">Drone Type</p>
          <p className="text-sm font-semibold text-foreground">{DRONE_TYPE_MAP[data.droneType]}</p>
        </Card>

        <Card className="flex flex-col gap-2 px-4 py-3">
          <p className="text-xs font-medium uppercase tracking-wide text-foreground-muted">Serial Number</p>
          <p className="text-sm font-monospace font-semibold text-foreground">{data.serialNumber}</p>
        </Card>

        <Card className="flex flex-col gap-2 px-4 py-3">
          <p className="text-xs font-medium uppercase tracking-wide text-foreground-muted">Registration Number</p>
          <p className="text-sm font-monospace font-semibold text-foreground">{data.registrationNumber || 'Not provided'}</p>
        </Card>

        <Card className="flex flex-col gap-2 px-4 py-3">
          <p className="text-xs font-medium uppercase tracking-wide text-foreground-muted">Date Acquired</p>
          <p className="text-sm font-semibold text-foreground">{formatDate(new Date(data.dateAcquired))}</p>
        </Card>

        <Card className="flex flex-col gap-2 px-4 py-3">
          <p className="text-xs font-medium uppercase tracking-wide text-foreground-muted">Operational Status</p>
          <p className="text-sm font-semibold text-foreground">{STATUS_MAP[data.operationalStatus]}</p>
        </Card>

        {data.lastInspectionDate && (
          <Card className="flex flex-col gap-2 px-4 py-3">
            <p className="text-xs font-medium uppercase tracking-wide text-foreground-muted">Last Inspection</p>
            <p className="text-sm font-semibold text-foreground">{formatDate(new Date(data.lastInspectionDate))}</p>
          </Card>
        )}

        {data.notes && (
          <Card className="flex flex-col gap-2 px-4 py-3 md:col-span-2">
            <p className="text-xs font-medium uppercase tracking-wide text-foreground-muted">Notes</p>
            <p className="text-sm text-foreground">{data.notes}</p>
          </Card>
        )}
      </div>

      <div className="rounded-md bg-accent-subtle px-3 py-2 text-sm text-accent-fg">
        <p className="font-medium">Ready to register</p>
        <p className="text-xs opacity-90 mt-1">Click "Register Drone" to complete the registration process</p>
      </div>
    </div>
  )
}
