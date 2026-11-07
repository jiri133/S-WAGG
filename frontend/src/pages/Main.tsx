import { solarApi, type Module } from '../api/api'
import { useApi } from '../hooks/useApi'

// Simple grid of the park from GET /api/park. The canvas ParkMap replaces it later.
function groupBy<T>(items: T[], key: (item: T) => string): [string, T[]][] {
  const out = new Map<string, T[]>()
  for (const item of items) {
    const k = key(item)
    out.set(k, [...(out.get(k) ?? []), item])
  }
  return [...out]
}

function Table({ id, modules }: { id: string; modules: Module[] }) {
  return (
    <div title={id} className="grid grid-cols-6 gap-px rounded-sm bg-slate-300 p-px">
      {modules.map((m) => (
        <div key={m.id} title={m.id} className="h-4 w-3 bg-sky-800 hover:bg-amber-400" />
      ))}
    </div>
  )
}

export default function Main() {
  const { data: park, loading, error } = useApi(solarApi.park)

  if (loading) return <p className="text-neutral-500">Se încarcă parcul…</p>
  if (error || !park) return <p className="text-red-700">Backend-ul nu răspunde: {error?.message}</p>

  const blocks = new Set(park.map((m) => m.block)).size
  const inverters = new Set(park.map((m) => m.inverter)).size
  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Parcul fotovoltaic</h1>
        <p className="text-neutral-600" data-testid="park-summary">
          {park.length} module · {blocks} blocuri · {inverters} invertoare
        </p>
      </header>
      {groupBy(park, (m) => `B${m.block}`).map(([block, blockModules]) => (
        <div key={block} className="space-y-2">
          <h2 className="font-semibold">Blocul {block.slice(1)}</h2>
          {groupBy(blockModules, (m) => `${block}-R${m.row}`).map(([row, rowModules]) => (
            <div key={row} className="flex items-center gap-3">
              <span className="w-20 font-mono text-xs text-neutral-500">{row}</span>
              {groupBy(rowModules, (m) => m.table).map(([table, modules]) => (
                <Table key={table} id={table} modules={modules} />
              ))}
            </div>
          ))}
        </div>
      ))}
    </section>
  )
}
