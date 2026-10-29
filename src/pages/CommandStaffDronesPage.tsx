import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Wifi } from 'lucide-react'
import { PageHeader } from '../components/layout'
import { Reveal } from '../components/landing/Reveal'
import { DroneList, DroneFormModal } from '../components/drones'
import { Button, Modal } from '../components/ui'
import { ConnectDroneModal } from '../components/media'
import { useCommandStaffData } from '../features/command-staff'
import { useAddFeed } from '../features/media/useFeeds'
import { useToast } from '../features/toast'
import { ROUTES } from '../routes/paths'
import type { Drone } from '../types/drone'

const CONNECT_DELAY_MS = 800

/**
 * Drones — register, edit and remove them, connect them, and start their live
 * feeds. Recorded footage lives in the Media Library, not here.
 */
export function CommandStaffDronesPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const { drones, liveDroneIds, connectDrone, startLiveFeed, registerDrone, updateDroneDetails, removeDrone } =
    useCommandStaffData()

  const [connectingDroneId, setConnectingDroneId] = useState<string | null>(null)
  const [connectOpen, setConnectOpen] = useState(false)
  const [registerOpen, setRegisterOpen] = useState(false)
  const [editingDrone, setEditingDrone] = useState<Drone | null>(null)
  const [removingDrone, setRemovingDrone] = useState<Drone | null>(null)
  const [removing, setRemoving] = useState(false)
  const [removeError, setRemoveError] = useState<string | null>(null)

  /** Serial and registration numbers taken by the agency's drones, one drone's own left out when editing it. */
  function takenNumbers(exceptDroneId?: string) {
    const others = drones.filter((d) => d.id !== exceptDroneId)
    return {
      existingSerialNumbers: others.map((d) => d.serialNumber),
      existingRegistrationNumbers: others.flatMap((d) => (d.registrationNumber ? [d.registrationNumber] : [])),
    }
  }

  function openRemove(drone: Drone) {
    setRemoveError(null)
    setRemovingDrone(drone)
  }

  function closeRemove() {
    if (!removing) setRemovingDrone(null)
  }

  async function confirmRemove() {
    if (!removingDrone) return
    setRemoving(true)
    const result = await removeDrone(removingDrone.id)
    setRemoving(false)
    if (!result.ok) {
      setRemoveError(result.error || 'Failed to remove the drone. Please try again.')
      return
    }
    toast.success(`${removingDrone.name} was removed from the fleet.`, 'Drone removed')
    setRemovingDrone(null)
  }
  const addFeed = useAddFeed()

  function handleConnect(droneId: string) {
    setConnectingDroneId(droneId)
    window.setTimeout(() => {
      connectDrone(droneId)
      setConnectingDroneId(null)
    }, CONNECT_DELAY_MS)
  }

  /**
   * Opens a real live source as a feed and hands off to Live Monitoring.
   *
   * A wildcard source means the API listens and the aircraft publishes to it,
   * so the feed is registered *before* the pilot starts streaming — the panel
   * simply stays dark until frames arrive.
   */
  function handleConnectFeed(source: string, label: string, droneId: string) {
    addFeed.mutate(
      { source, label, droneId },
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
            onEdit={setEditingDrone}
            onRemove={openRemove}
          />
        </Reveal>
      </div>

      {/* Mounted only while open, so each opening starts from a fresh form. */}
      {registerOpen ? (
        <DroneFormModal open onClose={() => setRegisterOpen(false)} {...takenNumbers()} onSubmit={registerDrone} />
      ) : null}

      {editingDrone ? (
        <DroneFormModal
          open
          drone={editingDrone}
          onClose={() => setEditingDrone(null)}
          {...takenNumbers(editingDrone.id)}
          onSubmit={(data) => updateDroneDetails(editingDrone.id, data)}
          onSaved={(name) => toast.success(`${name} was updated.`, 'Changes saved')}
        />
      ) : null}

      <Modal
        open={!!removingDrone}
        onClose={closeRemove}
        title="Remove Drone"
        footer={
          <>
            <Button variant="outline" onClick={closeRemove} disabled={removing}>
              Cancel
            </Button>
            <Button variant="danger" onClick={confirmRemove} disabled={removing}>
              {removing ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  Removing…
                </>
              ) : (
                'Remove Drone'
              )}
            </Button>
          </>
        }
      >
        {removingDrone ? (
          <div className="flex flex-col gap-3">
            <p>
              Remove <strong>{removingDrone.name}</strong> (serial{' '}
              <span className="font-mono">{removingDrone.serialNumber}</span>) from your agency's fleet? It will no
              longer be able to connect or stream. Detections it already recorded are kept. This can't be undone.
            </p>
            {removeError ? (
              <div className="rounded-md bg-danger-subtle px-3 py-2 text-sm text-danger-fg" role="alert">
                {removeError}
              </div>
            ) : null}
          </div>
        ) : null}
      </Modal>

      <ConnectDroneModal
        open={connectOpen}
        onClose={() => setConnectOpen(false)}
        drones={drones}
        onRegisterClick={() => {
          setConnectOpen(false)
          setRegisterOpen(true)
        }}
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
