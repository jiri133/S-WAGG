import type { ChangeEvent } from 'react'
import type { FarmDraft, Tracking } from '../types/farm'

const NATIONAL_PEAK_MW = 9296

const inputClass =
  'w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 shadow-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'

interface FarmFormProps {
  draft: FarmDraft
  onChange: (patch: Partial<FarmDraft>) => void
  onSave: () => void
  onActivate: () => void
  saving: boolean
  canActivate: boolean
  error: string | null
  message: string | null
}

interface NumberFieldProps {
  label: string
  value: number
  onChange: (value: number) => void
  step?: string
  min?: number
  max?: number
  hint?: string
}

function NumberField({ label, value, onChange, step = 'any', min, max, hint }: NumberFieldProps) {
  return (
    <label className="space-y-1 text-sm">
      <span className="font-medium text-neutral-700">{label}</span>
      <input
        type="number"
        className={inputClass}
        value={Number.isFinite(value) ? value : ''}
        step={step}
        min={min}
        max={max}
        onChange={(event: ChangeEvent<HTMLInputElement>) => onChange(Number(event.target.value))}
      />
      {hint && <span className="block text-xs text-neutral-500">{hint}</span>}
    </label>
  )
}

function TextField({
  label,
  value,
  onChange,
  hint,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  hint?: string
}) {
  return (
    <label className="space-y-1 text-sm">
      <span className="font-medium text-neutral-700">{label}</span>
      <input
        type="text"
        className={inputClass}
        value={value}
        onChange={(event: ChangeEvent<HTMLInputElement>) => onChange(event.target.value)}
      />
      {hint && <span className="block text-xs text-neutral-500">{hint}</span>}
    </label>
  )
}

