import { useState } from 'react'
import { Drone } from 'lucide-react'
import { Card, Button } from '../ui'

interface PilotModeCardProps {
  pilotDrone: string | null
  onChange: (droneName: string | null) => void
}

/**
 * "I'm flying this drone." Most drones stream video with no GPS in it, so
 * while this is on, the pilot's phone stands in for the drone's position on
 * the Command Staff map — shown as a wide circle, because the drone is near
 * the pilot, not on them (api/services/drone_locations.py). The name must
 * match the drone's name in Connect Drone.
 */
export function PilotModeCard({ pilotDrone, onChange }: PilotModeCardProps) {
  const [name, setName] = useState('')

  return (
    <Card className="flex flex-col gap-3 px-4 py-4">
      <div className="flex items-center gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-accent-subtle text-accent">
          <Drone className="size-5" />
        </span>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-foreground">Drone pilot</p>
          <p className="text-xs text-foreground-secondary">
            {pilotDrone
              ? `Your location is placing “${pilotDrone}” on the map.`
              : 'Flying a drone with no GPS link? Your phone can show where it is.'}
          </p>
        </div>
      </div>
      {pilotDrone ? (
        <Button variant="outline" onClick={() => onChange(null)}>
          Stop — I've landed
        </Button>
      ) : (
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            if (name.trim()) onChange(name.trim())
          }}
        >
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Drone name, as in Connect Drone"
            aria-label="Drone name"
            className="h-11 min-w-0 flex-1 rounded-md border border-border bg-surface px-3 text-sm text-foreground"
          />
          <Button type="submit" disabled={!name.trim()}>
            I'm flying it
          </Button>
        </form>
      )}
    </Card>
  )
}
