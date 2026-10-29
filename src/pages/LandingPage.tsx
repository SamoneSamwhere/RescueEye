import {
  LandingHeader,
  HeroSection,
  CapabilitiesGrid,
  WorkflowTimeline,
  MobileAppSection,
  CtaSection,
  LandingFooter,
} from '../components/landing'

function LandingPageContent() {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <LandingHeader />
      <main>
      <HeroSection />
      <CapabilitiesGrid />
        <WorkflowTimeline />
        <MobileAppSection />
        <CtaSection />
      </main>
      <LandingFooter />
    </div>
  )
}

export function LandingPage() {
  return <LandingPageContent />
}
