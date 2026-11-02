import type { Drone, DroneType, DroneOperationalStatus } from '../../../types/drone'

export interface DroneRegistrationData {
  name: string
  manufacturer: string
  model: string
  droneType: DroneType
  serialNumber: string
  registrationNumber?: string
  dateAcquired: string
  operationalStatus: DroneOperationalStatus
  assignedOperatorId?: string
  lastInspectionDate?: string
  notes?: string
}

/** A blank form, dated today in local time (toISOString would give the UTC date, a day off in UTC+8 mornings). */
export function emptyRegistrationData(): DroneRegistrationData {
  const today = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return {
    name: '',
    manufacturer: '',
    model: '',
    droneType: 'QUADCOPTER',
    serialNumber: '',
    dateAcquired: `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`,
    operationalStatus: 'ACTIVE',
  }
}

/** The form prefilled with an existing drone, for editing it. */
export function registrationDataFromDrone(drone: Drone): DroneRegistrationData {
  return {
    name: drone.name,
    manufacturer: drone.manufacturer,
    model: drone.model,
    droneType: drone.droneType,
    serialNumber: drone.serialNumber,
    registrationNumber: drone.registrationNumber,
    // The database returns a timestamp; the date input wants YYYY-MM-DD.
    dateAcquired: drone.dateAcquired.slice(0, 10),
    operationalStatus: drone.operationalStatus,
    assignedOperatorId: drone.assignedOperatorId,
    lastInspectionDate: drone.lastInspectionDate,
    notes: drone.notes,
  }
}
