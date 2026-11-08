import { Navigate } from 'react-router-dom'
import { ROUTES } from '../routes/paths'

/**
 * Add Staff used to be its own page. It is now a dialog on Manage Personnel;
 * this keeps old links and bookmarks working by opening it there.
 */
export function AgencyAdminUserCreationPage() {
  return <Navigate to={ROUTES.agencyAdminAccountStatus} replace state={{ addStaff: true }} />
}
