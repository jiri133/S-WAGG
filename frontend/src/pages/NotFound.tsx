import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <section className="mx-auto max-w-md space-y-3 rounded-xl border border-line bg-surface p-8 text-center shadow-sm">
      <p className="font-display text-5xl font-bold tracking-tight text-brand">404</p>
      <p className="text-sm text-ink-soft">Pagina nu există.</p>
      <Link
        to="/"
        className="inline-block rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white transition hover:bg-brand/90"
      >
        Înapoi la parc
      </Link>
    </section>
  )
}
