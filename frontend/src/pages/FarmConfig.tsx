import { useCallback, useEffect, useState } from 'react'
import { ApiError, api } from '../api/client'
import FarmForm from '../components/FarmForm'
import FarmMap from '../components/FarmMap'
import {
  DEFAULT_FARM_DRAFT,
  draftToPayload,
  farmToDraft,
  type FarmConfigRead,
  type FarmDraft,
  type FarmExportResult,
} from '../types/farm'

const inputClass =
  'w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 shadow-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'

function formatError(error: unknown): string {
  if (error instanceof ApiError) {
    const body = error.body as { detail?: unknown } | null
    if (body && typeof body === 'object' && 'detail' in body) {
      return JSON.stringify(body.detail)
    }
    return error.message
  }
  return error instanceof Error ? error.message : String(error)
}

export default function FarmConfigPage() {
  const [farms, setFarms] = useState<FarmConfigRead[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [draft, setDraft] = useState<FarmDraft>(DEFAULT_FARM_DRAFT)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const loadFarms = useCallback(async (preferredId?: number | null) => {
    try {
      const data = await api.get<FarmConfigRead[]>('/farms')
      setFarms(data)
      const target =
        preferredId != null
          ? (data.find((farm) => farm.id === preferredId) ?? null)
          : (data.find((farm) => farm.active) ?? data[0] ?? null)
      if (target) {
        setSelectedId(target.id)
        setDraft(farmToDraft(target))
      } else {
        setSelectedId(null)
        setDraft(DEFAULT_FARM_DRAFT)
      }
    } catch (loadError) {
      setError(formatError(loadError))
    }
  }, [])

  useEffect(() => {
    // Fetching the saved farms is the external synchronization this effect exists for.
    // oxlint-disable-next-line react/set-state-in-effect
    void loadFarms()
  }, [loadFarms])

  function handleChange(patch: Partial<FarmDraft>) {
    setDraft((previous) => ({ ...previous, ...patch }))
  }

  async function handleSave() {
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const payload = draftToPayload(draft)
      const saved =
        selectedId == null
          ? await api.post<FarmConfigRead>('/farms', payload)
          : await api.put<FarmConfigRead>(`/farms/${selectedId}`, payload)
      setMessage(
        saved.active
          ? 'Parcul a fost salvat și activat; configurația a fost exportată.'
          : 'Parcul a fost salvat. Activează-l pentru a exporta configurația către pipeline-ul ML.',
      )
      await loadFarms(saved.id)
    } catch (saveError) {
      setError(formatError(saveError))
    } finally {
      setSaving(false)
    }
  }

  async function handleActivate() {
    if (selectedId == null) return
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const result = await api.post<FarmExportResult>(`/farms/${selectedId}/activate`)
      setMessage(
        `Configurația a fost exportată · SHA-256 ${result.checksum.slice(0, 12)}…`,
      )
      await loadFarms(selectedId)
    } catch (activateError) {
      setError(formatError(activateError))
    } finally {
      setSaving(false)
    }
  }

  function handleSelect(value: string) {
    setMessage(null)
    setError(null)
    if (value === '') {
      setSelectedId(null)
      setDraft(DEFAULT_FARM_DRAFT)
      return
    }
    const farm = farms.find((item) => item.id === Number(value))
    if (farm) {
      setSelectedId(farm.id)
      setDraft(farmToDraft(farm))
    }
  }

  function handleNew() {
    setSelectedId(null)
    setDraft(DEFAULT_FARM_DRAFT)
    setMessage(null)
    setError(null)
  }

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-3xl font-bold tracking-tight">Configurare parc</h1>
        <p className="text-neutral-600">
          Alege parcul de referință pe hartă, setează scara activului, apoi activează și
          exportă configurația folosită de pipeline-ul ML.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          <div className="rounded-xl border border-neutral-200 bg-white p-5">
            <div className="flex flex-wrap items-end gap-3">
              <label className="min-w-[12rem] flex-1 space-y-1 text-sm">
                <span className="font-medium text-neutral-700">Parcuri salvate</span>
                <select
                  className={inputClass}
                  value={selectedId ?? ''}
                  onChange={(event) => handleSelect(event.target.value)}
                >
                  <option value="">Parc nou</option>
                  {farms.map((farm) => (
                    <option key={farm.id} value={farm.id}>
                      {farm.name} — {farm.active ? 'activ' : 'inactiv'}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                onClick={handleNew}
                className="rounded-lg border border-neutral-300 bg-white px-4 py-2 text-sm font-medium text-neutral-800 hover:bg-neutral-50"
              >
                Parc nou
              </button>
            </div>
            {farms.length === 0 && (
              <p className="mt-3 text-sm text-neutral-500">
                Nu există parcuri salvate încă. Completează formularul și salvează primul parc.
              </p>
            )}
            {selectedId != null && (
              <p className="mt-3 text-xs text-neutral-500">
                Activarea exportă configurația către pipeline-ul RL.
              </p>
            )}
          </div>

          <FarmMap
            latitude={draft.latitude}
            longitude={draft.longitude}
            onChange={(latitude, longitude) => handleChange({ latitude, longitude })}
          />
          <p className="text-xs text-neutral-500">
            Click pe hartă pentru a plasa parcul de referință; coordonatele pot fi scrise și
            manual.
          </p>
        </div>

        <FarmForm
          draft={draft}
          onChange={handleChange}
          onSave={handleSave}
          onActivate={handleActivate}
          saving={saving}
          canActivate={selectedId !== null}
          error={error}
          message={message}
        />
      </div>
    </section>
  )
}
