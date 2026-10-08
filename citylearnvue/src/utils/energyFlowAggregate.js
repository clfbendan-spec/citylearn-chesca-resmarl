/**
 * CityLearn → Home Assistant 风格「能源分配」日聚合。
 *
 * 可用导出列与 HA 概念映射：
 *   光伏发电      ← abs(Energy Production from PV-kWh)
 *   电网购入      ← max(Net Electricity Consumption-kWh, 0)
 *   电网外送      ← max(-Net, 0)
 *   电池充电      ← max(Battery (Dis)Charge-kWh, 0)
 *   电池放电      ← max(-Battery (Dis)Charge, 0)
 *   家庭/社区用电 ← 光伏 + 购入 + 放电 − 充电 − 外送
 *   不可调负荷    ← Non-shiftable Load-kWh（或 Electricity Consumption）
 *   其他用电      ← 家庭用电 − 不可调负荷（冷机/热水等未单独导出的部分）
 *
 * 六条电边（HA energy-distribution，四节点两两相连）：
 *   太阳能 → 家庭 / 电网 / 电池
 *   电网   → 家庭 / 电池；电网 ← 太阳能 / 电池
 *   电池   → 家庭 / 电网；电池 ← 太阳能
 *
 * exported_data 无独立 cooling/dhw 电量列，故「其他用电」用能量守恒残差表示。
 */

const PV_KEYS = [
  'Energy Production from PV-kWh',
  'Energy Production from PV',
  'Total Solar Generation-kWh'
]
const NET_KEYS = ['Net Electricity Consumption-kWh', 'Net Electricity Consumption']
const LOAD_KEYS = [
  'Non-shiftable Load Electricity Consumption-kWh',
  'Non-shiftable Load-kWh',
  'Non-shiftable Load'
]
const BAT_KEYS = ['Battery (Dis)Charge-kWh', 'Battery (Dis)Charge']

function pickNumber(row, keys) {
  for (const k of keys) {
    if (row[k] != null && row[k] !== '') {
      const n = Number(row[k])
      if (Number.isFinite(n)) return n
    }
  }
  return 0
}

function dayKeyFromTs(ts) {
  if (!ts) return null
  const s = String(ts)
  if (s.length >= 10) return s.slice(0, 10)
  return null
}

/** 统一为可比较字符串：YYYY-MM-DD HH:mm:ss */
export function normalizeEnergyTimestamp(ts) {
  if (ts == null || ts === '') return ''
  const s = String(ts).trim().replace('T', ' ')
  if (s.length >= 19) return s.slice(0, 19)
  if (s.length >= 16) return `${s.slice(0, 16)}:00`
  if (s.length >= 10) return `${s.slice(0, 10)} 00:00:00`
  return s
}

/**
 * 截断到截止时刻（含），用于首页「不超过当前时间」的按日聚合。
 * @param {Record<string, Array>} folderData
 * @param {string|null} untilTs YYYY-MM-DD HH:mm:ss
 */
export function clipFolderDataUntil(folderData, untilTs) {
  if (!untilTs) return folderData || {}
  const max = normalizeEnergyTimestamp(untilTs)
  const out = {}
  Object.entries(folderData || {}).forEach(([key, rows]) => {
    out[key] = (rows || []).filter((r) => {
      const t = normalizeEnergyTimestamp(r && r.timestamp)
      return t && t <= max
    })
  })
  return out
}

function round3(x) {
  return Math.round(x * 1000) / 1000
}

/**
 * @param {Record<string, Array<Record<string, any>>>} folderData filteredData(sim)
 * @returns {{ days: string[], buildings: string[] }}
 */
