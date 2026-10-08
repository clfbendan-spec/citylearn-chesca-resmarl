import Papa from 'papaparse'
import dayjs from 'dayjs'
import {
  DATASET_HOURS,
  hourIndexIn2026,
  timestampAtHourIndex
} from '@/utils/dataset2026Clock'
import { resolveWeatherCondition } from '@/utils/haIcons'

const WEATHER_URL =
  '/datasets/citylearn_challenge_2026_from_2022/weather.csv'
const CARBON_URL =
  '/datasets/citylearn_challenge_2026_from_2022/carbon_intensity.csv'
const PRICING_URL =
  '/datasets/citylearn_challenge_2026_from_2022/pricing.csv'
const BUILDING_URLS = [
  '/datasets/citylearn_challenge_2026_from_2022/Building_1.csv',
  '/datasets/citylearn_challenge_2026_from_2022/Building_2.csv',
  '/datasets/citylearn_challenge_2026_from_2022/Building_3.csv'
]

export const BUILDING_OPTIONS = [
  { id: 0, label: '建筑 1', short: 'B1' },
  { id: 1, label: '建筑 2', short: 'B2' },
  { id: 2, label: '建筑 3', short: 'B3' }
]

const BUILDING_FIELDS = [
  'indoor_dry_bulb_temperature',
  'indoor_relative_humidity',
  'indoor_dry_bulb_temperature_cooling_set_point',
  'indoor_dry_bulb_temperature_heating_set_point',
  'occupant_count',
  'solar_generation',
  'hvac_mode',
  'heating_demand',
  'cooling_demand'
]

let cachedBaseRows = null
/** @type {Array<Array<Record<string, number|null>>>|null} */
let cachedBuildings = null
let loadingPromise = null

