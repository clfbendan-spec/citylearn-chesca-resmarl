/**
 * 解析 chesca_trace.csv 为结构化行，供可解释可视化使用。
 */

const BOOL_FIELDS = new Set([
  'outage_flag',
  'refine_applied',
  'trigger_reduce_load',
  'trigger_increase_load',
  'resmarl_enabled',
  'residual_applied'
])

const STRING_FIELDS = new Set([
  'control_mode',
  'refine_skip_reason',
  'decision_summary',
  'balance_type',
  'residual_skip_reason'
])

const NUM_FIELDS = new Set([
  'episode',
  'step',
  'hour',
  'building',
  'actual_outdoor_temp',
  'forecast_outdoor_temp',
  'forecast_outdoor_next',
  'abs_pct_error_outdoor_temp',
  'actual_solar',
  'forecast_solar',
  'forecast_solar_next',
  'abs_pct_error_solar',
  'actual_load',
  'forecast_load',
  'forecast_load_next',
  'abs_pct_error_load',
  'actual_dhw',
  'forecast_dhw',
  'forecast_dhw_next',
  'abs_pct_error_dhw',
  'battery_soc',
  'dhw_soc',
  'action_dhw_init',
  'action_ele_init',
  'action_tmp_init',
  'action_dhw_final',
  'action_ele_final',
  'action_tmp_final',
  'net_load_next',
  'net_load_mean',
  'net_load_std',
  'battery_search_cost',
  'tau',
  'B_low',
  'B_high',
  'TMP_max_reduction_percent',
  'residual_alpha',
  'residual_delta_dhw',
  'residual_delta_ele',
  'residual_delta_tmp',
  'residual_raw_delta_dhw',
  'residual_raw_delta_ele',
  'residual_raw_delta_tmp',
  'residual_base_dhw',
  'residual_base_ele',
  'residual_base_tmp',
  'residual_final_dhw',
  'residual_final_ele',
  'residual_final_tmp'
])

export const TRACE_METRICS = [
  {
    key: 'solar',
    label: '光伏发电',
    actual: 'actual_solar',
    forecast: 'forecast_solar',
    error: 'abs_pct_error_solar'
  },
  {
    key: 'load',
    label: '不可调负荷',
    actual: 'actual_load',
    forecast: 'forecast_load',
    error: 'abs_pct_error_load'
  },
  {
    key: 'dhw',
    label: '热水需求',
    actual: 'actual_dhw',
    forecast: 'forecast_dhw',
    error: 'abs_pct_error_dhw'
  },
  {
    key: 'outdoor_temp',
    label: '室外温度',
    actual: 'actual_outdoor_temp',
    forecast: 'forecast_outdoor_temp',
    error: 'abs_pct_error_outdoor_temp'
  }
]

function parseBool(value) {
  if (value === true || value === false) return value
  const s = String(value ?? '').trim().toLowerCase()
  if (!s) return false
  return s === '1' || s === 'true' || s === 'yes'
}

function parseNum(value) {
  if (value === null || value === undefined || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

function normalizeRow(raw) {
  const row = {}
  Object.entries(raw || {}).forEach(([key, value]) => {
    const k = String(key).replace(/^\ufeff/, '').trim()
    const v = value === null || value === undefined ? '' : String(value).trim()
    if (BOOL_FIELDS.has(k)) {
      row[k] = parseBool(v)
    } else if (NUM_FIELDS.has(k)) {
      row[k] = parseNum(v)
    } else if (STRING_FIELDS.has(k)) {
      row[k] = v
    } else {
      row[k] = v
    }
  })
  return row
}

/**
 * @param {string} csvText
 * @returns {object[]}
 */
export function parseChescaTraceCsv(csvText) {
  if (!csvText || !String(csvText).trim()) {
    return []
  }
  const lines = String(csvText).trim().split(/\r?\n/)
  if (lines.length < 2) {
    return []
  }
  const headers = lines[0].split(',').map((h) => h.trim().replace(/^\ufeff/, ''))
  const rows = []
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim()
    if (!line) continue
    const fields = line.split(',')
    const raw = {}
    headers.forEach((header, idx) => {
      raw[header] = idx < fields.length ? fields[idx] : ''
    })
    rows.push(normalizeRow(raw))
  }
  return rows
}

export function listTraceBuildings(rows) {
  const set = new Set()
  rows.forEach((row) => {
    if (row.building != null && !Number.isNaN(row.building)) {
      set.add(row.building)
    }
  })
  return [...set].sort((a, b) => a - b)
}

export function listTraceEpisodes(rows) {
  const set = new Set()
  rows.forEach((row) => {
    if (row.episode != null && !Number.isNaN(row.episode)) {
      set.add(row.episode)
    }
  })
  return [...set].sort((a, b) => a - b)
}

export function filterTraceRows(rows, { building, episode } = {}) {
  return rows.filter((row) => {
    if (building != null && row.building !== building) return false
    if (episode != null && row.episode !== episode) return false
    return true
  })
}

export function buildingLabel(building) {
  const n = Number(building)
  return Number.isFinite(n) ? `建筑 ${n + 1}` : String(building)
}

export const ACTION_SERIES = [
  { key: 'action_dhw_final', label: 'DHW 储热', color: '#5470c6' },
  { key: 'action_ele_final', label: '电池充放电', color: '#91cc75' },
  { key: 'action_tmp_final', label: '冷机', color: '#fac858' }
]

const BUILDING_COLORS = ['#5470c6', '#91cc75', '#ee6666']

/**
 * 按 step 对齐多建筑动作序列，供折线图使用。
 * @returns {{ steps: number[], series: { name: string, data: (number|null)[] }[] }}
 */
export function buildStepActionSeries(rows, buildings, { allBuildings = true, building = 0 } = {}) {
  const sorted = [...rows].sort((a, b) => (a.step ?? 0) - (b.step ?? 0))
  const steps = [...new Set(sorted.map((r) => r.step).filter((s) => s != null))].sort((a, b) => a - b)
  const index = new Map()
  sorted.forEach((r) => {
    index.set(`${r.step}-${r.building}`, r)
  })

  const targetBuildings = allBuildings ? buildings : [building]
  const series = []

  targetBuildings.forEach((b) => {
    ACTION_SERIES.forEach((act, actIdx) => {
      const lineColor = BUILDING_COLORS[b % BUILDING_COLORS.length]
      series.push({
        name: allBuildings ? `${buildingLabel(b)} · ${act.label}` : act.label,
        key: act.key,
        color: allBuildings ? lineColor : act.color,
        lineStyle: allBuildings ? { type: actIdx === 0 ? 'solid' : actIdx === 1 ? 'dashed' : 'dotted' } : undefined,
        data: steps.map((step) => {
          const row = index.get(`${step}-${b}`)
          if (!row) return null
          const v = row[act.key]
          return v == null || Number.isNaN(v) ? null : v
        })
      })
    })
  })

  return { steps, series }
}


export function formatPctError(value) {
  if (value == null || Number.isNaN(value)) return null
  return value * 100
}
