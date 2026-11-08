import { NavLink, Outlet } from 'react-router-dom'

const navClass = ({ isActive }: { isActive: boolean }) =>
  [
    'relative py-1 text-base transition-colors',
    isActive
      ? 'font-semibold text-brand after:absolute after:inset-x-0 after:-bottom-0.5 after:h-0.5 after:bg-brand'
      : 'text-ink-soft hover:text-ink',
  ].join(' ')

export default function Layout() {
  return (
    <div className="relative flex min-h-screen flex-col bg-paper text-ink antialiased">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage:
            'radial-gradient(ellipse at top, #e6f0fb 0%, transparent 55%), radial-gradient(ellipse at bottom right, #e7f5e6 0%, transparent 45%)',
        }}
      />
      <header className="relative border-b border-line bg-surface/70 backdrop-blur">
        <nav
          className="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6"
          aria-label="Principal"
        >
          <NavLink to="/" end className={navClass}>Parc</NavLink>
          <NavLink to="/plan" className={navClass}>Plan</NavLink>
          <NavLink to="/raport" className={navClass}>Raport</NavLink>
          <NavLink to="/evaluare" className={navClass}>Evaluare</NavLink>
          <NavLink to="/farm-config" className={navClass}>Farm config</NavLink>
          <NavLink to="/simulation" className={navClass}>Farm costs</NavLink>
        </nav>
      </header>
      <main className="relative mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6 sm:py-10">
        <Outlet />
      </main>
    </div>
  )
}
