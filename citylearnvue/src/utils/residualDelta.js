/**
 * ResMARL 残差 ΔELE 时序序列，供折线图使用。
 */

import {
  buildingLabel,
  filterTraceRows,
  listTraceBuildings,
  listTraceEpisodes
} from './chescaTraceParse'

const BUILDING_COLORS = ['#5470c6', '#91cc75', '#ee6666', '#fac858', '#73c0de']

function toNum(v) {
  if (v == null || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

/**
 * 按 step 对齐多建筑 Δele / base / final。
 * @returns {{
 *   steps: number[],
 *   labels: string[],
 *   series: { name: string, key: string, color: string, data: (number|null)[] }[],
 *   stats: { meanAbs: number|null, maxAbs: number|null, appliedRate: number|null, n: number }
 * }}
 */
export function buildResidualEleSeries(
  rows,
  {
    episode = null,
    buildings = null,
    showBase = false,
    showFinal = false,
    stepRange = null
  } = {}
) {
  let filtered = filterTraceRows(rows || [], { episode })
  if (stepRange && stepRange.length === 2) {
    const [min, max] = stepRange
    filtered = filtered.filter((r) => r.step >= min && r.step <= max)
  }

  const allBuildings = listTraceBuildings(filtered)
  const targetBuildings =
    buildings == null || (Array.isArray(buildings) && buildings.length === 0)
      ? allBuildings
      : buildings.filter((b) => allBuildings.includes(b))

  const sorted = [...filtered].sort((a, b) => (a.step ?? 0) - (b.step ?? 0))
  const steps = [...new Set(sorted.map((r) => r.step).filter((s) => s != null))].sort((a, b) => a - b)
  const hourByStep = new Map()
  sorted.forEach((r) => {
    if (r.step != null && !hourByStep.has(r.step)) {
      hourByStep.set(r.step, r.hour)
    }
  })
  const labels = steps.map((s) => `S${s}\nH${hourByStep.get(s) ?? '-'}`)

  const index = new Map()
  sorted.forEach((r) => {
    index.set(`${r.step}-${r.building}`, r)
  })

  const series = []
  targetBuildings.forEach((b) => {
    const color = BUILDING_COLORS[b % BUILDING_COLORS.length]
    series.push({
      name: `${buildingLabel(b)} · ΔELE`,
      key: `delta-${b}`,
      color,
      lineStyle: { width: 2 },
      data: steps.map((step) => {
        const row = index.get(`${step}-${b}`)
        return row ? toNum(row.residual_delta_ele) : null
      })
    })
    if (showBase) {
      series.push({
        name: `${buildingLabel(b)} · base ELE`,
        key: `base-${b}`,
        color,
        lineStyle: { type: 'dashed', width: 1.5 },
        data: steps.map((step) => {
          const row = index.get(`${step}-${b}`)
          return row ? toNum(row.residual_base_ele) : null
        })
      })
    }
    if (showFinal) {
      series.push({
        name: `${buildingLabel(b)} · final ELE`,
        key: `final-${b}`,
        color,
        lineStyle: { type: 'dotted', width: 1.5 },
        data: steps.map((step) => {
          const row = index.get(`${step}-${b}`)
          return row ? toNum(row.residual_final_ele) : null
        })
      })
    }
  })

  return {
    steps,
    labels,
    series,
    buildings: allBuildings,
    episodes: listTraceEpisodes(rows || []),
    stats: computeDeltaStats(filtered, targetBuildings),
    resmarlHint: detectResmarlHint(filtered)
  }
}

function computeDeltaStats(rows, buildings) {
  const subset = rows.filter((r) => buildings.includes(r.building))
  const deltas = subset.map((r) => toNum(r.residual_delta_ele)).filter((v) => v != null)
  if (!deltas.length) {
    return { meanAbs: null, maxAbs: null, appliedRate: null, n: 0, meanAlpha: null }
  }
  const abs = deltas.map((v) => Math.abs(v))
  const applied = subset.filter((r) => r.residual_applied).length
  const alphas = subset.map((r) => toNum(r.residual_alpha)).filter((v) => v != null)
  return {
    meanAbs: abs.reduce((s, v) => s + v, 0) / abs.length,
    maxAbs: Math.max(...abs),
    appliedRate: subset.length ? applied / subset.length : null,
    n: deltas.length,
    meanAlpha: alphas.length ? alphas.reduce((s, v) => s + v, 0) / alphas.length : null
  }
}

function detectResmarlHint(rows) {
  if (!rows.length) return { enabled: false, alpha: null }
  const enabled = rows.some((r) => r.resmarl_enabled)
  const alphas = rows.map((r) => toNum(r.residual_alpha)).filter((v) => v != null)
  return {
    enabled,
    alpha: alphas.length ? alphas[0] : null
  }
}

export function formatDelta(value, digits = 4) {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toFixed(digits)
}

export function formatPct(value, digits = 1) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

export { buildingLabel, listTraceBuildings, listTraceEpisodes }
