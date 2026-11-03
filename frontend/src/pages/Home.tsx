import { api } from '../api/client'
import { useApi } from '../hooks/useApi'
import type { Health } from '../types'

export default function Home() {
  const { data, loading, error } = useApi(() => api.get<Health>('/health'))

  return (
    <section className="space-y-2">
      <h1 className="text-3xl font-bold tracking-tight">Ready to build</h1>
      <p className="text-neutral-600">
        Backend:{' '}
        {loading ? (
          'checking…'
        ) : error ? (
          <span className="font-medium text-red-700">unreachable</span>
        ) : (
          <span className="font-medium text-green-700">{data?.status}</span>
        )}
      </p>
    </section>
  )
}
