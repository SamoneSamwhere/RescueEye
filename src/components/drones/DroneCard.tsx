import { Loader2, Video, MonitorPlay, Pencil, Trash2 } from 'lucide-react'
import { Card, Button, StatusIndicator } from '../ui'
import { DroneIllustration } from './DroneIllustration'
import { formatDateTime } from '../../lib/formatDateTime'
import { cn } from '../../lib/cn'
import type { Drone } from '../../types/drone'

interface DroneCardProps {
  drone: Drone
  isConnecting: boolean
  isLive: boolean
  onConnect: (droneId: string) => void
  onStartLiveFeed: (droneId: string) => void
  onViewLive: () => void
  onEdit: (drone: Drone) => void
  onRemove: (drone: Drone) => void
}

const ICON_BUTTON_CLASS =
  'rounded-md p-1.5 text-foreground-muted transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus'

export function DroneCard({
  drone,
  isConnecting,
  isLive,
  onConnect,
  onStartLiveFeed,
  onViewLive,
  onEdit,
  onRemove,
}: DroneCardProps) {
  const isConnected = drone.connectionStatus === 'CONNECTED'

  return (
    <Card
      className={cn(
        'relative flex flex-col items-center gap-3 p-4 text-center transition-all duration-300',
        'hover:-translate-y-1 hover:border-accent-border hover:shadow-modal',
      )}
    >
      <div className="absolute right-2 top-2 flex gap-0.5">
        <button
          type="button"
          onClick={() => onEdit(drone)}
          aria-label={`Edit ${drone.name}`}
          title="Edit"
          className={cn(ICON_BUTTON_CLASS, 'hover:bg-surface-secondary hover:text-foreground')}
        >
          <Pencil className="size-3.5" />
        </button>
        <button
          type="button"
          onClick={() => onRemove(drone)}
          aria-label={`Remove ${drone.name}`}
          title="Remove"
          className={cn(ICON_BUTTON_CLASS, 'hover:bg-danger-subtle hover:text-danger-fg')}
        >
          <Trash2 className="size-3.5" />
        </button>
      </div>

      <DroneIllustration active={isConnected} className="h-20 w-full" />

      <div className="flex flex-col items-center gap-1">
        <span className="text-sm font-semibold text-foreground">{drone.name}</span>
        <span className="font-mono text-xs text-foreground-muted">{drone.serialNumber}</span>
      </div>

      {isConnecting ? (
        <span className="inline-flex items-center gap-1.5 text-sm text-foreground-secondary">
          <Loader2 className="size-3.5 animate-spin" />
          Connecting…
        </span>
      ) : (
        <StatusIndicator tone={isConnected ? 'success' : 'neutral'} label={isConnected ? 'Online' : 'Offline'} />
      )}

      <span className="text-xs text-foreground-muted">
        Last connected: {drone.lastConnectedAt ? formatDateTime(drone.lastConnectedAt) : '—'}
      </span>

      <div className="mt-1 w-full">
        {isConnected ? (
          <Button
            size="sm"
            className="w-full"
            variant={isLive ? 'secondary' : 'primary'}
            onClick={() => (isLive ? onViewLive() : onStartLiveFeed(drone.id))}
          >
            {isLive ? (
              <>
                <MonitorPlay className="size-3.5" />
                View Live
              </>
            ) : (
              <>
                <Video className="size-3.5" />
                Start Live Feed
              </>
            )}
          </Button>
        ) : (
          <Button size="sm" variant="outline" className="w-full" disabled={isConnecting} onClick={() => onConnect(drone.id)}>
            {isConnecting ? 'Connecting…' : 'Connect'}
          </Button>
        )}
      </div>
    </Card>
  )
}
