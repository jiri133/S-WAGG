import { NavLink, Outlet } from 'react-router-dom'

const navClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-4 py-2 text-base transition-colors ${
    isActive
      ? 'font-bold text-neutral-900'
      : 'font-normal text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900'
  }`

export default function Layout() {
  return (
    <div className="flex min-h-screen flex-col bg-neutral-50 text-neutral-900 antialiased">
      <header className="flex items-center justify-center border-b border-neutral-200 bg-white px-6 py-3">
        <nav className="flex gap-2" aria-label="Principal">
          <NavLink to="/" end className={navClass}>Parc</NavLink>
          <NavLink to="/plan" className={navClass}>Plan</NavLink>
          <NavLink to="/raport" className={navClass}>Raport</NavLink>
          <NavLink to="/evaluare" className={navClass}>Evaluare</NavLink>
        </nav>
      </header>
      <main className="mx-auto w-full max-w-[76rem] flex-1 px-6 py-8">
        <Outlet />
      </main>
    </div>
  )
}
