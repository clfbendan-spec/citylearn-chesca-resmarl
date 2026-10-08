/**
 * 首页 / 模型优选电价曲线：实际电价 + 6/12/24h 预测。
 * 优先仿真导出 pricing，否则回退数据集 pricing.csv（经 weather2026 缓存）。
 */
import { getPricingRowsForDays } from '@/utils/weather2026'

const PRICE_FIELDS = [
  'electricity_pricing',
  'electricity_pricing_predicted_1',
  'electricity_pricing_predicted_2',
  'electricity_pricing_predicted_3'
]

const PRICE_FIELD_ALIASES = {
  electricity_pricing: [
    'electricity_pricing',
    'electricity_pricing-$/kWh',
    '电价(electricity_pricing)-$/kWh'
  ],
  electricity_pricing_predicted_1: [
    'electricity_pricing_predicted_1',
    'electricity_pricing_predicted_1-$/kWh',
    '6小时预测电价(electricity_pricing_predicted_1)-$/kWh'
  ],
  electricity_pricing_predicted_2: [
    'electricity_pricing_predicted_2',
    'electricity_pricing_predicted_2-$/kWh',
    '12小时预测电价(electricity_pricing_predicted_2)-$/kWh'
  ],
  electricity_pricing_predicted_3: [
    'electricity_pricing_predicted_3',
    'electricity_pricing_predicted_3-$/kWh',
    '24小时预测电价(electricity_pricing_predicted_3)-$/kWh'
  ]
}

function toNumber(v) {
  if (v == null || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

function dayKeyFromTs(ts) {
  if (!ts) return null
  const s = String(ts).replace('T', ' ')
  if (s.length >= 10) return s.slice(0, 10)
  return null
}

function pickField(row, aliases) {
  for (const k of aliases) {
    if (row[k] != null && row[k] !== '') {
      const n = toNumber(row[k])
      if (n != null) return n
    }
  }
  return null
}

function normalizePricingRow(row) {
  const day = dayKeyFromTs(row.timestamp || row.time || row.ts)
  let ts = row.timestamp || row.time || row.ts
  if (!ts && day) ts = `${day} 00:00:00`
  const out = { ts: String(ts || '').replace('T', ' ').slice(0, 19) }
  PRICE_FIELDS.forEach((f) => {
    out[f] = pickField(row, PRICE_FIELD_ALIASES[f])
  })
  return out
}

function findPricingTable(folderData) {
  if (!folderData) return null
  const key = Object.keys(folderData).find((k) => {
    const base = k.replace(/_ep\d+$/i, '').toLowerCase()
    return base === 'pricing' || base.startsWith('pricing')
  })
  if (!key) return null
  const rows = folderData[key]
  return Array.isArray(rows) && rows.length ? rows : null
}

function avg(nums) {
  const list = nums.filter((n) => n != null && Number.isFinite(n))
  if (!list.length) return null
  return list.reduce((a, b) => a + b, 0) / list.length
}

function toDailyPoints(hourlyPoints) {
  const byDay = new Map()
  hourlyPoints.forEach((p) => {
    const day = dayKeyFromTs(p.ts)
    if (!day) return
    if (!byDay.has(day)) {
      byDay.set(day, {
        ts: `${day} 12:00:00`,
        buckets: PRICE_FIELDS.reduce((o, f) => {
          o[f] = []
          return o
        }, {})
      })
    }
    const bucket = byDay.get(day)
    PRICE_FIELDS.forEach((f) => {
      if (p[f] != null) bucket.buckets[f].push(Number(p[f]))
    })
  })
  return [...byDay.keys()].sort().map((day) => {
    const b = byDay.get(day)
    const out = { ts: b.ts }
    PRICE_FIELDS.forEach((f) => {
      const v = avg(b.buckets[f])
      out[f] = v == null ? null : Math.round(v * 1000) / 1000
    })
    return out
  })
}

/** 从仿真 folderData 抽电价点 */
export function buildPricingPointsFromFolder(folderData, periodDays, grain = 'hour') {
  const table = findPricingTable(folderData)
  if (!table) return null
  const daySet = new Set(periodDays || [])
  const hourly = table
    .map((row) => normalizePricingRow(row))
    .filter((p) => {
      const d = dayKeyFromTs(p.ts)
      return d && daySet.has(d)
    })
    .sort((a, b) => String(a.ts).localeCompare(String(b.ts)))
  if (!hourly.length) return null
  if (grain === 'day' && (periodDays || []).length > 1) {
    return toDailyPoints(hourly)
  }
  return hourly
}

/** 数据集电价（与首页同源） */
export async function buildPricingPointsFromDataset(periodDays, grain = 'hour') {
  const days = [...(periodDays || [])].sort()
  if (!days.length) return []
  const hourly = await getPricingRowsForDays(days)
  if (grain === 'day' && days.length > 1) {
    return toDailyPoints(hourly)
  }
  return hourly
}

/**
 * @returns {Promise<{ points: Array, grain: 'hour'|'day', source: 'sim'|'dataset'|'none' }>}
 */
export async function buildPricingSeriesPoints(folderData, periodDays, mode = 'day') {
  const grain = mode === 'day' || (periodDays || []).length <= 1 ? 'hour' : 'day'
  const fromSim = buildPricingPointsFromFolder(folderData, periodDays, grain)
  if (fromSim && fromSim.length) {
    return { points: fromSim, grain, source: 'sim' }
  }
  try {
    const fromDs = await buildPricingPointsFromDataset(periodDays, grain)
    if (fromDs && fromDs.length) {
      return { points: fromDs, grain, source: 'dataset' }
    }
  } catch (e) {
    console.warn('加载数据集电价失败', e)
  }
  return { points: [], grain, source: 'none' }
}

export const PRICING_CHART_SERIES = [
  { field: 'electricity_pricing', name: '电价', color: '#43A047' },
  { field: 'electricity_pricing_predicted_1', name: '6小时预测', color: '#81C784' },
  { field: 'electricity_pricing_predicted_2', name: '12小时预测', color: '#FFB74D' },
  { field: 'electricity_pricing_predicted_3', name: '24小时预测', color: '#64B5F6' }
]