export function listEnergyFlowMeta(folderData) {
  const buildings = new Set()
  const days = new Set()
  Object.keys(folderData || {}).forEach((key) => {
    const base = key.replace(/_ep\d+$/i, '').toLowerCase()
    const m = base.match(/^building_(\d+)$/)
    if (m) buildings.add(`building_${m[1]}`)
    const rows = folderData[key] || []
    rows.forEach((r) => {
      const d = dayKeyFromTs(r.timestamp)
      if (d) days.add(d)
    })
  })
  return {
    buildings: [...buildings].sort((a, b) => {
      const na = parseInt(a.match(/\d+/)?.[0] || '0', 10)
      const nb = parseInt(b.match(/\d+/)?.[0] || '0', 10)
      return na - nb
    }),
    days: [...days].sort()
  }
}

function indexByTimestamp(rows) {
  const map = new Map()
  ;(rows || []).forEach((r) => {
    if (r?.timestamp) map.set(String(r.timestamp), r)
  })
  return map
}

/**
 * Home Assistant `computeConsumptionData` 单步分摊。
 * 优先顺序：光伏充电池 → 光伏外送 → 电池外送 → 电网充电池 → 光伏供家 → 电池供家 → 电网供家。
 */
export function computeHaConsumption({ solar, fromGrid, toGrid, toBattery, fromBattery }) {
  let to_grid = Math.max(toGrid || 0, 0)
  let to_battery = Math.max(toBattery || 0, 0)
  let pv = Math.max(solar || 0, 0)
  let from_grid = Math.max(fromGrid || 0, 0)
  let from_battery = Math.max(fromBattery || 0, 0)

  const used_total = from_grid + pv + from_battery - to_grid - to_battery
  let used_total_remaining = Math.max(used_total, 0)
  let grid_to_battery = 0

  const excessGridToBattery = Math.max(
    0,
    Math.min(to_battery, from_grid - used_total_remaining)
  )
  grid_to_battery += excessGridToBattery
  to_battery -= excessGridToBattery
  from_grid -= excessGridToBattery

  const solar_to_battery = Math.min(pv, to_battery)
  to_battery -= solar_to_battery
  pv -= solar_to_battery

  const solar_to_grid = Math.min(pv, to_grid)
  to_grid -= solar_to_grid
  pv -= solar_to_grid

  const battery_to_grid = Math.min(from_battery, to_grid)
  from_battery -= battery_to_grid

  const grid_to_battery_2 = Math.min(from_grid, to_battery)
  grid_to_battery += grid_to_battery_2
  from_grid -= grid_to_battery_2

  const used_solar = Math.min(used_total_remaining, pv)
  used_total_remaining -= used_solar

  const used_battery = Math.min(from_battery, used_total_remaining)
  used_total_remaining -= used_battery

  const used_grid = Math.min(used_total_remaining, from_grid)

  return {
    solarToHome: used_solar,
    solarToGrid: solar_to_grid,
    solarToBattery: solar_to_battery,
    gridToHome: used_grid,
    gridToBattery: grid_to_battery,
    batteryToHome: used_battery,
    batteryToGrid: battery_to_grid,
    home: Math.max(used_total, 0)
  }
}

function emptyPairwise() {
  return {
    solarToHome: 0,
    solarToGrid: 0,
    solarToBattery: 0,
    gridToHome: 0,
    gridToBattery: 0,
    batteryToHome: 0,
    batteryToGrid: 0,
    home: 0
  }
}

function addPairwise(acc, step) {
  Object.keys(acc).forEach((k) => {
    acc[k] += step[k] || 0
  })
}

/**
 * 聚合单日能量流（kWh）。
 * 按小时分摊后再求和，避免「白天光伏 + 夜间充电」被日合计误分到同一条边。
 *
 * @param {object} folderData
 * @param {string} day YYYY-MM-DD
 * @param {'community'|string} scope community 或 building_N
 */
