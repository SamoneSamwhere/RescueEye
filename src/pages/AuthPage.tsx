import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { Building2, CheckCircle2, LogIn } from 'lucide-react'
import { useAuth, ROLE_HOME_ROUTE } from '../features/auth'
import { IS_RESPONDER_APP } from '../lib/appTarget'
import { ServerAddressSetting } from '../components/field-responder/ServerAddressSetting'
import { Field, Input, Button } from '../components/ui'
import { AuthPageShell, Reveal } from '../components/landing'
import { AuthCardDecor } from '../components/landing/AuthCardDecor'
import {
  RegistrationStepper,
  OrganizationDetailsStep,
  AddressStep,
  AdminInfoStep,
  DocumentsStep,
  DOCUMENT_CATALOGUE,
  OTHER_POSITION,
  categoryForType,
  documentsFor,
  emptyDocumentRecord,
  formatAddress,
  resolvedPosition,
} from '../components/landing/registration'
import type {
  AgencyInfoValues,
  AdminInfoValues,
  DocumentFiles,
  DocumentErrors,
  DocumentId,
  OrganizationCategory,
} from '../components/landing/registration'
import { useAgencyStore } from '../state/AgencyStore'
import { useAgencyDatabase } from '../db/useAgencyDatabase'
import { now } from '../lib/now'
import { formatPhPhone, parsePhPhone } from '../lib/phone'
import { cn } from '../lib/cn'

type AuthMode = 'signin' | 'signup'

