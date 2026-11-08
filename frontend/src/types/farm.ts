export type Tracking = 'none' | 'single_axis' | 'dual_axis'

export interface FarmConfigPayload {
  name: string
  latitude: number
  longitude: number
  pv_kwp: number
  inverter_ac_mw: number
  tilt_deg: number
  azimuth_deg: number
  tracking: Tracking
  battery_capacity_mwh: number
  battery_p_max_mw: number
  soc_min: number
  soc_max: number
  eta_charge: number
  eta_discharge: number
  asset_scale: number
  export_limit_mw: number | null
  import_limit_mw: number | null
  metered_pv_path: string | null
  timezone: string
  notes: string | null
}

export interface FarmConfigRead extends FarmConfigPayload {
  id: number
  active: boolean
  created_at: string
  updated_at: string
  scaled_pv_kwp: number
  scaled_inverter_ac_mw: number
  scaled_battery_capacity_mwh: number
  scaled_p_max_mw: number
  battery_pct_of_national_peak: number
}

export interface FarmExportResult {
  path: string
  checksum: string
  farm: FarmConfigRead
}

/** Form state: optional limits stay as strings so an empty input means "none". */
export interface FarmDraft {
  name: string
  latitude: number
  longitude: number
  pv_kwp: number
  inverter_ac_mw: number
  tilt_deg: number
  azimuth_deg: number
  tracking: Tracking
  battery_capacity_mwh: number
  battery_p_max_mw: number
  soc_min: number
  soc_max: number
  eta_charge: number
  eta_discharge: number
  asset_scale: number
  export_limit_mw: string
  import_limit_mw: string
  notes: string
}

export const DEFAULT_FARM_DRAFT: FarmDraft = {
  name: 'seed-demo',
  latitude: 44.1598,
  longitude: 28.6348,
  pv_kwp: 6000,
  inverter_ac_mw: 6,
  tilt_deg: 30,
  azimuth_deg: 180,
  tracking: 'none',
  battery_capacity_mwh: 10,
  battery_p_max_mw: 2,
  soc_min: 0.1,
  soc_max: 0.9,
  eta_charge: 0.95,
  eta_discharge: 0.95,
  asset_scale: 1,
  export_limit_mw: '',
  import_limit_mw: '',
  notes: '',
}

export function farmToDraft(farm: FarmConfigRead): FarmDraft {
  return {
    name: farm.name,
    latitude: farm.latitude,
    longitude: farm.longitude,
    pv_kwp: farm.pv_kwp,
    inverter_ac_mw: farm.inverter_ac_mw,
    tilt_deg: farm.tilt_deg,
    azimuth_deg: farm.azimuth_deg,
    tracking: farm.tracking,
    battery_capacity_mwh: farm.battery_capacity_mwh,
    battery_p_max_mw: farm.battery_p_max_mw,
    soc_min: farm.soc_min,
    soc_max: farm.soc_max,
    eta_charge: farm.eta_charge,
    eta_discharge: farm.eta_discharge,
    asset_scale: farm.asset_scale,
    export_limit_mw: farm.export_limit_mw == null ? '' : String(farm.export_limit_mw),
    import_limit_mw: farm.import_limit_mw == null ? '' : String(farm.import_limit_mw),
    notes: farm.notes ?? '',
  }
}

function optionalNumber(value: string): number | null {
  const trimmed = value.trim()
  if (trimmed === '') return null
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : null
}

export function draftToPayload(draft: FarmDraft): FarmConfigPayload {
  return {
    name: draft.name.trim(),
    latitude: draft.latitude,
    longitude: draft.longitude,
    pv_kwp: draft.pv_kwp,
    inverter_ac_mw: draft.inverter_ac_mw,
    tilt_deg: draft.tilt_deg,
    azimuth_deg: draft.azimuth_deg,
    tracking: draft.tracking,
    battery_capacity_mwh: draft.battery_capacity_mwh,
    battery_p_max_mw: draft.battery_p_max_mw,
    soc_min: draft.soc_min,
    soc_max: draft.soc_max,
    eta_charge: draft.eta_charge,
    eta_discharge: draft.eta_discharge,
    asset_scale: draft.asset_scale,
    export_limit_mw: optionalNumber(draft.export_limit_mw),
    import_limit_mw: optionalNumber(draft.import_limit_mw),
    metered_pv_path: null,
    timezone: 'Europe/Bucharest',
    notes: draft.notes.trim() === '' ? null : draft.notes.trim(),
  }
}
