import { Building2, Crown, FlaskConical } from 'lucide-react'
import { Button, Panel } from '../ui'
import { formatDateTime } from '../../lib/formatDateTime'
import { LEAD_COLOR, SUPPORT_COLOR, agencyColor, useDemoAgency } from '../../features/operations/useOperations'
import type { NearbyAgencies } from '../../features/operations/useOperations'
import type { GeoPoint } from '../../types/geo'

interface AgencyLegendPanelProps {
  data: NearbyAgencies | undefined
  /** This agency's first open incident: where the demo organization is placed. */
  demoCentre: GeoPoint | null
}

/**
 * Who else is working this area, and who leads. The lead is the organization
 * whose incident here has been open longest; when it closes them, the next one
 * takes over and the colours switch by themselves.
 */
export function AgencyLegendPanel({ data, demoCentre }: AgencyLegendPanelProps) {
  const { place, end } = useDemoAgency()
  const agencies = data?.agencies ?? []
  const others = agencies.filter((a) => !a.isSelf)
  const self = agencies.find((a) => a.isSelf)
  const demoPlaced = others.some((a) => a.demo)
  const radiusKm = (data?.radiusM ?? 5000) / 1000

  return (
    <Panel title="Organizations in this area">
      <div className="flex flex-col gap-3 text-sm">
        <div className="flex flex-wrap gap-3 text-xs text-foreground-secondary">
          <span className="flex items-center gap-1.5">
            <span className="size-3 rounded-full" style={{ background: LEAD_COLOR }} /> Lead organization
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-3 rounded-full border-2 border-dashed" style={{ borderColor: SUPPORT_COLOR }} />{' '}
            Supporting organization
          </span>
        </div>

        {!self || self.incidents.length === 0 ? (
          <p className="text-foreground-muted">
            Other organizations within {radiusKm} km appear here once your agency has an open incident.
          </p>
        ) : (
          <>
            <p className="text-foreground">
              {self.isLead ? (
                <>Your agency is <strong>leading</strong> this area.</>
              ) : (
                <>
                  <strong>{agencies.find((a) => a.isLead)?.name ?? 'Another organization'}</strong> is leading; your agency
                  is supporting.
                </>
              )}
            </p>
            <ul className="flex flex-col gap-2">
              {agencies.map((agency) => (
                <li key={agency.agencyId} className="flex items-start gap-2">
                  <span className="mt-1 size-3 shrink-0 rounded-full" style={{ background: agencyColor(agency) }} />
                  <div className="min-w-0">
                    <p className="flex items-center gap-1 font-medium text-foreground">
                      {agency.isLead ? <Crown className="size-3.5 text-success" /> : <Building2 className="size-3.5 text-foreground-muted" />}
                      <span className="truncate">{agency.name}</span>
                      {agency.isSelf ? <span className="font-normal text-foreground-muted">(you)</span> : null}
                    </p>
                    <p className="text-xs text-foreground-muted">
                      {agency.isLead ? 'Lead' : 'Supporting'} · {agency.incidents.length} incident
                      {agency.incidents.length === 1 ? '' : 's'}
                      {agency.isSelf ? '' : ` · ${agency.responders.length} responder${agency.responders.length === 1 ? '' : 's'}`}
                      {agency.leadingSince ? ` · since ${formatDateTime(agency.leadingSince)}` : ''}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
            {others.length === 0 ? (
              <p className="text-xs text-foreground-muted">No other organization is working within {radiusKm} km.</p>
            ) : null}
          </>
        )}

        {/* Rehearsal: a sample organization only this agency sees. */}
        {demoCentre ? (
          <div className="flex flex-col gap-2 border-t border-border pt-3">
            <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-foreground-secondary">
              <FlaskConical className="size-3.5" />
              Rehearsal
            </p>
            <p className="text-xs text-foreground-muted">
              Places a sample organization near your incident. Only your agency sees it.
            </p>
            {demoPlaced ? (
              <Button size="sm" variant="outline" disabled={end.isPending} onClick={() => end.mutate()}>
                End the sample organization's operation
              </Button>
            ) : (
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" disabled={place.isPending} onClick={() => place.mutate({ ...demoCentre, lead: true })}>
                  Add a sample organization (leading)
                </Button>
                <Button size="sm" variant="outline" disabled={place.isPending} onClick={() => place.mutate({ ...demoCentre, lead: false })}>
                  …(supporting)
                </Button>
              </div>
            )}
          </div>
        ) : null}
      </div>
    </Panel>
  )
}
