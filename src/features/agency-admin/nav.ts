import { LayoutDashboard, Users, UsersRound, History, CircleHelp } from 'lucide-react'
import type { NavItem } from '../../types/nav'
import { ROUTES } from '../../routes/paths'

export const AGENCY_ADMIN_NAV_ITEMS: NavItem[] = [
  { label: 'Dashboard', href: ROUTES.agencyAdmin, icon: LayoutDashboard },
  // Add Staff lives on the Manage Personnel page, next to the people it adds.
  { label: 'Manage Personnel', href: ROUTES.agencyAdminAccountStatus, icon: Users },
  { label: 'Response Teams', href: ROUTES.agencyAdminTeams, icon: UsersRound },
  { label: 'Mission History', href: ROUTES.agencyAdminIncidentHistory, icon: History },
  { label: 'Help', href: ROUTES.agencyAdminHelp, icon: CircleHelp },
]
