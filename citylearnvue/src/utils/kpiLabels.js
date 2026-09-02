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
  zero_net_energy: '零净能耗达标率'
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