function toNumber(v) {
  if (v == null || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

function emptyBuildingFields() {
  const o = {}
  BUILDING_FIELDS.forEach((f) => {
    o[f] = null
  })
  return o
}

function normalizeWeatherRows(raw) {
  return raw.map((row, i) => ({
    index: i,
    time: timestampAtHourIndex(i).toDate(),
    outdoor_dry_bulb_temperature: toNumber(row.outdoor_dry_bulb_temperature),
    outdoor_relative_humidity: toNumber(row.outdoor_relative_humidity),
    diffuse_solar_irradiance: toNumber(row.diffuse_solar_irradiance),
    direct_solar_irradiance: toNumber(row.direct_solar_irradiance),
    outdoor_dry_bulb_temperature_predicted_1: toNumber(
      row.outdoor_dry_bulb_temperature_predicted_1
    ),
    outdoor_dry_bulb_temperature_predicted_2: toNumber(
      row.outdoor_dry_bulb_temperature_predicted_2
    ),
    outdoor_dry_bulb_temperature_predicted_3: toNumber(
      row.outdoor_dry_bulb_temperature_predicted_3
    ),
    outdoor_relative_humidity_predicted_1: toNumber(
      row.outdoor_relative_humidity_predicted_1
    ),
    outdoor_relative_humidity_predicted_2: toNumber(
      row.outdoor_relative_humidity_predicted_2
    ),
    outdoor_relative_humidity_predicted_3: toNumber(
      row.outdoor_relative_humidity_predicted_3
    ),
    diffuse_solar_irradiance_predicted_1: toNumber(
      row.diffuse_solar_irradiance_predicted_1
    ),
    diffuse_solar_irradiance_predicted_2: toNumber(
      row.diffuse_solar_irradiance_predicted_2
    ),
    diffuse_solar_irradiance_predicted_3: toNumber(
      row.diffuse_solar_irradiance_predicted_3
    ),
    direct_solar_irradiance_predicted_1: toNumber(
      row.direct_solar_irradiance_predicted_1
    ),
    direct_solar_irradiance_predicted_2: toNumber(
      row.direct_solar_irradiance_predicted_2
    ),
    direct_solar_irradiance_predicted_3: toNumber(
      row.direct_solar_irradiance_predicted_3
    ),
    carbon_intensity: null,
    electricity_pricing: null,
    electricity_pricing_predicted_1: null,
    electricity_pricing_predicted_2: null,
    electricity_pricing_predicted_3: null,
    ...emptyBuildingFields()
  }))
}

async function loadCarbonSeries() {
  const res = await fetch(CARBON_URL)
  if (!res.ok) throw new Error(`无法加载碳排放数据 (${res.status})`)
  const text = await res.text()
  const parsed = Papa.parse(text, { header: true, skipEmptyLines: true })
  return parsed.data.map((row) => toNumber(row.carbon_intensity))
}

async function loadPricingSeries() {
  const res = await fetch(PRICING_URL)
  if (!res.ok) throw new Error(`无法加载电价数据 (${res.status})`)
  const text = await res.text()
  const parsed = Papa.parse(text, { header: true, skipEmptyLines: true })
  return parsed.data.map((row) => ({
    electricity_pricing: toNumber(row.electricity_pricing),
    electricity_pricing_predicted_1: toNumber(row.electricity_pricing_predicted_1),
    electricity_pricing_predicted_2: toNumber(row.electricity_pricing_predicted_2),
    electricity_pricing_predicted_3: toNumber(row.electricity_pricing_predicted_3)
  }))
}

async function loadBuildingTables() {
  const texts = await Promise.all(
    BUILDING_URLS.map(async (url) => {
      const res = await fetch(url)
      if (!res.ok) throw new Error(`无法加载建筑数据 (${url}: ${res.status})`)
      return res.text()
    })
  )
  return texts.map((text) => {
    const parsed = Papa.parse(text, { header: true, skipEmptyLines: true })
    return parsed.data.slice(0, DATASET_HOURS).map((row) => {
      const out = {}
      BUILDING_FIELDS.forEach((field) => {
        out[field] = toNumber(row[field])
      })
      return out
    })
  })
}

function withBuilding(baseRow, buildingIndex) {
  if (!baseRow) return null
  const bTable = cachedBuildings && cachedBuildings[buildingIndex]
  const bRow = bTable && bTable[baseRow.index]
  const merged = { ...baseRow }
  BUILDING_FIELDS.forEach((field) => {
    merged[field] = bRow ? bRow[field] : null
  })
  return merged
}

async function ensureDatasetLoaded() {
  if (cachedBaseRows && cachedBuildings) return
  if (loadingPromise) {
    await loadingPromise
    return
  }

  loadingPromise = Promise.all([
    fetch(WEATHER_URL).then((res) => {
      if (!res.ok) throw new Error(`无法加载天气数据 (${res.status})`)
      return res.text()
    }),
    loadCarbonSeries(),
    loadPricingSeries(),
    loadBuildingTables()
  ])
    .then(([weatherText, carbon, pricing, buildings]) => {
      const parsed = Papa.parse(weatherText, {
        header: true,
        skipEmptyLines: true
      })
      if (parsed.errors && parsed.errors.length) {
        console.warn('weather.csv parse warnings', parsed.errors.slice(0, 3))
      }
      const rows = normalizeWeatherRows(parsed.data).slice(0, DATASET_HOURS)
      for (let i = 0; i < rows.length; i += 1) {
        rows[i].carbon_intensity = carbon[i] != null ? carbon[i] : null
        const p = pricing[i]
        if (p) {
          rows[i].electricity_pricing = p.electricity_pricing
          rows[i].electricity_pricing_predicted_1 = p.electricity_pricing_predicted_1
          rows[i].electricity_pricing_predicted_2 = p.electricity_pricing_predicted_2
          rows[i].electricity_pricing_predicted_3 = p.electricity_pricing_predicted_3
        }
      }
      cachedBaseRows = rows
      cachedBuildings = buildings
      return true
    })
    .finally(() => {
      loadingPromise = null
    })

  await loadingPromise
}

/** @deprecated 兼容旧调用；请用 getWeatherSnapshot */
export async function loadWeather2026() {
  await ensureDatasetLoaded()
  return cachedBaseRows
}

function dayExtrema(history) {
  const temps = history
    .map((r) => r.outdoor_dry_bulb_temperature)
    .filter((v) => v != null)
  if (!temps.length) return { high: null, low: null }
  return {
    high: Math.max(...temps),
    low: Math.min(...temps)
  }
}

/**
 * 用预测列拼 HA 风格「小时预报」条（6h / 12h / 24h），不把未来实测画进历史图。
 */
function buildForecastChips(current) {
  if (!current) return []
  const slots = [
    { key: 1, hours: 6, label: '+6h' },
    { key: 2, hours: 12, label: '+12h' },
    { key: 3, hours: 24, label: '+24h' }
  ]
  return slots.map((s) => {
    const temp = current[`outdoor_dry_bulb_temperature_predicted_${s.key}`]
    const humidity = current[`outdoor_relative_humidity_predicted_${s.key}`]
    const direct = current[`direct_solar_irradiance_predicted_${s.key}`]
    const diffuse = current[`diffuse_solar_irradiance_predicted_${s.key}`]
    const fakeRow = {
      time: new Date(current.time.getTime() + s.hours * 3600 * 1000),
      direct_solar_irradiance: direct,
      diffuse_solar_irradiance: diffuse
    }
    return {
      ...s,
      temperature: temp,
      humidity,
      condition: resolveWeatherCondition(fakeRow)
    }
  })
}

/**
 * @param {'day'|'24h'|'all'} range
 * @param {number} buildingIndex 0–2，仅影响建筑侧字段
 */
export async function getWeatherSnapshot(
  now = new Date(),
  range = 'day',
  buildingIndex = 0
) {
  await ensureDatasetLoaded()
  const bIdx = Math.max(0, Math.min(2, Number(buildingIndex) || 0))
  const currentIndex = hourIndexIn2026(now)
  const current = withBuilding(cachedBaseRows[currentIndex], bIdx)

  let startIndex = 0
  if (range === '24h') {
    startIndex = Math.max(0, currentIndex - 23)
  } else if (range === 'day') {
    const hourOfDay = currentIndex % 24
    startIndex = currentIndex - hourOfDay
  }

  const history = cachedBaseRows
    .slice(startIndex, currentIndex + 1)
    .map((row) => withBuilding(row, bIdx))
  const condition = resolveWeatherCondition(current)
  const extrema = dayExtrema(history)
  const forecast = buildForecastChips(current)
  const recentHours = history.slice(-6)

  return {
    currentIndex,
    current,
    history,
    range,
    buildingIndex: bIdx,
    condition,
    extrema,
    forecast,
    recentHours
  }
}

/**
 * 按日期列表取电价序列（含预测列），供模型优选电网详情图使用。
 * @param {string[]} days YYYY-MM-DD
 * @returns {Promise<Array<{ts, electricity_pricing, ...}>>}
 */
export async function getPricingRowsForDays(days = []) {
  await ensureDatasetLoaded()
  const daySet = new Set(days || [])
  if (!daySet.size || !cachedBaseRows) return []
  return cachedBaseRows
    .filter((r) => {
      if (!r || !r.time) return false
      const d = dayjs(r.time).format('YYYY-MM-DD')
      return daySet.has(d)
    })
    .map((r) => ({
      ts: dayjs(r.time).format('YYYY-MM-DD HH:mm:ss'),
      electricity_pricing: r.electricity_pricing,
      electricity_pricing_predicted_1: r.electricity_pricing_predicted_1,
      electricity_pricing_predicted_2: r.electricity_pricing_predicted_2,
      electricity_pricing_predicted_3: r.electricity_pricing_predicted_3
    }))
}
