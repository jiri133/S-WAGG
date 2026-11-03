import { useCallback, useEffect, useState } from 'react'

// Minimal data-fetching hook: const { data, loading, error, reload } = useApi(() => api.get('/items'))
export function useApi<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    fn()
      .then(setData)
      .catch(setError)
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(load, [load])

  return { data, loading, error, reload: load }
}
