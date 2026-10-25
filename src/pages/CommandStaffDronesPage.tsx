import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Wifi } from 'lucide-react'
import { PageHeader } from '../components/layout'
import { Reveal } from '../components/landing/Reveal'
import { DroneList, DroneRegistrationModal } from '../components/drones'
import { Button } from '../components/ui'
import { ConnectDroneModal } from '../components/media'
import { useCommandStaffData } from '../features/command-staff'
import { useUserStore } from '../state/UserStore'
import { useAddFeed } from '../features/media/useFeeds'
import { ROUTES } from '../routes/paths'

const CONNECT_DELAY_MS = 800

/**
 * Drones — register them, connect them, and start their live feeds.
 * Recorded footage lives in the Media Library, not here.
 */
export function CommandStaffDronesPage() {
  const navigate = useNavigate()
  const { drones, liveDroneIds, connectDrone, startLiveFeed, addDemoDrone, registerDrone } = useCommandStaffData()
  const { users } = useUserStore()

  const [connectingDroneId, setConnectingDroneId] = useState<string | null>(null)
  const [connectOpen, setConnectOpen] = useState(false)
  const [registerOpen, setRegisterOpen] = useState(false)
  const addFeed = useAddFeed()

  function handleConnect(droneId: string) {
    setConnectingDroneId(droneId)
    window.setTimeout(() => {
      connectDrone(droneId)
      setConnectingDroneId(null)
    }, CONNECT_DELAY_MS)
  }

  function handleAddDemoDrone() {
    const drone = addDemoDrone()
    // Connect it immediately: an operator who asked for a demo drone wants to
    // reach the feed step, not watch a second spinner first.
    handleConnect(drone.id)
  }

  /**
   * Opens a real live source as a feed and hands off to Live Monitoring.
   *
   * A wildcard source means the API listens and the aircraft publishes to it,
   * so the feed is registered *before* the pilot starts streaming — the panel
   * simply stays dark until frames arrive.
   */
  function handleConnectFeed(source: string, label: string) {
    addFeed.mutate(
      { source, label },
      {
        onSuccess: () => {
          setConnectOpen(false)
          navigate(ROUTES.commandStaffLiveMonitoring)
        },
      },
    )
  }

  /** Hands the drone's feed off to the dedicated Live Monitoring screen instead of streaming it inline. */
  function handleStartLiveFeed(droneId: string) {
    startLiveFeed(droneId)
    navigate(ROUTES.commandStaffLiveMonitoring)
  }

  return (
    <>
      <PageHeader title="Drones" description="Register drones, connect them, and start their live feeds." />

      <div className="flex flex-col gap-4 px-4 py-4">
        <Reveal>
          <div className="flex justify-end">
            <Button
              size="sm"
              onClick={() => {
                addFeed.reset()
                setConnectOpen(true)
              }}
            >
              <Wifi className="size-3.5" />
              Connect Drone
            </Button>
          </div>
        </Reveal>

        <Reveal>
          <DroneList
            drones={drones}
            connectingDroneId={connectingDroneId}
            liveDroneIds={liveDroneIds}
            onConnect={handleConnect}
            onStartLiveFeed={handleStartLiveFeed}
            onViewLive={() => navigate(ROUTES.commandStaffLiveMonitoring)}
            onRegisterClick={() => setRegisterOpen(true)}
            onAddDemoDrone={handleAddDemoDrone}
          />
        </Reveal>
      </div>

      {/* Mounted only while open, so each registration starts at step one with an empty form. */}
      {registerOpen ? (
        <DroneRegistrationModal
          open
          onClose={() => setRegisterOpen(false)}
          existingSerialNumbers={drones.map((d) => d.serialNumber)}
          existingRegistrationNumbers={drones.flatMap((d) => (d.registrationNumber ? [d.registrationNumber] : []))}
          availableOperators={users.filter((u) => u.role === 'COMMAND_STAFF' && u.accountStatus === 'ACTIVE')}
          onRegister={registerDrone}
        />
      ) : null}

      <ConnectDroneModal
        open={connectOpen}
        onClose={() => setConnectOpen(false)}
        onConnect={handleConnectFeed}
        connecting={addFeed.isPending}
        error={addFeed.error instanceof Error ? addFeed.error.message : null}
        onViewLive={() => {
          setConnectOpen(false)
          navigate(ROUTES.commandStaffLiveMonitoring)
        }}
      />
    </>
  )
}
