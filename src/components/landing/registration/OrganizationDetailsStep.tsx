import { Building2, Globe, Mail, Phone } from 'lucide-react'
import { Field } from '../../ui'
import { formatPhPhone } from '../../../lib/phone'
import { cn } from '../../../lib/cn'
import { IconInput } from './IconInput'
import { ORGANIZATION_TYPES } from './types'
import type { AgencyInfoValues } from './types'

const selectClasses =
  'h-9 w-full rounded-md border border-border-strong bg-surface px-2 text-sm text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus'

interface OrganizationDetailsStepProps {
  values: AgencyInfoValues
  onChange: (patch: Partial<AgencyInfoValues>) => void
}

/**
 * Step 1 — who the organization is and how to reach it. Address lives on its
 * own step (see AddressStep) so this one doesn't overwhelm the small card
 * with ten fields at once.
 */
export function OrganizationDetailsStep({ values, onChange }: OrganizationDetailsStepProps) {
  return (
    <div className="grid grid-cols-1 gap-x-3 gap-y-5 @sm:grid-cols-2">
      <Field label="Organization Name" htmlFor="agency-name">
        <IconInput
          id="agency-name"
          icon={Building2}
          value={values.agencyName}
          onChange={(event) => onChange({ agencyName: event.target.value })}
          placeholder="Cebu City Rescue Volunteers"
          required
        />
      </Field>

      <Field label="Organization Type" htmlFor="agency-type">
        <select
          id="agency-type"
          value={values.agencyType}
          onChange={(event) => onChange({ agencyType: event.target.value })}
          className={cn(selectClasses, 'truncate')}
          title={values.agencyType || undefined}
        >
          <option value="" disabled>
            Select a type
          </option>
          {ORGANIZATION_TYPES.map((type) => (
            <option key={type.value} value={type.value}>
              {type.value}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Contact Number" htmlFor="agency-phone" hint="PH mobile or landline.">
        <IconInput
          id="agency-phone"
          icon={Phone}
          type="tel"
          value={values.agencyPhone}
          onChange={(event) => onChange({ agencyPhone: event.target.value })}
          onBlur={() => onChange({ agencyPhone: formatPhPhone(values.agencyPhone) })}
          placeholder="0917 123 4567"
          required
        />
      </Field>

      <Field label="Official Email" htmlFor="agency-email">
        <IconInput
          id="agency-email"
          icon={Mail}
          type="email"
          value={values.agencyEmail}
          onChange={(event) => onChange({ agencyEmail: event.target.value })}
          placeholder="ops@yourorganization.org"
          required
        />
      </Field>

      <Field label="Website (optional)" htmlFor="agency-website">
        <IconInput
          id="agency-website"
          icon={Globe}
          type="url"
          value={values.agencyWebsite}
          onChange={(event) => onChange({ agencyWebsite: event.target.value })}
          placeholder="https://"
        />
      </Field>
    </div>
  )
}
