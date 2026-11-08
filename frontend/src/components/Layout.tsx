import { NavLink, Outlet } from 'react-router-dom'

const navClass = ({ isActive }: { isActive: boolean }) =>
  isActive ? 'font-medium text-neutral-900' : 'text-neutral-500 hover:text-neutral-900'

export default function Layout() {
  return (
    <div className="flex min-h-screen flex-col bg-neutral-50 text-neutral-900 antialiased">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-neutral-200 bg-white px-4 py-3 sm:gap-x-8 sm:px-6">
        <span className="font-semibold">SolarTriage</span>
        <nav className="flex flex-wrap gap-3 text-sm sm:gap-4">
          <NavLink to="/" end className={navClass}>Parc</NavLink>
          <NavLink to="/farm-config" className={navClass}>Farm config</NavLink>
          <NavLink to="/simulation" className={navClass}>Planning</NavLink>
          <NavLink to="/status" className={navClass}>Status</NavLink>
        </nav>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 sm:py-8">
        <Outlet />
      </main>
    </div>
  )
}
