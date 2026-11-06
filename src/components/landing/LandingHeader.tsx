import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Menu, X } from 'lucide-react'
import { ROUTES } from '../../routes/paths'
import { Button } from '../ui'
import logo from '../../assets/logo.png'

/**
 * Anchor links for the landing page nav.
 *
 * Typed explicitly because the list is currently empty: an empty array literal
 * infers as `any[]`, which fails the build under `noImplicitAny` at each of the
 * three places it is mapped. The type is what the JSX below already assumes.
 */
const NAV_LINKS: Array<{ href: string; label: string }> = []

export function LandingHeader() {
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <header className="sticky top-0 z-50 border-b border-border/60 bg-surface-inverse/85 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link to="/" className="group flex items-center gap-2 text-foreground-inverse">
          <span className="inline-flex size-8 items-center justify-center rounded-md bg-white/95 p-1 transition-transform duration-300 group-hover:-rotate-6 group-hover:scale-105">
            <img src={logo} alt="" className="size-full object-contain" />
          </span>
          <span className="text-lg font-semibold tracking-tight">RescueEye</span>
        </Link>

        <nav className="hidden items-center gap-8 md:flex">
          {NAV_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="group relative py-1 text-sm font-medium text-foreground-inverse/70 transition-colors hover:text-foreground-inverse"
            >
              {link.label}
              <span className="absolute inset-x-0 -bottom-0.5 h-px origin-left scale-x-0 bg-accent transition-transform duration-300 ease-out group-hover:scale-x-100" />
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-2 sm:gap-3">
          <div className="hidden items-center gap-3 md:flex">
            <Link
              to={ROUTES.login}
              className="inline-block transition-transform duration-200 hover:-translate-y-0.5 active:translate-y-0"
            >
              <Button variant="ghost" className="text-foreground-inverse hover:bg-white/10 hover:text-foreground-inverse">
                Login
              </Button>
            </Link>
            <Link
              to={ROUTES.signup}
              className="inline-block transition-transform duration-200 hover:-translate-y-0.5 active:translate-y-0"
            >
              <Button variant="primary">Sign Up</Button>
            </Link>
          </div>

          <button
            type="button"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
            className="rounded-sm p-2 text-foreground-inverse md:hidden"
          >
            {menuOpen ? <X className="size-5" /> : <Menu className="size-5" />}
          </button>
        </div>
      </div>

      {menuOpen ? (
        <div className="border-t border-border/60 bg-surface-inverse px-4 pb-4 md:hidden">
          <nav className="flex flex-col gap-1 pt-3">
            {NAV_LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                onClick={() => setMenuOpen(false)}
                className="rounded-md px-2 py-2 text-sm font-medium text-foreground-inverse/80 hover:bg-white/10 hover:text-foreground-inverse"
              >
                {link.label}
              </a>
            ))}
          </nav>
          <div className="mt-3 flex flex-col gap-2">
            <Link to={ROUTES.login} onClick={() => setMenuOpen(false)}>
              <Button variant="outline" className="w-full border-white/30 text-foreground-inverse hover:bg-white/10">
                Login
              </Button>
            </Link>
            <Link to={ROUTES.signup} onClick={() => setMenuOpen(false)}>
              <Button variant="primary" className="w-full">
                Sign Up
              </Button>
            </Link>
          </div>
        </div>
      ) : null}
    </header>
  )
}