const STEP_LABELS = ['Organization', 'Address', 'Admin', 'Documents']

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
/** Letters (any script, so ñ and accented names pass), spaces, hyphens, apostrophes and periods. */
const NAME_PATTERN = /^[\p{L}][\p{L}\s.'-]*$/u
/** Philippine ZIP codes are four digits. */
const ZIP_PATTERN = /^\d{4}$/

function validateOrganizationStep(values: AgencyInfoValues): string | null {
  if (!values.agencyName.trim() || !values.agencyType || !values.agencyPhone.trim() || !values.agencyEmail.trim()) {
    return 'Please fill in all required organization fields.'
  }
  const orgPhone = parsePhPhone(values.agencyPhone)
  if (!orgPhone.ok) return orgPhone.error
  if (!EMAIL_PATTERN.test(values.agencyEmail)) {
    return 'Enter a valid official email address.'
  }
  return null
}

function validateAddressStep(values: AgencyInfoValues): string | null {
  // City and barangay are only selectable once their parents (region, and
  // province where applicable) are chosen, so having both codes set already
  // guarantees the whole chain above them was picked too.
  if (!values.addressCityCode || !values.addressBarangayCode) {
    return 'Please select your region, province, city/municipality, and barangay.'
  }
  if (!values.addressZip.trim()) {
    return 'Please enter a ZIP code.'
  }
  if (!ZIP_PATTERN.test(values.addressZip.trim())) {
    return 'ZIP code must be 4 digits (e.g. 6000 for Cebu City).'
  }
  return null
}

function validateAdminStep(values: AdminInfoValues): string | null {
  if (
    !values.firstName.trim() ||
    !values.middleName.trim() ||
    !values.lastName.trim() ||
    !values.position ||
    !values.email.trim() ||
    !values.phone.trim() ||
    !values.password ||
    !values.confirmPassword
  ) {
    return 'Please fill in all required admin fields, including your middle name.'
  }
  for (const [label, value] of [
    ['First name', values.firstName],
    ['Middle name', values.middleName],
    ['Last name', values.lastName],
  ] as const) {
    if (!NAME_PATTERN.test(value.trim())) return `${label} can only contain letters, spaces, hyphens, and apostrophes.`
  }
  if (values.position === OTHER_POSITION && !values.positionOther.trim()) {
    return 'Enter your position.'
  }
  if (!EMAIL_PATTERN.test(values.email)) {
    return 'Enter a valid email address.'
  }
  const adminPhone = parsePhPhone(values.phone, ['mobile'])
  if (!adminPhone.ok) return adminPhone.error
  if (values.password.length < 8) {
    return 'Password must be at least 8 characters.'
  }
  if (values.password !== values.confirmPassword) {
    return 'Passwords do not match.'
  }
  return null
}

function validateDocumentsStep(
  category: OrganizationCategory,
  files: DocumentFiles,
  errors: DocumentErrors,
  agreedToTerms: boolean,
): string | null {
  const docs = documentsFor(category)
  const missing = docs.filter((doc) => doc.requirement === 'required' && !files[doc.id])
  if (missing.length > 0) {
    return `Please upload: ${missing.map((doc) => DOCUMENT_CATALOGUE[doc.id].label).join(', ')}.`
  }
  const oneOf = docs.filter((doc) => doc.requirement === 'oneOf')
  if (oneOf.length > 0 && !oneOf.some((doc) => files[doc.id])) {
    return 'Upload at least one supporting document — any of the ones listed is enough.'
  }
  if (docs.some((doc) => errors[doc.id])) {
    return 'Resolve the file errors above before continuing.'
  }
  if (!agreedToTerms) {
    return 'You must agree to the Terms of Service to continue.'
  }
  return null
}

const MOBILE_QUERY = '(max-width: 1023px)'

/**
 * Sign-in fields stand out from the card: a fill a shade lighter than the card
 * (a foreground tint, so it works in both themes — the default input fill is
 * darker than the card in dark mode), a clearly visible border, and a little
 * more height for a primary form.
 */
const SIGN_IN_INPUT_CLASS =
  'h-11 border-foreground-muted/70 bg-foreground/[0.06] px-3 text-base placeholder:text-foreground-secondary/60 hover:border-foreground-muted focus-visible:border-accent'

export function AuthPage() {
  const { login, logout, session } = useAuth()
  const { addAgency } = useAgencyStore()
  const { createAgency: createAgencyInDb, isLoading: isCreatingAgency } = useAgencyDatabase()
  const [searchParams, setSearchParams] = useSearchParams()
  const mode: AuthMode = searchParams.get('mode') === 'signup' ? 'signup' : 'signin'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loginError, setLoginError] = useState<string | null>(null)
  const [isLoggingIn, setIsLoggingIn] = useState(false)

  const [currentStep, setCurrentStep] = useState(0)
  const [agency, setAgency] = useState<AgencyInfoValues>({
    agencyName: '',
    agencyType: '',
    addressStreet: '',
    addressRegionCode: '',
    addressRegionName: '',
    addressProvinceCode: '',
    addressProvince: '',
    addressCityCode: '',
    addressCity: '',
    addressBarangayCode: '',
    addressBarangay: '',
    addressZip: '',
    agencyPhone: '',
    agencyEmail: '',
    agencyWebsite: '',
  })
  const [admin, setAdmin] = useState<AdminInfoValues>({
    firstName: '',
    middleName: '',
    lastName: '',
    position: '',
    positionOther: '',
    email: '',
    phone: '',
    password: '',
    confirmPassword: '',
  })
  const [documents, setDocuments] = useState<DocumentFiles>(() => emptyDocumentRecord<File | null>(null))
  const [documentErrors, setDocumentErrors] = useState<DocumentErrors>(() => emptyDocumentRecord<string | null>(null))
  const category = categoryForType(agency.agencyType)
  const [agreedToTerms, setAgreedToTerms] = useState(false)
  const [signupError, setSignupError] = useState<string | null>(null)
  const [submitted, setSubmitted] = useState(false)

  useEffect(() => {
    // Field responders only sign in on mobile — registration is a desktop, agency-admin flow.
    if (mode !== 'signup') return
    const mql = window.matchMedia(MOBILE_QUERY)
    if (mql.matches) switchMode('signin')
    const onChange = (event: MediaQueryListEvent) => {
      if (event.matches) switchMode('signin')
    }
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode])

  // The Android app is the Field Responder app only; anyone else is signed
  // straight back out and pointed at the website.
  const wrongAppRole = IS_RESPONDER_APP && !!session && session.role !== 'FIELD_RESPONDER'
  useEffect(() => {
    if (!wrongAppRole) return
    logout()
    setLoginError('This app is for Field Responders. Command Staff and administrators sign in on the RescueEye website.')
  }, [wrongAppRole, logout])

  if (session && !wrongAppRole) {
    return <Navigate to={ROLE_HOME_ROUTE[session.role]} replace />
  }

  function switchMode(next: AuthMode) {
    const params = new URLSearchParams(searchParams)
    if (next === 'signup') params.set('mode', 'signup')
    else params.delete('mode')
    setSearchParams(params, { replace: true })
  }

  async function handleLoginSubmit(event: FormEvent) {
    event.preventDefault()
    setLoginError(null)
    setIsLoggingIn(true)
    const result = await login(email, password)
    setIsLoggingIn(false)
    if (!result.ok) {
      setLoginError(result.error)
    }
  }

  function handleDocumentChange(id: DocumentId, file: File | null, docError: string | null) {
    setDocuments((prev) => ({ ...prev, [id]: file }))
    setDocumentErrors((prev) => ({ ...prev, [id]: docError }))
  }

  function goToNextStep() {
    const stepError =
      currentStep === 0
        ? validateOrganizationStep(agency)
        : currentStep === 1
          ? validateAddressStep(agency)
          : validateAdminStep(admin)
    if (stepError) {
      setSignupError(stepError)
      return
    }
    setSignupError(null)
    setCurrentStep((step) => step + 1)
  }

  function goToPreviousStep() {
    setSignupError(null)
    setCurrentStep((step) => Math.max(0, step - 1))
  }

  async function handleSignupSubmit(event: FormEvent) {
    event.preventDefault()
    const stepError = validateDocumentsStep(category, documents, documentErrors, agreedToTerms)
    if (stepError) {
      setSignupError(stepError)
      return
    }
    setSignupError(null)

    const address = formatAddress(agency)
    const position = resolvedPosition(admin)

    let result: Awaited<ReturnType<typeof createAgencyInDb>>
    try {
      result = await createAgencyInDb({
        agencyName: agency.agencyName,
        agencyType: agency.agencyType,
        agencyAddress: address,
        agencyAddressRegionCode: agency.addressRegionCode,
        agencyAddressProvinceCode: agency.addressProvinceCode,
        agencyAddressCityCode: agency.addressCityCode,
        agencyAddressBarangayCode: agency.addressBarangayCode,
        agencyPhone: formatPhPhone(agency.agencyPhone),
        agencyEmail: agency.agencyEmail,
        agencyWebsite: agency.agencyWebsite,
        adminFirstName: admin.firstName,
        adminMiddleName: admin.middleName,
        adminLastName: admin.lastName,
        adminPosition: position,
        adminEmail: admin.email,
        adminPhone: formatPhPhone(admin.phone, ['mobile']),
        adminPassword: admin.password,
      })
    } catch (err) {
      // createAgency reports its own failures; this catches anything it didn't
      // (a crash in password hashing, say) so the form never fails silently.
      console.error('Registration failed unexpectedly:', err)
      setSignupError('Registration could not be submitted. Please try again.')
      return
    }

    if (!result.success) {
      setSignupError(result.error || 'Failed to register your organization. Please try again.')
      // The email lives on the Admin step; land the user where they can fix it
      // instead of leaving them on Documents with nothing to change.
      if (result.field === 'adminEmail') setCurrentStep(2)
      return
    }

    // Also add to local mock store for consistency
    addAgency({
      id: `agency-${result.agencyId}`,
      name: agency.agencyName,
      agencyType: agency.agencyType,
      address,
      contactPhone: formatPhPhone(agency.agencyPhone),
      contactEmail: agency.agencyEmail,
      website: agency.agencyWebsite || undefined,
      agencyAdmin: {
        fullName: [admin.firstName, admin.middleName, admin.lastName].map((n) => n.trim()).join(' '),
        position,
        email: admin.email,
        phone: formatPhPhone(admin.phone, ['mobile']),
      },
      // The files the reviewer will look at. These were dropped before — the
      // record went out with no documents at all, so the System Admin had
      // nothing to verify against. Held as object URLs for this session.
      documents: documentsFor(category)
        .filter(({ id }) => documents[id])
        .map(({ id, requirement }) => {
          const file = documents[id] as File
          return {
            id,
            label: DOCUMENT_CATALOGUE[id].label,
            required: requirement === 'required',
            fileName: file.name,
            fileType: file.type === 'application/pdf' ? ('pdf' as const) : ('image' as const),
            url: URL.createObjectURL(file),
            uploadedAt: now().toISOString(),
          }
        }),
      registrationStatus: 'PENDING',
      accountStatus: 'INACTIVE',
      registeredAt: now().toISOString(),
    })

    setSubmitted(true)
  }

  // Sign in is always the same two fields, so it keeps one small fixed height. Registration's
  // tallest step (Documents, with up to six upload slots) doesn't fit that same height no matter
  // how tight the spacing gets, so signup gets a taller card instead — capped against the
  // viewport so it never grows past the visible screen.
  const cardWidthClass = 'max-w-2xl'
  const cardHeightClass = mode === 'signup' ? 'h-[min(800px,90vh)]' : 'h-[520px]'

  return (
    <AuthPageShell>
      {/* Reveal owns the slow scroll-in transition (1200ms); the resize below is a separate, snappier
          transition on its own element so the two durations don't collide on the same class list. */}
      <Reveal className="flex w-full flex-col">
        <div className={cn('mx-auto w-full motion-safe:transition-[max-width,height] motion-safe:duration-300 motion-safe:ease-in-out', cardWidthClass, cardHeightClass)}>
          <div className="relative h-full overflow-hidden rounded-2xl border border-border bg-surface shadow-modal">
          <AuthCardDecor />
          <div className="relative flex h-full flex-col lg:flex-row">
            {/* Sign in slot — always shown on mobile, where it's the only slot in the row.
                On desktop it collapses to zero width in signup mode (mirroring the sign-up slot below) since
                both slots now share one fixed-size card — whichever mode is active gets the full row width,
                minus the accent sliver on the right. */}
            <div
              className={cn(
                'flex w-full flex-1 flex-col justify-center overflow-x-hidden overflow-y-auto px-6 py-6 sm:px-10 sm:py-7 lg:min-w-0 lg:pr-20 motion-safe:transition-[flex-grow,opacity,transform] motion-safe:duration-500 motion-safe:ease-out',
                mode === 'signup' && 'lg:flex-none lg:basis-0 lg:translate-x-3 lg:opacity-0 lg:px-0',
              )}
              inert={mode === 'signup' ? true : undefined}
            >
              <div className="mx-auto w-full max-w-md">
                <h2 className="text-center text-2xl font-semibold text-foreground">Sign In</h2>
              </div>

              <div className="mx-auto mt-5 w-full max-w-md rounded-md border border-accent-border bg-accent-subtle px-3 py-2.5">
                <p className="text-xs font-medium text-accent">Secure responder access</p>
                <p className="mt-0.5 text-xs leading-relaxed text-foreground-secondary">
                  Your agency administrator provides your account and role permissions.
                </p>
              </div>

              <form className="mx-auto mt-6 flex w-full max-w-md flex-col gap-4" onSubmit={handleLoginSubmit}>
                <Field
                  label="Email"
                  htmlFor="email"
                >
                  <Input
                    id="email"
                    type="email"
                    autoComplete="username"
                    placeholder="name@agency.org"
                    className={SIGN_IN_INPUT_CLASS}
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    required
                  />
                </Field>
                <Field
                  label="Password"
                  htmlFor="password"
                >
                  <Input
                    id="password"
                    type="password"
                    autoComplete="current-password"
                    placeholder="Enter your password"
                    className={SIGN_IN_INPUT_CLASS}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                  />
                </Field>

                {loginError ? (
                  <p
                    role="alert"
                    className="rounded-md border border-danger-border bg-danger-bg px-2 py-2 text-sm text-danger-fg"
                  >
                    {loginError}
                  </p>
                ) : null}

                <Button type="submit" className="mt-1 self-center px-8" disabled={isLoggingIn}>
                  {isLoggingIn ? 'Signing in…' : 'Sign in'}
                </Button>
              </form>
              {IS_RESPONDER_APP ? <ServerAddressSetting /> : null}
            </div>

            {/* Sign up slot — desktop only; agency registration is not part of the mobile field-responder app.
                Same fixed card as sign in, so this slot takes the full row width (minus the accent sliver)
                when active, and collapses to zero width — rather than just being hidden behind an overlay —
                when sign in is active. */}
            <div
              className={cn(
                '@container hidden flex-1 overflow-x-hidden overflow-y-auto py-6 sm:py-7 lg:flex lg:min-w-0 lg:flex-col lg:justify-center motion-safe:transition-[flex-grow,opacity,transform] motion-safe:duration-500 motion-safe:ease-out',
                mode === 'signup' ? 'translate-x-0 px-6 opacity-100 sm:px-10 lg:pl-20' : 'lg:flex-none lg:basis-0 lg:-translate-x-3 lg:px-0 lg:opacity-0',
              )}
              inert={mode === 'signin' ? true : undefined}
            >
              {submitted ? (
                <div className="mx-auto flex w-full max-w-lg flex-col items-center gap-3 py-8 text-center">
                  <CheckCircle2 className="size-10 text-success" />
                  <h2 className="text-base font-semibold text-foreground">Registration submitted</h2>
                  <p className="text-sm leading-relaxed text-foreground-secondary">
                    {agency.agencyName.trim() || 'Your organization'} has been submitted for review. A System Admin
                    will verify your documents and approve or reject the registration — you can sign in once it is
                    approved.
                  </p>
                  <Button className="mt-2 w-full" onClick={() => switchMode('signin')}>
                    Go to sign in
                  </Button>
                </div>
              ) : (
                <div className="mx-auto w-full max-w-lg">
                  <h2 className="mb-5 text-center text-2xl font-semibold text-foreground">{STEP_LABELS[currentStep]} Information</h2>
                  <RegistrationStepper steps={STEP_LABELS} currentStep={currentStep} />

                  <form className="flex flex-col gap-4" onSubmit={handleSignupSubmit}>
                    <div key={currentStep} className="motion-safe:animate-step-in">
                      {currentStep === 0 ? (
                        <OrganizationDetailsStep
                          values={agency}
                          onChange={(patch) => setAgency((prev) => ({ ...prev, ...patch }))}
                        />
                      ) : null}
                      {currentStep === 1 ? (
                        <AddressStep
                          values={agency}
                          onChange={(patch) => setAgency((prev) => ({ ...prev, ...patch }))}
                        />
                      ) : null}
                      {currentStep === 2 ? (
                        <AdminInfoStep
                          values={admin}
                          onChange={(patch) => setAdmin((prev) => ({ ...prev, ...patch }))}
                        />
                      ) : null}
                      {currentStep === 3 ? (
                        <DocumentsStep
                          category={category}
                          files={documents}
                          errors={documentErrors}
                          onDocumentChange={handleDocumentChange}
                          agreedToTerms={agreedToTerms}
                          onTermsChange={setAgreedToTerms}
                        />
                      ) : null}
                    </div>

                    {signupError ? (
                      <p
                        role="alert"
                        className="rounded-md border border-danger-border bg-danger-bg px-2 py-2 text-sm text-danger-fg motion-safe:animate-shake"
                      >
                        {signupError}
                      </p>
                    ) : null}

                    <div className="flex shrink-0 items-center justify-end gap-3 pt-1">
                      {currentStep > 0 ? (
                        <Button type="button" variant="outline" onClick={goToPreviousStep} disabled={isCreatingAgency}>
                          Back
                        </Button>
                      ) : null}
                      {currentStep < STEP_LABELS.length - 1 ? (
                        <Button type="button" onClick={goToNextStep}>
                          Continue
                        </Button>
                      ) : (
                        <Button type="submit" disabled={isCreatingAgency}>
                          {isCreatingAgency ? 'Submitting...' : 'Submit Registration'}
                        </Button>
                      )}
                    </div>
                  </form>
                </div>
              )}
            </div>

            {/* Accent sliver — desktop only, constant width (w-20) in both modes; it never grows. Absolutely
                positioned within the relative row above so it can slide on `left` (an animatable property —
                unlike `order`, which browsers snap instead of tweening) from docked-right in sign in to
                docked-left in sign up, sweeping across and briefly covering the card like a sliding door. The
                two content slots reserve lg:pr-20 / lg:pl-20 so it doesn't overlap them once at rest. */}
            <div
              className={cn(
                'absolute inset-y-0 z-10 hidden w-20 flex-col items-center justify-center overflow-hidden bg-gradient-to-br from-[#1e3a8a] via-[#1e40af] to-[#172554] text-center motion-safe:transition-[left] motion-safe:duration-500 motion-safe:ease-in-out lg:flex',
                mode === 'signup' ? 'left-0' : 'left-[calc(100%-5rem)]',
              )}
            >
              <div
                aria-hidden="true"
                className="absolute inset-0 opacity-20 [background-image:linear-gradient(135deg,rgba(255,255,255,0.12)_1px,transparent_1px),linear-gradient(45deg,rgba(255,255,255,0.06)_1px,transparent_1px)] [background-size:28px_28px]"
              />
              <div
                aria-hidden="true"
                className="absolute inset-0 bg-[radial-gradient(circle_at_50%_35%,rgba(255,255,255,0.18),transparent_62%)]"
              />

              <button
                type="button"
                onClick={() => switchMode(mode === 'signin' ? 'signup' : 'signin')}
                aria-label={mode === 'signin' ? 'Register organization' : 'Sign in'}
                className="pointer-events-auto relative flex h-full w-full flex-col items-center justify-center gap-3 text-foreground-inverse transition-colors hover:bg-white/10"
              >
                <span
                  key={mode}
                  className="relative flex flex-col items-center gap-3 motion-safe:animate-step-in"
                >
                  {mode === 'signin' ? (
                    <Building2 className="size-5 shrink-0" />
                  ) : (
                    <LogIn className="size-5 shrink-0" />
                  )}
                  <span className="text-[11px] font-medium tracking-wide [writing-mode:vertical-rl]">
                    {mode === 'signin' ? 'Register' : 'Sign In'}
                  </span>
                </span>
              </button>
            </div>
          </div>
        </div>
        </div>
      </Reveal>
    </AuthPageShell>
  )
}
