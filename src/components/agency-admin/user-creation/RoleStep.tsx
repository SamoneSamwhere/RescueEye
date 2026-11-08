import { UserCog } from 'lucide-react'
import { RoleSelectCard } from '../RoleSelectCard'
import { ROLE_OPTIONS } from './types'
import type { CreatableUserRole } from '../../../features/agency-admin'

interface RoleStepProps {
  selectedRole: CreatableUserRole | null
  onSelect: (role: CreatableUserRole) => void
}

export function RoleStep({ selectedRole, onSelect }: RoleStepProps) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start gap-2.5 rounded-md border border-accent-border bg-accent-subtle px-3 py-2.5">
        <UserCog className="mt-0.5 size-4 shrink-0 text-accent" />
        <div>
          <p className="text-xs font-medium text-accent">Choose a role</p>
          <p className="mt-0.5 text-xs leading-relaxed text-foreground-secondary">
            The role determines what this person can see and do in RescueEye. Personnel are managed from Manage
            Personnel.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {ROLE_OPTIONS.map((option) => (
          <RoleSelectCard
            key={option.role}
            icon={option.icon}
            title={option.title}
            description={option.description}
            responsibilities={option.responsibilities}
            selected={selectedRole === option.role}
            onSelect={() => onSelect(option.role)}
          />
        ))}
      </div>
    </div>
  )
}