export default function FarmForm({
  draft,
  onChange,
  onSave,
  onActivate,
  saving,
  canActivate,
  error,
  message,
}: FarmFormProps) {
  const scale = draft.asset_scale > 0 ? draft.asset_scale : 0
  const scaledPv = draft.pv_kwp * scale
  const scaledInverter = draft.inverter_ac_mw * scale
  const scaledBatteryCapacity = draft.battery_capacity_mwh * scale
  const scaledBatteryPower = draft.battery_p_max_mw * scale
  const batteryPct = (100 * scaledBatteryPower) / NATIONAL_PEAK_MW
  const batteryIsNegligible = batteryPct < 1

  return (
    <form
      className="space-y-5 rounded-xl border border-neutral-200 bg-white p-5"
      onSubmit={(event) => {
        event.preventDefault()
        onSave()
      }}
    >
      <div>
        <h2 className="text-lg font-semibold">Farm parameters</h2>
        <p className="text-sm text-neutral-500">
          Every run consumes the exported config. The asset scale multiplies PV, inverter and
          battery together.
        </p>
      </div>

      <TextField
        label="Farm name"
        value={draft.name}
        onChange={(name) => onChange({ name })}
      />

      <div className="grid gap-4 sm:grid-cols-2">
        <NumberField
          label="Latitude"
          value={draft.latitude}
          onChange={(latitude) => onChange({ latitude })}
          step="0.0001"
          min={-90}
          max={90}
        />
        <NumberField
          label="Longitude"
          value={draft.longitude}
          onChange={(longitude) => onChange({ longitude })}
          step="0.0001"
          min={-180}
          max={180}
        />
      </div>

      <fieldset className="space-y-3">
        <legend className="text-sm font-semibold text-neutral-800">PV plant</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <NumberField
            label="Installed capacity (kWp)"
            value={draft.pv_kwp}
            onChange={(pv_kwp) => onChange({ pv_kwp })}
            step="0.1"
            min={0}
          />
          <NumberField
            label="Inverter AC rating (MW)"
            value={draft.inverter_ac_mw}
            onChange={(inverter_ac_mw) => onChange({ inverter_ac_mw })}
            step="0.01"
            min={0}
          />
          <NumberField
            label="Tilt (degrees)"
            value={draft.tilt_deg}
            onChange={(tilt_deg) => onChange({ tilt_deg })}
            step="1"
            min={0}
            max={90}
          />
          <NumberField
            label="Azimuth (degrees)"
            value={draft.azimuth_deg}
            onChange={(azimuth_deg) => onChange({ azimuth_deg })}
            step="1"
            min={0}
            max={360}
            hint="0 = north, 90 = east, 180 = south, 270 = west"
          />
        </div>
        <label className="space-y-1 text-sm">
          <span className="font-medium text-neutral-700">Tracking</span>
          <select
            className={inputClass}
            value={draft.tracking}
            onChange={(event) => onChange({ tracking: event.target.value as Tracking })}
          >
            <option value="none">None</option>
            <option value="single_axis">Single axis</option>
            <option value="dual_axis">Dual axis</option>
          </select>
        </label>
      </fieldset>

      <fieldset className="space-y-3">
        <legend className="text-sm font-semibold text-neutral-800">Battery</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <NumberField
            label="Capacity (MWh)"
            value={draft.battery_capacity_mwh}
            onChange={(battery_capacity_mwh) => onChange({ battery_capacity_mwh })}
            step="0.1"
            min={0}
          />
          <NumberField
            label="Max charge / discharge (MW)"
            value={draft.battery_p_max_mw}
            onChange={(battery_p_max_mw) => onChange({ battery_p_max_mw })}
            step="0.1"
            min={0}
          />
          <NumberField
            label="SoC minimum"
            value={draft.soc_min}
            onChange={(soc_min) => onChange({ soc_min })}
            step="0.01"
            min={0}
            max={1}
            hint="Fraction, e.g. 0.10"
          />
          <NumberField
            label="SoC maximum"
            value={draft.soc_max}
            onChange={(soc_max) => onChange({ soc_max })}
            step="0.01"
            min={0}
            max={1}
            hint="Fraction, e.g. 0.90"
          />
          <NumberField
            label="Charge efficiency"
            value={draft.eta_charge}
            onChange={(eta_charge) => onChange({ eta_charge })}
            step="0.01"
            min={0}
            max={1}
          />
          <NumberField
            label="Discharge efficiency"
            value={draft.eta_discharge}
            onChange={(eta_discharge) => onChange({ eta_discharge })}
            step="0.01"
            min={0}
            max={1}
          />
        </div>
      </fieldset>

      <fieldset className="space-y-3">
        <legend className="text-sm font-semibold text-neutral-800">Grid and scale</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <NumberField
            label="Asset scale s"
            value={draft.asset_scale}
            onChange={(asset_scale) => onChange({ asset_scale })}
            step="0.1"
            min={0}
            hint="1 = IDEA sizes; 500 = national-fleet multiplier"
          />
          <TextField
            label="Export limit (MW)"
            value={draft.export_limit_mw}
            onChange={(export_limit_mw) => onChange({ export_limit_mw })}
            hint="Leave empty for no limit"
          />
          <TextField
            label="Import limit (MW)"
            value={draft.import_limit_mw}
            onChange={(import_limit_mw) => onChange({ import_limit_mw })}
            hint="Leave empty for unlimited"
          />
        </div>
      </fieldset>

      <div className="space-y-2 rounded-lg bg-neutral-50 p-4 text-sm">
        <p className="font-medium text-neutral-800">Scaled system</p>
        <div className="grid gap-1 text-neutral-600 sm:grid-cols-2">
          <span>PV: {scaledPv.toLocaleString(undefined, { maximumFractionDigits: 1 })} kWp</span>
          <span>
            Inverter: {scaledInverter.toLocaleString(undefined, { maximumFractionDigits: 1 })} MW
          </span>
          <span>
            Battery: {scaledBatteryCapacity.toLocaleString(undefined, { maximumFractionDigits: 1 })}{' '}
            MWh
          </span>
          <span>
            Power: {scaledBatteryPower.toLocaleString(undefined, { maximumFractionDigits: 1 })} MW
          </span>
        </div>
        <p className="text-xs text-neutral-500">
          Battery power is {batteryPct.toFixed(3)}% of the national peak load (9,296 MW).
        </p>
        {batteryIsNegligible && (
          <p className="rounded-md bg-amber-50 p-2 text-xs text-amber-800">
            At this scale the battery is under 1% of national peak load; the agent is effectively
            doing price arbitrage. Increase s to make the assets material.
          </p>
        )}
      </div>

      <TextField
        label="Notes"
        value={draft.notes}
        onChange={(notes) => onChange({ notes })}
        hint="Optional provenance note stored with the config"
      />

      {error && (
        <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}
      {message && (
        <p className="rounded-lg bg-green-50 p-3 text-sm text-green-700" role="status">
          {message}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <button
          type="submit"
          disabled={saving}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Save farm'}
        </button>
        <button
          type="button"
          onClick={onActivate}
          disabled={saving || !canActivate}
          className="rounded-lg border border-neutral-300 bg-white px-4 py-2 text-sm font-medium text-neutral-800 hover:bg-neutral-50 disabled:opacity-50"
        >
          Activate &amp; export
        </button>
      </div>
    </form>
  )
}
