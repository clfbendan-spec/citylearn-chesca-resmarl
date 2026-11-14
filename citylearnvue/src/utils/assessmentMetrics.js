const definitions = [
  { key: 'actual_cost', label: '用电成本', diagnostic: 'positiveCost' },
  { key: 'actual_carbon', label: '碳排放（kgCO₂）', diagnostic: 'carbonEmissions' },
  { key: 'discomfort_hot_proportion', label: '热不适比例', percent: true },
  { key: 'discomfort_cold_proportion', label: '冷不适比例', percent: true },
  { key: 'discomfort_proportion', label: '总不适比例', percent: true }
]

const numeric = value => typeof value === 'number' && Number.isFinite(value) ? value : null

export function assessmentMatrix(baseline) {
  const metrics = baseline && baseline.metrics || {}
  const diagnostics = baseline && baseline.diagnostics || {}
  const currency = diagnostics.units && diagnostics.units.positiveCost
  const official = metrics.officialRows || []
  const actual = diagnostics.buildings || []
  const names = [...new Set([
    ...(metrics.buildings || []).map(item => item.name),
    ...official.filter(item => item.level === 'building').map(item => item.name),
    ...actual.map(item => item.name)
  ].filter(Boolean))]
  const columns = names.length || official.some(item => item.level === 'district') ? [...names, 'District'] : []
  const rows = definitions.map(definition => {
    const result = { ...definition, label: definition.key === 'actual_cost' ? `用电成本（${currency || '未知币种'}）` : definition.label }
    columns.forEach(name => {
      if (definition.diagnostic) {
        if (name === 'District') {
          const values = names.map(building => numeric((actual.find(item => item.name === building) || {})[definition.diagnostic]))
          result[name] = values.length && values.every(value => value !== null) ? numeric(values.reduce((sum, value) => sum + value, 0)) : null
        } else {
          result[name] = numeric((actual.find(item => item.name === name) || {})[definition.diagnostic])
        }
      } else {
        const matches = official.filter(item => item.name === name && item.level === (name === 'District' ? 'district' : 'building') && item.cost_function === definition.key)
        const undefinedMetric = Object.prototype.hasOwnProperty.call(metrics.undefinedMetrics || {}, name + '.' + definition.key)
        result[name] = matches.length === 1 && !undefinedMetric ? numeric(matches[0].value) : null
      }
    })
    return result
  })
  return { columns, rows }
}

export function assessmentOpportunities(baseline) {
  const diagnostics = baseline && baseline.diagnostics || {}
  const currency = diagnostics.units && diagnostics.units.positiveCost || '未知币种'
  const symbols = { USD: '$', CNY: '¥', EUR: '€', GBP: '£', JPY: 'JP¥', HKD: 'HK$', CAD: 'CA$', AUD: 'A$', SGD: 'S$' }
  const moneyUnit = symbols[currency] || currency
  const countNote = '一个时段对应一次数据记录；这些时段不一定都能停止制冷，还需要检查后续室温。'
  const costNote = `单位：${currency}。这是电价不低于本次仿真第 75 百分位时的已发生费用，不是可节省金额；固定电价也可能被计入。`
  const metric = (label, value, unit, explanation, digits = 2) => {
    const valid = numeric(value)
    if (valid === null || valid < 0) return null
    const threshold = 10 ** -digits
    return { label, unit, explanation, value: valid > 0 && valid < threshold
      ? `<${threshold}` : valid.toLocaleString('zh-CN', { maximumFractionDigits: digits }) }
  }
  return (diagnostics.optimizationOpportunities || []).filter(item =>
    ['电池移峰', '冷热负荷', '热水负荷'].includes(item.category)
  ).map(item => {
    const row = { building: item.building, direction: '', metrics: [], emptyText: '数据不足',
      reason: '这条记录缺少相关数值，补齐数据后再评估。' }
    if (item.category === '电池移峰') {
      row.direction = '电池错峰用电'
      if ((item.status || '').includes('未配置')) {
        return { ...row, emptyText: '未配置电池', reason: '当前没有可用电池，暂不能通过充放电调整用电时间。' }
      }
      row.metrics = [metric('最大有效价差', item.maxUnitMargin, `${moneyUnit}/度`,
        `单位：${currency}/kWh。已考虑电池效率，但尚未计算电池实际能充放多少电，不是已实现的节省金额。`, 4)].filter(Boolean)
      if (row.metrics.length) {
        const count = numeric(item.candidateChargeSteps)
        row.reason = item.maxUnitMargin > 0
          ? `${count !== null && count > 0 ? `${count} 个时段有价差条件。` : ''}可研究低价时充电、高价时放电，减少购电费用。`
          : '考虑电池效率后，本次未发现低价充电、高价放电的正价差。'
      }
    } else if (item.category === '冷热负荷') {
      row.direction = '减少空调多余运行'
      const idle = numeric(item.unoccupiedCoolingSteps)
      const cold = numeric(item.occupiedOvercoolSteps)
      if ((idle !== null && idle > 0) || (cold !== null && cold > 0)) {
        row.metrics = [
          metric('无人时仍制冷', idle, '个时段', countNote, 0),
          metric('室温偏低仍制冷', cold, '个时段',
            `有人时，室温低于制冷设定温度，设备仍在制冷。${countNote}`, 0)
        ].filter(Boolean)
        row.reason = idle > 0 && cold > 0
          ? '无人时或室温已经偏低时仍在制冷，可检查是否能减少空调运行。'
          : idle > 0 ? '无人时仍有制冷用电，可检查是否能减少空转，同时保证有人回来时的室温。'
            : '有人时室温已低于制冷设定温度，仍在制冷，可检查是否能适当降低制冷强度。'
      } else if (numeric(item.highPriceExposure) !== null && item.highPriceExposure > 0) {
        row.direction = '调整空调用电时间'
        row.metrics = [metric('较高电价时段已发生费用', item.highPriceExposure, moneyUnit, costNote)]
        row.reason = '若存在低价时段，可研究提前制冷或供暖，但要保证后续室温舒适。'
      } else if (idle === 0 && cold === 0 && item.highPriceExposure === 0) {
        row.metrics = [metric('无人或室温偏低时仍制冷', 0, '个时段', countNote, 0)]
        row.reason = '本次未发现无人制冷、室温偏低仍制冷或较高电价时段费用的明显线索。'
      }
    } else {
      row.direction = '调整热水加热时间'
      if ((item.status || '').includes('未配置')) {
        return { ...row, emptyText: '未配置热水设备', reason: '当前没有有效热水设备，暂不评估热水调度。' }
      }
      row.metrics = [metric('较高电价时段已发生费用', item.highPriceExposure, moneyUnit, costNote)].filter(Boolean)
      if (row.metrics.length) {
        row.reason = item.highPriceExposure > 0
          ? '若存在低价时段且能储存热水，可考虑提前加热，减少高价时段用电。'
          : '本次未发现较高电价时段的热水用电费用，暂不优先调整加热时间。'
      }
    }
    return row
  })
}
