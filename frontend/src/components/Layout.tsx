import { NavLink, Outlet } from 'react-router-dom'

const navClass = ({ isActive }: { isActive: boolean }) =>
  [
    'relative py-1 text-base transition-colors',
    isActive
      ? 'font-semibold text-ink after:absolute after:inset-x-0 after:-bottom-0.5 after:h-0.5 after:bg-solar'
      : 'text-ink-soft hover:text-ink',
  ].join(' ')

export default function Layout() {
  return (
    <div className="flex min-h-screen flex-col bg-paper text-ink antialiased">
      <header className="border-b border-line bg-surface/60">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
          <span className="flex items-center gap-2 text-sm font-semibold tracking-tight">
            <span aria-hidden className="block h-2.5 w-2.5 rounded-[2px] bg-solar" />
            SolarTriage
          </span>
          <nav
            className="flex flex-wrap items-center gap-x-6 gap-y-2 sm:ml-auto"
            aria-label="Principal"
          >
            <NavLink to="/" end className={navClass}>Parc</NavLink>
            <NavLink to="/plan" className={navClass}>Plan</NavLink>
            <NavLink to="/raport" className={navClass}>Raport</NavLink>
            <NavLink to="/evaluare" className={navClass}>Evaluare</NavLink>
            <NavLink to="/farm-config" className={navClass}>Farm config</NavLink>
            <NavLink to="/simulation" className={navClass}>Farm costs</NavLink>
            <NavLink to="/status" className={navClass}>Status</NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6 sm:py-10">
        <Outlet />
      </main>
    </div>
  )
}
