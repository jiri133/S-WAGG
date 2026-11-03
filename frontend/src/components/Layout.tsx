import { NavLink, Outlet } from 'react-router-dom'

const navClass = ({ isActive }: { isActive: boolean }) =>
  isActive ? 'font-medium text-neutral-900' : 'text-neutral-500 hover:text-neutral-900'

export default function Layout() {
  return (
    <div className="flex min-h-screen flex-col bg-neutral-50 text-neutral-900 antialiased">
      <header className="flex items-center gap-8 border-b border-neutral-200 bg-white px-6 py-3">
        <span className="font-semibold">Hackathon App</span>
        <nav className="flex gap-4">
          <NavLink to="/" end className={navClass}>Home</NavLink>
        </nav>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">
        <Outlet />
      </main>
    </div>
  )
}
