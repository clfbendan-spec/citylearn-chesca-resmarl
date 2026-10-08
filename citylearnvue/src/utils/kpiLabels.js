/** CityLearn exported_kpis.csv 指标与列名中英文映射 */

export const KPI_LABELS_ZH = {
  all_time_peak_average: '全时段峰值平均值',
  annual_normalized_unserved_energy_total: '年度标准化未满足能源总量',
  carbon_emissions_total: '碳排放总量',
  cost_total: '总成本',
  daily_one_minus_load_factor_average: '日平均(1-负荷率)',
  daily_peak_average: '日峰值平均值',
  discomfort_cold_delta_average: '低温不适温差平均值',
  discomfort_cold_delta_maximum: '低温不适温差最大值',
  discomfort_cold_delta_minimum: '低温不适温差最小值',
  discomfort_cold_proportion: '低温不适比例',
  discomfort_hot_delta_average: '高温不适温差平均值',
  discomfort_hot_delta_maximum: '高温不适温差最大值',
  discomfort_hot_delta_minimum: '高温不适温差最小值',
  discomfort_hot_proportion: '高温不适比例',
  discomfort_proportion: '不适比例',
  electricity_consumption_total: '电量消耗总量',
  monthly_one_minus_load_factor_average: '月平均(1-负荷率)',
  one_minus_thermal_resilience_proportion: '热弹性不足比例',
  power_outage_normalized_unserved_energy_total: '停电未满足能源总量',
  ramping_average: '负荷爬坡率',
  zero_net_energy: '零净能耗（归一化）'
}

/**
 * 越高越好的指标。
 *
 * ⚠️ CityLearn 导出的这批 KPI 里**没有**"越高越好"的，一律越低越好：
 *    · 归一化比值（控制 ÷ 无控制基准）：cost_total / carbon_emissions_total /
 *      electricity_consumption_total / **zero_net_energy** —— 小于 1 才说明比无控制更好；
 *    · 本身即"占比/幅度"的：不适比例、热弹性不足比例、停电未满足能源总量、爬坡率、峰值…
 *
 * 历史 bug（2026-10-08 修正）：zero_net_energy 曾被错列在本集合里。
 *   它是 `citylearn/citylearn.py` 里 `_safe_div(zne_c, zne_b)` 的**归一化净取电量**
 *   （CostFunction.zero_net_energy = 净取电量滚动和），越低越好；
 *   错列后模型优选页该行的 👍/👎 正好反了（把"更差"标成"更好"）。
 *   同时旧中文名"零净能耗达标率"带"率"字，也误导成越高越好 ⇒ 改名"零净能耗（归一化）"。
 */
export const KPI_HIGHER_IS_BETTER = new Set([])

/**
 * @param {string} kpiKey
 * @returns {boolean}
 */
export function isKpiHigherBetter(kpiKey) {
  const key = String(kpiKey || '').trim()
  return KPI_HIGHER_IS_BETTER.has(key)
}

/**
 * 评估相对对照的优劣。
 * @returns {'better'|'worse'|'equal'|null}
 */
export function compareKpiAdvantage(kpiKey, evalRaw, controlRaw) {
  const a = parseFloat(evalRaw)
  const b = parseFloat(controlRaw)
  if (!Number.isFinite(a) || !Number.isFinite(b)) {
    return null
  }
  const eps = 1e-9
  if (Math.abs(a - b) <= eps) {
    return 'equal'
  }
  const higherBetter = isKpiHigherBetter(kpiKey)
  if (higherBetter) {
    return a > b ? 'better' : 'worse'
  }
  return a < b ? 'better' : 'worse'
}

const COLUMN_LABELS_ZH = {
  KPI: '指标',
  cost_function: '指标',
  District: '区域'
}

export function formatLabel(key, zhMap, mode = 'zh') {
  const en = key
  const zh = zhMap[key] || columnZhFromPattern(key)
  if (mode === 'en') return en
  if (mode === 'zh-en') {
    if (zh === en) return en
    return `${zh}（${en}）`
  }
  return zh
}

function columnZhFromPattern(key) {
  if (COLUMN_LABELS_ZH[key]) return COLUMN_LABELS_ZH[key]
  const m = /^Building_(\d+)$/.exec(key)
  if (m) return `建筑${m[1]}`
  return key
}

export function formatKpiName(kpiKey, mode = 'zh') {
  return formatLabel(kpiKey, KPI_LABELS_ZH, mode)
}

export function formatColumnName(colKey, mode = 'zh') {
  return formatLabel(colKey, COLUMN_LABELS_ZH, mode)
}
