import { Link } from 'react-router-dom'
import { Mail, Phone } from 'lucide-react'
import { ROUTES } from '../../routes/paths'
import logo from '../../assets/logo.png'

const PRODUCT_LINKS = [
  { label: 'Capabilities', href: '#capabilities' },
  { label: 'How it works', href: '#workflow' },
  { label: 'Field Responder app', href: '#mobile-app' },
]

export function LandingFooter() {
  return (
    <footer className="border-t border-border bg-surface">
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-10 sm:grid-cols-3">
          <div>
            <div className="flex items-center gap-2 text-foreground">
              <span className="inline-flex size-7 items-center justify-center rounded-md bg-white/95 p-1">
                <img src={logo} alt="" className="size-full object-contain" />
              </span>
              <span className="text-base font-semibold tracking-tight">RescueEye</span>
            </div>
            <p className="mt-3 max-w-xs text-sm leading-relaxed text-foreground-secondary">
              AI-assisted disaster response and rescue management, built to keep humans in
              control of every decision.
            </p>
          </div>

          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-foreground-muted">
              Product
            </p>
            <ul className="mt-3 flex flex-col gap-2">
              {PRODUCT_LINKS.map((link) => (
                <li key={link.href}>
                  <a
                    href={link.href}
                    className="text-sm text-foreground-secondary hover:text-foreground"
                  >
                    {link.label}
                  </a>
                </li>
              ))}
              <li>
                <Link to={ROUTES.login} className="text-sm text-foreground-secondary hover:text-foreground">
                  Login
                </Link>
              </li>
              <li>
                <Link to={ROUTES.signup} className="text-sm text-foreground-secondary hover:text-foreground">
                  Sign Up
                </Link>
              </li>
            </ul>
          </div>

          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-foreground-muted">
              Contact
            </p>
            <ul className="mt-3 flex flex-col gap-2">
              <li className="flex items-center gap-2 text-sm text-foreground-secondary">
                <Mail className="size-4 shrink-0" />
                <a href="mailto:rescueeyedev@gmail.com" className="hover:text-foreground">
                  rescueeyedev@gmail.com
                </a>
              </li>
              <li className="flex items-center gap-2 text-sm text-foreground-secondary">
                <Phone className="size-4 shrink-0" />
                <a href="tel:+639487177945" className="hover:text-foreground">
                  0948 717 7945
                </a>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-10 flex flex-col items-center justify-between gap-3 border-t border-border pt-6 text-xs text-foreground-muted sm:flex-row">
          <p>© {new Date().getFullYear()} RescueEye. All rights reserved.</p>
          <p>Built for rescue command staff and field responders.</p>
        </div>
      </div>
    </footer>
  )
}
