import { Radio } from 'lucide-react'
import { Panel, Button, EmptyState } from '../ui'
import { DroneCard } from './DroneCard'
import type { Drone } from '../../types/drone'

interface DroneListProps {
  drones: Drone[]
  connectingDroneId: string | null
  liveDroneIds: string[]
  onConnect: (droneId: string) => void
  onStartLiveFeed: (droneId: string) => void
  onViewLive: () => void
  onRegisterClick: () => void
}

export function DroneList({
  drones,
  connectingDroneId,
  liveDroneIds,
  onConnect,
  onStartLiveFeed,
  onViewLive,
  onRegisterClick,
}: DroneListProps) {
  return (
    <Panel
      title="Registered Drones"
      actions={
        <Button size="sm" onClick={onRegisterClick}>
          Register Drone
        </Button>
      }
    >
      {drones.length === 0 ? (
        <EmptyState
          icon={Radio}
          title="No drones registered"
          description="Only registered drones can be connected. Register one to get started."
          action={
            <Button size="sm" onClick={onRegisterClick}>
              Register Drone
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {drones.map((drone) => (
            <DroneCard
              key={drone.id}
              drone={drone}
              isConnecting={connectingDroneId === drone.id}
              isLive={liveDroneIds.includes(drone.id)}
              onConnect={onConnect}
              onStartLiveFeed={onStartLiveFeed}
              onViewLive={onViewLive}
            />
          ))}
        </div>
      )}
    </Panel>
  )
}
