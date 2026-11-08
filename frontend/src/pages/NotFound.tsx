import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <section className="space-y-2">
      <h1 className="text-3xl font-bold">404</h1>
      <Link to="/" className="text-brand underline">Înapoi la parc</Link>
    </section>
  )
}
