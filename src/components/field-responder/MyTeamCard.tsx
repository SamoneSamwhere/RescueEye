import { UsersRound } from 'lucide-react'
import { Card } from '../ui'
import { useAuth } from '../../features/auth'
import { useMyTeam } from '../../features/teams/useTeams'

/** Which team this responder is on, who leads it and who they go out with. Hidden when on no team. */
export function MyTeamCard() {
  const { session } = useAuth()
  const team = useMyTeam(session?.role === 'FIELD_RESPONDER').data
  if (!team || !session) return null
  const others = team.members.filter((m) => m.id !== session.id).map((m) => m.name)
  return (
    <Card className="flex items-start gap-3 px-4 py-3">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-accent-subtle text-accent">
        <UsersRound className="size-5" />
      </span>
      <div className="min-w-0 text-sm">
        <p className="font-semibold text-foreground">You're on Team {team.name}</p>
        <p className="text-foreground-secondary">Led by {team.commanderName || 'your Command Staff'}</p>
        {others.length ? <p className="text-foreground-muted">With {others.join(', ')}</p> : null}
      </div>
    </Card>
  )
}
