import type { LucideIcon } from 'lucide-react'
import { BellRing, ClipboardCheck, Download, MapPinned, Navigation, Smartphone } from 'lucide-react'
import { buttonClasses } from '../ui'
import { Reveal } from './Reveal'
import { AmbientBackground } from './AmbientBackground'

/**
 * The Field Responder APK. `npm run android:apk` copies the build to
 * public/downloads/, so it ships with the website; set VITE_APK_DOWNLOAD_URL
 * to serve it from somewhere else (e.g. a GitHub release) instead.
 */
const APK_URL = import.meta.env.VITE_APK_DOWNLOAD_URL || '/downloads/RescueEye-FieldResponder.apk'
const APK_FILENAME = 'RescueEye-FieldResponder.apk'

interface AppFeature {
  icon: LucideIcon
  title: string
  description: string
}

const FEATURES: AppFeature[] = [
  {
    icon: BellRing,
    title: 'Rescue alerts',
    description: 'Get notified the moment Command Staff dispatch you to a verified incident.',
  },
  {
    icon: ClipboardCheck,
    title: 'Assigned missions',
    description: 'Review the incident type, severity, and location, then accept or decline.',
  },
  {
    icon: MapPinned,
    title: 'Navigation and maps',
    description: 'Get directions to the site and see other responders and drones on the damage map.',
  },
  {
    icon: Navigation,
    title: 'Response status',
    description: 'Mark yourself en route, on site, and rescue complete so command stays in sync.',
  },
]

export function MobileAppSection() {
  return (
    <section id="mobile-app" className="relative overflow-hidden bg-background">
      <AmbientBackground />
      <div className="relative mx-auto grid max-w-7xl grid-cols-1 items-center gap-12 px-4 py-20 sm:px-6 lg:grid-cols-2 lg:px-8">
        <Reveal>
          <p className="text-xs font-semibold uppercase tracking-wide text-accent">
            Field Responder app
          </p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
            Take your missions into the field
          </h2>
          <p className="mt-4 max-w-xl text-sm leading-relaxed text-foreground-secondary sm:text-base">
            The RescueEye Android app is built for Field Responders. Receive rescue alerts, manage
            the missions assigned to you, view incident details and maps, and update your response
            status from the scene. Sign in with the account your agency administrator created for
            you.
          </p>

          <div className="mt-8 flex flex-col items-start gap-3">
            <a
              href={APK_URL}
              download={APK_FILENAME}
              type="application/vnd.android.package-archive"
              className={buttonClasses(
                'primary',
                'lg',
                'w-full gap-2 px-6 transition-transform duration-200 hover:-translate-y-0.5 active:translate-y-0 sm:w-auto',
              )}
            >
              <Download className="size-4" aria-hidden="true" />
              Download Field Responder App
            </a>
            <p className="flex items-center gap-1.5 text-xs text-foreground-muted">
              <Smartphone className="size-3.5 shrink-0" aria-hidden="true" />
              Android 5.1 or later · .apk installer · allow installs from your browser when prompted
            </p>
          </div>
        </Reveal>

        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {FEATURES.map(({ icon: Icon, title, description }, index) => (
            <Reveal
              key={title}
              as="li"
              delayMs={index * 90}
              className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-5 shadow-panel"
            >
              <span className="inline-flex size-10 items-center justify-center rounded-md bg-accent-subtle text-accent">
                <Icon className="size-5" />
              </span>
              <div>
                <h3 className="text-base font-semibold text-foreground">{title}</h3>
                <p className="mt-1 text-sm leading-relaxed text-foreground-secondary">{description}</p>
              </div>
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  )
}
