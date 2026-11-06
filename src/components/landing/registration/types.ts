export interface AgencyInfoValues {
  agencyName: string
  agencyType: string
  /** House/building no. and street. Optional: many barangays have no street address. */
  addressStreet: string
  /** PSGC codes are the source of truth for the address; the *Name fields are display copies kept in step with them by PhilippineAddressFields. */
  addressRegionCode: string
  addressRegionName: string
  addressProvinceCode: string
  addressProvince: string
  addressCityCode: string
  addressCity: string
  addressBarangayCode: string
  addressBarangay: string
  addressZip: string
  agencyPhone: string
  agencyEmail: string
  agencyWebsite: string
}

export interface AdminInfoValues {
  firstName: string
  middleName: string
  lastName: string
  /** One of SAR_POSITIONS, or OTHER_POSITION with the title in positionOther. */
  position: string
  positionOther: string
  email: string
  phone: string
  password: string
  confirmPassword: string
}

// ── Organization types ───────────────────────────────────────────────────────
// Only organizations whose purpose is search and rescue or disaster response,
// and of a kind that flies drones or responds from drone footage — RescueEye
// is a drone platform, so a type that would never use it does not belong here.
// (Humanitarian / Red Cross units were dropped on that basis.)
// Each entry names the rescue/response unit, not a whole institution with a
// wider mandate: "a PCG search and rescue unit" qualifies, "the Coast Guard"
// does not. "Law Enforcement" and a catch-all "Other" were dropped for the
// same reason — neither says the organization exists to respond to disasters.
//
// Each type maps to one of three categories, and the category — not the type —
// decides the documents (see DOCUMENT_CATALOGUE).

/**
 * - government: a public office. Not SEC-registered; its standing comes from an
 *   office order, appointment or ordinance.
 * - registered: an NGO, company or chartered body registered with SEC, CDA or DOLE.
 * - volunteer: a community or volunteer group, which may have no registration
 *   at all (NDRRMC MC No. 64 s. 2021 accredits these through the LDRRMO).
 */
export type OrganizationCategory = 'government' | 'registered' | 'volunteer'

export const ORGANIZATION_TYPES: Array<{ value: string; category: OrganizationCategory }> = [
  { value: 'Local DRRM Office (PDRRMO / CDRRMO / MDRRMO)', category: 'government' },
  { value: 'Barangay DRRM Committee / Emergency Response Team', category: 'government' },
  { value: 'BFP Special Rescue / Fire and Rescue Unit', category: 'government' },
  { value: 'Government search and rescue unit (e.g. PCG, AFP HADR)', category: 'government' },
  { value: 'Search and rescue / disaster response NGO', category: 'registered' },
  { value: 'Private emergency response / rescue team', category: 'registered' },
  { value: 'Volunteer rescue group / community emergency response team', category: 'volunteer' },
]

/** Kept for existing imports. */
export const AGENCY_TYPES = ORGANIZATION_TYPES.map((t) => t.value)

/**
 * Category for a stored type. Records created before these types existed
 * (e.g. "Search & Rescue (SAR)") fall back to "registered", which asks for
 * the certificate of registration the old form always required.
 */
export function categoryForType(type: string): OrganizationCategory {
  return ORGANIZATION_TYPES.find((t) => t.value === type)?.category ?? 'registered'
}

// ── Address ──────────────────────────────────────────────────────────────────
// Kept, because the reviewer needs it to verify the organization exists and
// where it operates: NDRRMC accreditation of volunteer organizations asks for
// proof of a physical office, and an organization's jurisdiction is set by the
// LGU it sits in. Region/Province/City/Barangay are picked from the official
// PSGC via cascading dropdowns (see PhilippineAddressFields) rather than
// typed, so every stored address resolves to a real, unambiguous place.

/** One line for the existing `address` column: "Street, Brgy. X, City, Province 6000". */
export function formatAddress(v: AgencyInfoValues): string {
  const barangay = /^(brgy\.?|barangay)\s/i.test(v.addressBarangay.trim())
    ? v.addressBarangay.trim()
    : `Brgy. ${v.addressBarangay.trim()}`
  return [v.addressStreet.trim(), barangay, v.addressCity.trim(), `${v.addressProvince} ${v.addressZip.trim()}`]
    .filter(Boolean)
    .join(', ')
}

// ── Positions ────────────────────────────────────────────────────────────────
// Titles a person registering a response organization in the Philippines
// actually holds. Sources: the Incident Command System positions adopted by
// NDRRMC Memorandum Circular No. 4 s. 2012, and the Local DRRM Office
// positions made mandatory by CSC-DBM-DILG-NDRRMC Joint Memorandum Circular
// No. 2014-1 (a DRRM Officer plus officers for administration and training,
// research and planning, and operations and warning).

export const OTHER_POSITION = 'Other (please specify)'

export const SAR_POSITIONS: Array<{ group: string; positions: string[] }> = [
  {
    group: 'Organization leadership',
    positions: [
      'Head of Office / Chief',
      'President / Chairperson',
      'Executive Director',
      'Team Commander',
      'Team Leader',
      'Deputy Team Leader',
    ],
  },
  {
    group: 'Local DRRM Office',
    positions: [
      'Local DRRM Officer (PDRRMO / CDRRMO / MDRRMO)',
      'Administration and Training Officer',
      'Research and Planning Officer',
      'Operations and Warning Officer',
    ],
  },
  {
    group: 'Incident Command System',
    positions: [
      'Incident Commander',
      'Deputy Incident Commander',
      'Operations Section Chief',
      'Planning Section Chief',
      'Logistics Section Chief',
      'Finance / Administration Section Chief',
      'Safety Officer',
      'Liaison Officer',
      'Public Information Officer',
    ],
  },
]

