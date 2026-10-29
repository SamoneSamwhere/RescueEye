import type { DroneRegistrationData } from './types'

export const SERIAL_MIN_LENGTH = 4
export const SERIAL_MAX_LENGTH = 32
export const NAME_MAX_LENGTH = 50

/** Serial numbers are stored trimmed and upper-case, so "drn-001" and "DRN-001" are the same drone. */
export function normalizeSerialNumber(serial: string): string {
  return serial.trim().toUpperCase()
}

/**
 * Why a serial number can't be used, or null if it can. `existing` holds the
 * agency's other serials (the drone being edited excluded); the comparison
 * ignores case, matching how serials are stored.
 */
export function serialNumberProblem(serial: string, existing: string[]): string | null {
  const value = normalizeSerialNumber(serial)
  if (!value) return 'Serial number is required.'
  if (/\s/.test(value)) return 'Serial number cannot contain spaces.'
  if (!/^[A-Z0-9-]+$/.test(value)) return 'Use only letters, numbers and hyphens.'
  if (value.startsWith('-') || value.endsWith('-')) return 'Serial number cannot start or end with a hyphen.'
  if (value.length < SERIAL_MIN_LENGTH) return `Serial number must be at least ${SERIAL_MIN_LENGTH} characters.`
  if (value.length > SERIAL_MAX_LENGTH) return `Serial number must be at most ${SERIAL_MAX_LENGTH} characters.`
  if (existing.some((s) => normalizeSerialNumber(s) === value)) return 'This serial number is already registered.'
  return null
}

/**
 * Only the name (the drone's callsign and stream path) and serial number are
 * needed; everything else is for the record. `inMore` says the problem is in
 * the collapsed "More details" fields, so the form can open them.
 */
export function validateDetails(
  data: DroneRegistrationData,
  existingSerials: string[],
  existingRegNums: string[],
): { message: string; inMore: boolean } | null {
  if (!data.name.trim()) return { message: 'Drone name is required.', inMore: false }
  const serialProblem = serialNumberProblem(data.serialNumber, existingSerials)
  if (serialProblem) return { message: serialProblem, inMore: false }
  if (data.registrationNumber && existingRegNums.includes(data.registrationNumber.trim())) {
    return { message: 'This registration number is already in use.', inMore: true }
  }
  if (!data.dateAcquired) return { message: 'Date acquired is required.', inMore: true }
  return null
}