export function aggregateEnergyFlowDay(folderData, day, scope = 'community') {
  const buildingIds =
    scope === 'community'
      ? listEnergyFlowMeta(folderData).buildings
      : [String(scope).toLowerCase()]

  let pv = 0
  let gridIn = 0
  let gridOut = 0
  let batIn = 0
  let batOut = 0
  let nonShiftable = 0
  const pair = emptyPairwise()

  buildingIds.forEach((bId) => {
    const buildingKey = Object.keys(folderData || {}).find((k) => {
      const base = k.replace(/_ep\d+$/i, '').toLowerCase()
      return base === bId
    })
    const batteryKey = Object.keys(folderData || {}).find((k) => {
      const base = k.replace(/_ep\d+$/i, '').toLowerCase()
      return base === `${bId}_battery` || base.startsWith(`${bId}_battery`)
    })

    const bRows = buildingKey ? folderData[buildingKey] : []
    const batRows = batteryKey ? folderData[batteryKey] : []
    const batMap = indexByTimestamp(batRows)

    bRows.forEach((r) => {
      if (dayKeyFromTs(r.timestamp) !== day) return
      const bat = batMap.get(String(r.timestamp))
      const pvH = Math.abs(pickNumber(r, PV_KEYS))
      const net = pickNumber(r, NET_KEYS)
      const gridInH = Math.max(net, 0)
      const gridOutH = Math.max(-net, 0)
      const loadH = Math.max(pickNumber(r, LOAD_KEYS), 0)
      const batVal = bat ? pickNumber(bat, BAT_KEYS) : 0
      const batInH = Math.max(batVal, 0)
      const batOutH = Math.max(-batVal, 0)

      pv += pvH
      gridIn += gridInH
      gridOut += gridOutH
      batIn += batInH
      batOut += batOutH
      nonShiftable += loadH
      addPairwise(
        pair,
        computeHaConsumption({
          solar: pvH,
          fromGrid: gridInH,
          toGrid: gridOutH,
          toBattery: batInH,
          fromBattery: batOutH
        })
      )
    })
  })

  const home = pair.home
  let otherLoad = home - nonShiftable
  if (otherLoad < 0.05) otherLoad = 0
  let loadShown = Math.min(nonShiftable, home)
  if (loadShown + otherLoad > home && home > 0) {
    otherLoad = Math.max(home - loadShown, 0)
  }

  return {
    day,
    scope,
    pv: round3(pv),
    gridIn: round3(gridIn),
    gridOut: round3(gridOut),
    batIn: round3(batIn),
    batOut: round3(batOut),
    home: round3(home),
    nonShiftable: round3(loadShown),
    otherLoad: round3(otherLoad),
    /** 净用电量 = 购入 − 外送（可负） */
    net: round3(gridIn - gridOut),
    solarToHome: round3(pair.solarToHome),
    solarToGrid: round3(pair.solarToGrid),
    solarToBattery: round3(pair.solarToBattery),
    gridToHome: round3(pair.gridToHome),
    gridToBattery: round3(pair.gridToBattery),
    batteryToHome: round3(pair.batteryToHome),
    batteryToGrid: round3(pair.batteryToGrid)
  }
}

const FLOW_NUMERIC_KEYS = [
  'pv', 'gridIn', 'gridOut', 'batIn', 'batOut', 'home',
  'nonShiftable', 'otherLoad', 'net',
  'solarToHome', 'solarToGrid', 'solarToBattery',
  'gridToHome', 'gridToBattery',
  'batteryToHome', 'batteryToGrid'
]

function emptyFlowShell(scope = 'community') {
  const out = { scope }
  FLOW_NUMERIC_KEYS.forEach((k) => { out[k] = 0 })
  return out
}

function addFlows(acc, flow) {
  FLOW_NUMERIC_KEYS.forEach((k) => {
    acc[k] = round3((acc[k] || 0) + (Number(flow[k]) || 0))
  })
  return acc
}

/** ISO 周键：2026-W03 */
export function weekKeyFromDay(day) {
  const d = new Date(`${day}T00:00:00`)
  if (Number.isNaN(d.getTime())) return day
  const tmp = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
  const dayNum = tmp.getUTCDay() || 7
  tmp.setUTCDate(tmp.getUTCDate() + 4 - dayNum)
  const yearStart = new Date(Date.UTC(tmp.getUTCFullYear(), 0, 1))
  const weekNo = Math.ceil((((tmp - yearStart) / 86400000) + 1) / 7)
  return `${tmp.getUTCFullYear()}-W${String(weekNo).padStart(2, '0')}`
}

