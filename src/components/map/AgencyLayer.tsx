import { Fragment } from 'react'
import { Circle, CircleMarker, Tooltip } from 'react-leaflet'
import { agencyColor } from '../../features/operations/useOperations'
import type { NearbyAgency } from '../../features/operations/useOperations'

/** Ring drawn around each organization's incidents: the patch of ground it has committed to. */
const SITE_RING_M = 150

/**
 * Organizations working the same area, drawn in their role's colour: the lead
 * green, the others blue. Each incident gets a ring marking that agency's
 * site - this agency's own included, so the operator sees whether they lead.
 * Other agencies' responders are dots without names; this agency's own are
 * already on the map as normal responder markers.
 */
export function AgencyLayer({ agencies }: { agencies: NearbyAgency[] }) {
  return (
    <>
      {agencies.map((agency) => {
        const color = agencyColor(agency)
        const role = agency.isLead ? 'Lead organization' : 'Supporting organization'
        const who = agency.isSelf ? `${agency.name} (your agency)` : agency.name
        return (
          <Fragment key={agency.agencyId}>
            {agency.incidents.map((incident, i) => (
              <Circle
                key={`${agency.agencyId}-site-${i}`}
                center={[incident.lat, incident.lng]}
                radius={SITE_RING_M}
                pathOptions={{ color, weight: 2.5, dashArray: agency.isLead ? undefined : '6 5', fillColor: color, fillOpacity: 0.08 }}
              >
                <Tooltip>
                  {who} · {role}
                </Tooltip>
              </Circle>
            ))}
            {agency.isSelf
              ? null
              : agency.incidents.map((incident, i) => (
                  <CircleMarker
                    key={`${agency.agencyId}-incident-${i}`}
                    center={[incident.lat, incident.lng]}
                    radius={9}
                    pathOptions={{ color: '#ffffff', weight: 2, fillColor: color, fillOpacity: 0.9 }}
                  >
                    <Tooltip direction="top" offset={[0, -6]}>
                      {who} · incident · {role}
                    </Tooltip>
                  </CircleMarker>
                ))}
            {agency.isSelf
              ? null
              : agency.responders.map((responder, i) => (
                  <CircleMarker
                    key={`${agency.agencyId}-responder-${i}`}
                    center={[responder.lat, responder.lng]}
                    radius={5}
                    pathOptions={{ color, weight: 2, fillColor: color, fillOpacity: responder.busy ? 0.9 : 0.35 }}
                  >
                    <Tooltip direction="top" offset={[0, -4]}>
                      {who} · responder · {responder.busy ? 'on a mission' : 'available'}
                    </Tooltip>
                  </CircleMarker>
                ))}
          </Fragment>
        )
      })}
    </>
  )
}
