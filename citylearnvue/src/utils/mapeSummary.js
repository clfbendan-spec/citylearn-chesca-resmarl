/**
 * 从 chesca_trace 行计算 ForecastAgent 预测 MAPE 汇总。
 * MAPE(%) = mean(abs_pct_error_*) × 100
 */

import {
  TRACE_METRICS,
  buildingLabel,
  filterTraceRows,
  listTraceBuildings,
  listTraceEpisodes
} from './chescaTraceParse'

/**
 * @param {number[]} values
 * @returns {{ mape: number|null, count: number }}
 */
export function meanAbsPctError(values) {
  const nums = (values || []).filter((v) => v != null && Number.isFinite(Number(v))).map(Number)
  if (!nums.length) {
    return { mape: null, count: 0 }
  }
  const mean = nums.reduce((s, v) => s + v, 0) / nums.length
  return { mape: mean * 100, count: nums.length }
}

/**
 * 单组筛选后的 MAPE（按变量）。
 * @returns {{ key: string, label: string, mape: number|null, count: number }[]}
 */
export function computeMetricMape(rows) {
  return TRACE_METRICS.map((m) => {
    const { mape, count } = meanAbsPctError(rows.map((r) => r[m.error]))
    return {
      key: m.key,
      label: m.label,
      errorField: m.error,
      mape,
      count
    }
  })
}

/**
 * 按建筑拆分的 MAPE 表行。
 * @returns {{ building: number, buildingLabel: string, metrics: object, overall: number|null }[]}
 */
export function computeBuildingMapeTable(rows) {
  const buildings = listTraceBuildings(rows)
  return buildings.map((b) => {
    const subset = filterTraceRows(rows, { building: b })
    const metrics = {}
    let sum = 0
    let n = 0
    computeMetricMape(subset).forEach((item) => {
      metrics[item.key] = { mape: item.mape, count: item.count, label: item.label }
      if (item.mape != null) {
        sum += item.mape
        n += 1
      }
    })
    return {
      building: b,
      buildingLabel: buildingLabel(b),
      metrics,
      overall: n ? sum / n : null
    }
  })
}

/**
 * 整组仿真的 MAPE 摘要（可选 episode / building 过滤）。
 */
export function buildMapeSummary(rows, { episode = null, building = null } = {}) {
  const filtered = filterTraceRows(rows || [], { episode, building })
  const metrics = computeMetricMape(filtered)
  const withValue = metrics.filter((m) => m.mape != null)
  const overall =
    withValue.length > 0
      ? withValue.reduce((s, m) => s + m.mape, 0) / withValue.length
      : null
  return {
    episode,
    building,
    sampleCount: filtered.length,
    metrics,
    overall,
    byBuilding: computeBuildingMapeTable(filtered),
    episodes: listTraceEpisodes(rows || []),
    buildings: listTraceBuildings(rows || [])
  }
}

export function formatMape(value, digits = 2) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value.toFixed(digits)}%`
}

export { TRACE_METRICS, buildingLabel, listTraceEpisodes, listTraceBuildings }
