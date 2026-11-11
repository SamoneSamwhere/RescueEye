import { LayoutDashboard, Plane, Video, ScanSearch, ShieldCheck, Map, MonitorPlay, FileText, CircleHelp, UsersRound } from 'lucide-react'
import type { NavItem } from '../../types/nav'
import { ROUTES } from '../../routes/paths'

export const COMMAND_STAFF_NAV_ITEMS: NavItem[] = [
  { label: 'Dashboard', href: ROUTES.commandStaff, icon: LayoutDashboard },
  { label: 'Drones', href: ROUTES.commandStaffDrones, icon: Plane },
  { label: 'Media Library', href: ROUTES.commandStaffMediaLibrary, icon: Video },
  { label: 'Live Monitoring', href: ROUTES.commandStaffLiveMonitoring, icon: MonitorPlay },
  { label: 'Detection Review', href: ROUTES.commandStaffDetections, icon: ScanSearch },
  { label: 'My Team', href: ROUTES.commandStaffTeam, icon: UsersRound },
  { label: 'Incidents', href: ROUTES.commandStaffIncidents, icon: ShieldCheck },
  { label: 'Damage Map', href: ROUTES.commandStaffMap, icon: Map },
  { label: 'Logs', href: ROUTES.commandStaffLogs, icon: FileText },
  { label: 'Help', href: ROUTES.commandStaffHelp, icon: CircleHelp },
]