/** The title to store: the picked position, or the typed one for "Other". */
export function resolvedPosition(v: AdminInfoValues): string {
  return v.position === OTHER_POSITION ? v.positionOther.trim() : v.position
}

// ── Documents ────────────────────────────────────────────────────────────────
// Only what verifies two things is required: that the organization is real,
// and that the person registering may act for it. Everything else is optional.
//
// - Everyone: a valid government-issued ID for the person registering (the
//   individual requirement in NDRRMC's volunteer accreditation).
// - Government offices are not SEC-registered, so they prove standing with an
//   office order, appointment or designation instead.
// - Registered organizations submit their SEC, CDA or DOLE certificate — the
//   certification NDRRMC asks non-government organizations for.
// - Volunteer groups may have no registration at all. They submit at least one
//   supporting document of any kind they have on hand, so an unregistered
//   community rescue team is not locked out.

export type DocumentId =
  | 'adminId'
  | 'officeOrder'
  | 'registration'
  | 'lguEndorsement'
  | 'accreditation'
  | 'proofOfAddress'
  | 'otherSupporting'

export type DocumentFiles = Record<DocumentId, File | null>
export type DocumentErrors = Record<DocumentId, string | null>

export const DOCUMENT_IDS: DocumentId[] = [
  'adminId', 'officeOrder', 'registration', 'lguEndorsement', 'accreditation', 'proofOfAddress', 'otherSupporting',
]

/**
 * label/hint: the full wording, used by the System Admin review page and in
 * validation messages. shortLabel: the compact name shown on the registration
 * document cards, which fit in a small square (the full label and hint stay
 * available as the card's tooltip).
 */
export const DOCUMENT_CATALOGUE: Record<
  DocumentId,
  { label: string; hint: string; shortLabel: string }
> = {
  adminId: {
    label: 'Valid Government-Issued ID',
    hint: 'Of the person registering — e.g. PhilSys ID, driver’s license, passport, or UMID.',
    shortLabel: 'Government-issued ID',
  },
  officeOrder: {
    label: 'Office Order, Appointment, or Designation',
    hint: 'Shows you are authorized to register this office — e.g. an office order from the Mayor or head of agency.',
    shortLabel: 'Office order / appointment',
  },
  registration: {
    label: 'SEC, CDA, or DOLE Certificate of Registration',
    hint: 'Proves the organization is legally registered.',
    shortLabel: 'SEC / CDA / DOLE registration',
  },
  lguEndorsement: {
    label: 'Barangay Certification or LGU / DRRMO Endorsement',
    hint: 'A certification or endorsement from your barangay, LGU, or local DRRM office.',
    shortLabel: 'Barangay / LGU endorsement',
  },
  accreditation: {
    label: 'Accreditation Certificate',
    hint: 'e.g. NDRRMC Accredited Community Disaster Volunteers (ACDV) or USAR accreditation.',
    shortLabel: 'Accreditation certificate',
  },
  proofOfAddress: {
    label: 'Proof of Office Address',
    hint: "Mayor's or business permit, lease, or a utility bill for your office.",
    shortLabel: 'Proof of office address',
  },
  otherSupporting: {
    label: 'Other Supporting Document',
    hint: 'Anything else that shows your work — training certificates, list of members, or records of past operations.',
    shortLabel: 'Other supporting document',
  },
}

export type DocumentRequirement = 'required' | 'optional' | 'oneOf'

/**
 * Which documents a category sees and how each counts.
 * "oneOf": at least one of the oneOf documents must be uploaded.
 */
export function documentsFor(category: OrganizationCategory): Array<{ id: DocumentId; requirement: DocumentRequirement }> {
  switch (category) {
    case 'government':
      return [
        { id: 'adminId', requirement: 'required' },
        { id: 'officeOrder', requirement: 'required' },
        { id: 'proofOfAddress', requirement: 'optional' },
        { id: 'otherSupporting', requirement: 'optional' },
      ]
    case 'registered':
      return [
        { id: 'adminId', requirement: 'required' },
        { id: 'registration', requirement: 'required' },
        { id: 'accreditation', requirement: 'optional' },
        { id: 'proofOfAddress', requirement: 'optional' },
        { id: 'lguEndorsement', requirement: 'optional' },
        { id: 'otherSupporting', requirement: 'optional' },
      ]
    case 'volunteer':
      return [
        { id: 'adminId', requirement: 'required' },
        { id: 'lguEndorsement', requirement: 'oneOf' },
        { id: 'accreditation', requirement: 'oneOf' },
        { id: 'registration', requirement: 'oneOf' },
        { id: 'proofOfAddress', requirement: 'oneOf' },
        { id: 'otherSupporting', requirement: 'oneOf' },
      ]
  }
}

export function emptyDocumentRecord<T>(value: T): Record<DocumentId, T> {
  return Object.fromEntries(DOCUMENT_IDS.map((id) => [id, value])) as Record<DocumentId, T>
}

/**
 * The legacy fixed list, still read by the System Admin review page for
 * records that predate per-category documents.
 */
export const REQUIRED_DOCUMENTS: Array<{ id: DocumentId; label: string; hint: string; required: boolean }> =
  documentsFor('registered').map(({ id, requirement }) => ({
    id,
    ...DOCUMENT_CATALOGUE[id],
    required: requirement === 'required',
  }))
