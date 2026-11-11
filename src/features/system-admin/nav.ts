import { LayoutDashboard, ShieldCheck, Building2, CircleHelp } from 'lucide-react'
import type { NavItem } from '../../types/nav'
import { ROUTES } from '../../routes/paths'

export const SYSTEM_ADMIN_NAV_ITEMS: NavItem[] = [
  { label: 'Dashboard', href: ROUTES.systemAdmin, icon: LayoutDashboard },
  { label: 'Agency Validation', href: ROUTES.systemAdminAgencyValidation, icon: ShieldCheck },
  { label: 'Manage Agency', href: ROUTES.systemAdminAgencyStatus, icon: Building2 },
  { label: 'Help', href: ROUTES.systemAdminHelp, icon: CircleHelp },
]