export function monthKeyFromDay(day) {
  return String(day || '').slice(0, 7)
}

/**
 * @param {'day'|'week'|'month'|'all'} mode
 * @param {string[]} days sorted YYYY-MM-DD
 * @returns {{ key: string, label: string, days: string[] }[]}
 */
export function listEnergyFlowPeriods(days, mode = 'day') {
  const list = [...(days || [])].sort()
  if (!list.length) return []
  if (mode === 'day') {
    return list.map((d) => ({ key: d, label: d, days: [d] }))
  }
  if (mode === 'all') {
    return [{
      key: 'all',
      label: `全部（${list[0]} ~ ${list[list.length - 1]}）`,
      days: list
    }]
  }
  const map = new Map()
  list.forEach((d) => {
    const key = mode === 'week' ? weekKeyFromDay(d) : monthKeyFromDay(d)
    if (!map.has(key)) map.set(key, [])
    map.get(key).push(d)
  })
  return [...map.entries()].map(([key, ds]) => {
    const sorted = [...ds].sort()
    let label = key
    if (mode === 'week') {
      label = `${key}（${sorted[0].slice(5)} ~ ${sorted[sorted.length - 1].slice(5)}）`
    } else if (mode === 'month') {
      const [y, m] = key.split('-')
      label = `${y}年${Number(m)}月（${sorted.length}天）`
    }
    return { key, label, days: sorted }
  })
}

/**
 * 按周期聚合能量流。
 * @param {object} folderData
 * @param {string[]} periodDays
 * @param {string} scope
 */
export function aggregateEnergyFlowPeriod(folderData, periodDays, scope = 'community') {
  const days = [...(periodDays || [])]
  const acc = emptyFlowShell(scope)
  if (!days.length) return acc
  days.forEach((day) => {
    addFlows(acc, aggregateEnergyFlowDay(folderData, day, scope))
  })
  acc.day = days.length === 1 ? days[0] : `${days[0]}~${days[days.length - 1]}`
  acc.periodDays = days
  return acc
}

function hourKeyFromTs(ts) {
  const n = normalizeEnergyTimestamp(ts)
  return n.length >= 13 ? n.slice(0, 13) : n
}

/**
 * 单日逐小时能量点（供详情图）。
 * @returns {Array<Record<string, any>>}
 */
