import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Radio, ServerCrash, Zap, ZapOff } from 'lucide-react'
import { PageHeader } from '../components/layout'
import { Reveal } from '../components/landing/Reveal'
import { Panel, EmptyState, Button, LoadingState } from '../components/ui'
import { LiveFeedPanel } from '../components/media'
import { useFeeds, useCloseFeed } from '../features/media/useFeeds'
import { ROUTES } from '../routes/paths'
import { PageHelpButton } from '../components/help/PageHelpButton'

export function CommandStaffLiveMonitoringPage() {
  const [detectEnabled, setDetectEnabled] = useState(true)

  // A drone that goes live opens its feed by itself (api/services/drone_ingest.py); poll
  // often enough that its panel appears within a couple of seconds of Go Live.
  const feedsQuery = useFeeds(1500)
  const closeFeed = useCloseFeed()

  // Live drone feeds only. Uploaded clips play in their own section on Drones
  // & Media: a replayed recording on this wall reads as something happening now.
  const feeds = (feedsQuery.data?.feeds ?? []).filter((feed) => feed.kind === 'live')
  // The API suggests a cadence based on how many panels are open, so four
  // feeds don't all hammer /detect at the single-feed rate.
  const intervalMs = feedsQuery.data?.suggestedDetectIntervalMs ?? 350

  // A casualty awaiting a decision pops up over this page (and every other
  // Command Staff page) - see CasualtyAlertPopup, mounted in the router.

  const loadError = feedsQuery.error instanceof Error ? feedsQuery.error.message : null

  return (
    <>
      <PageHeader
        title="Live Monitoring"
        description="Live drone feeds, full-size, with AI detection running over them."
        actions={<PageHelpButton guideId="live-monitoring" />}
      />

      <div className="flex flex-col gap-4 px-4 py-4">
        {feeds.length > 0 ? (
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-foreground-secondary">
              {feeds.length} live feed{feeds.length === 1 ? '' : 's'} running
            </p>
            <Button
              variant={detectEnabled ? 'outline' : 'secondary'}
              size="sm"
              onClick={() => setDetectEnabled((on) => !on)}
            >
              {detectEnabled ? <Zap className="size-3.5" /> : <ZapOff className="size-3.5" />}
              {detectEnabled ? 'AI detection on' : 'AI detection off'}
            </Button>
          </div>
        ) : null}

        <Reveal>
          {feedsQuery.isLoading ? (
            <Panel title="Live Feeds">
              <LoadingState label="Looking for running feeds…" />
            </Panel>
          ) : loadError ? (
            <Panel title="Live Feeds">
              <EmptyState
                icon={ServerCrash}
                title="Could not reach the detection API"
                description={loadError}
                action={
                  <Button variant="outline" size="sm" onClick={() => void feedsQuery.refetch()}>
                    Retry
                  </Button>
                }
              />
            </Panel>
          ) : feeds.length === 0 ? (
            <Panel title="Live Feeds">
              <EmptyState
                icon={Radio}
                title="No live drone feeds right now"
                description="Connect a drone and start its live feed from the Drones page to see it here. Uploaded recordings play in the Media Library, not on this screen."
                action={
                  <Link to={ROUTES.commandStaffDrones}>
                    <Button size="sm">Go to Drones</Button>
                  </Link>
                }
              />
            </Panel>
          ) : (
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              {feeds.map((feed) => (
                <LiveFeedPanel
                  key={feed.id}
                  feed={feed}
                  detectEnabled={detectEnabled}
                  intervalMs={intervalMs}
                  onClose={(id) => closeFeed.mutate(id)}
                />
              ))}
            </div>
          )}
        </Reveal>


      </div>
    </>
  )
}