export function buildEnergyFlowHourlyPoints(folderData, day, scope = 'community') {
  const buildingIds =
    scope === 'community'
      ? listEnergyFlowMeta(folderData).buildings
      : [String(scope).toLowerCase()]

  const byHour = new Map()

  buildingIds.forEach((bId) => {
    const buildingKey = Object.keys(folderData || {}).find((k) => {
      const base = k.replace(/_ep\d+$/i, '').toLowerCase()
      return base === bId
    })
    const batteryKey = Object.keys(folderData || {}).find((k) => {
      const base = k.replace(/_ep\d+$/i, '').toLowerCase()
      return base === `${bId}_battery` || base.startsWith(`${bId}_battery`)
    })
    const bRows = buildingKey ? folderData[buildingKey] : []
    const batRows = batteryKey ? folderData[batteryKey] : []
    const batMap = indexByTimestamp(batRows)

    bRows.forEach((r) => {
      if (dayKeyFromTs(r.timestamp) !== day) return
      const hk = hourKeyFromTs(r.timestamp)
      if (!hk) return
      if (!byHour.has(hk)) {
        byHour.set(hk, {
          ts: `${hk}:00:00`,
          pv: 0, gridIn: 0, gridOut: 0, batIn: 0, batOut: 0, home: 0,
          nonShiftable: 0, net: 0,
          solarToHome: 0, solarToGrid: 0, solarToBattery: 0,
          gridToHome: 0, gridToBattery: 0,
          batteryToHome: 0, batteryToGrid: 0
        })
      }
      const pt = byHour.get(hk)
      const bat = batMap.get(String(r.timestamp))
      const pvH = Math.abs(pickNumber(r, PV_KEYS))
      const net = pickNumber(r, NET_KEYS)
      const gridInH = Math.max(net, 0)
      const gridOutH = Math.max(-net, 0)
      const loadH = Math.max(pickNumber(r, LOAD_KEYS), 0)
      const batVal = bat ? pickNumber(bat, BAT_KEYS) : 0
      const batInH = Math.max(batVal, 0)
      const batOutH = Math.max(-batVal, 0)
      const step = computeHaConsumption({
        solar: pvH,
        fromGrid: gridInH,
        toGrid: gridOutH,
        toBattery: batInH,
        fromBattery: batOutH
      })
      pt.pv += pvH
      pt.gridIn += gridInH
      pt.gridOut += gridOutH
      pt.batIn += batInH
      pt.batOut += batOutH
      pt.nonShiftable += loadH
      pt.net += net
      pt.home += step.home
      pt.solarToHome += step.solarToHome
      pt.solarToGrid += step.solarToGrid
      pt.solarToBattery += step.solarToBattery
      pt.gridToHome += step.gridToHome
      pt.gridToBattery += step.gridToBattery
      pt.batteryToHome += step.batteryToHome
      pt.batteryToGrid += step.batteryToGrid
    })
  })

  return [...byHour.keys()].sort().map((hk) => {
    const p = byHour.get(hk)
    const out = { ts: p.ts }
    FLOW_NUMERIC_KEYS.filter((k) => k !== 'otherLoad').forEach((k) => {
      out[k] = round3(p[k] || 0)
    })
    return out
  })
}

/**
 * 多日：每日合计点（周/月/全部详情图用）。
 */
export function buildEnergyFlowDailyPoints(folderData, days, scope = 'community') {
  return (days || []).map((day) => {
    const flow = aggregateEnergyFlowDay(folderData, day, scope)
    return {
      ts: `${day} 12:00:00`,
      ...FLOW_NUMERIC_KEYS.reduce((o, k) => {
        o[k] = flow[k] || 0
        return o
      }, {})
    }
  })
}

/**
 * 按聚合模式生成详情曲线点。
 */
export function buildEnergyFlowSeriesPoints(folderData, periodDays, mode = 'day', scope = 'community') {
  const days = [...(periodDays || [])]
  if (!days.length) return { points: [], grain: 'hour' }
  if (mode === 'day' || days.length === 1) {
    return {
      points: buildEnergyFlowHourlyPoints(folderData, days[0], scope),
      grain: 'hour'
    }
  }
  return {
    points: buildEnergyFlowDailyPoints(folderData, days, scope),
    grain: 'day'
  }
}

/**
 * 转为 ECharts sankey 数据（对齐 HA Energy Overview 六边拓扑）。
 */
export function toSankeyOption(flow) {
  const nodes = [
    { name: '光伏发电', itemStyle: { color: '#ff9800' } },
    { name: '电网购入', itemStyle: { color: '#488fc2' } },
    { name: '电池放电', itemStyle: { color: '#4db6ac' } },
    { name: '家庭', itemStyle: { color: '#8a8a8a' } },
    { name: '电池充电', itemStyle: { color: '#9ccc65' } },
    { name: '电网外送', itemStyle: { color: '#8353d1' } }
  ]

  const links = []
  const push = (source, target, value) => {
    if (value > 0.001) links.push({ source, target, value })
  }

  push('光伏发电', '家庭', flow.solarToHome)
  push('光伏发电', '电网外送', flow.solarToGrid)
  push('光伏发电', '电池充电', flow.solarToBattery)
  push('电网购入', '家庭', flow.gridToHome)
  push('电网购入', '电池充电', flow.gridToBattery)
  push('电池放电', '家庭', flow.batteryToHome)
  push('电池放电', '电网外送', flow.batteryToGrid)

  return { nodes, links }
}
