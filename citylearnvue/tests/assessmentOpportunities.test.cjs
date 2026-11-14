const assert = require('node:assert/strict')
const { test } = require('node:test')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const babel = require('@babel/core')
const source = fs.readFileSync(path.join(__dirname, '../src/utils/assessmentMetrics.js'), 'utf8')
const context = { exports: {} }
vm.runInNewContext(babel.transformSync(source, {
  configFile: false, babelrc: false,
  plugins: ['@babel/plugin-transform-modules-commonjs']
}).code, context)
const format = context.exports.assessmentOpportunities
const baseline = (rows, currency = 'USD') => ({
  diagnostics: { units: { positiveCost: currency }, optimizationOpportunities: rows }
})

test('summarizes numeric opportunities and omits the uncalculated joint-control row', () => {
  const rows = format(baseline([
    { building: 'Building_1', category: '电池移峰', candidateChargeSteps: 147, maxUnitMargin: 0.02872 },
    { building: 'Building_1', category: '冷热负荷', unoccupiedCoolingSteps: 11, occupiedOvercoolSteps: 33, highPriceExposure: 0.7192 },
    { building: 'Building_1', category: '热水负荷', highPriceExposure: 0.8682 },
    { building: '社区', category: '联合调度', status: '待完整环境回放' }
  ]))
  assert.equal(rows.length, 3)
  assert.equal(rows[0].metrics[0].value, '0.0287')
  assert.equal(rows[0].metrics[0].unit, '$/度')
  assert.match(rows[0].reason, /147/)
  assert.equal(rows[1].metrics[0].value, '11')
  assert.equal(rows[1].metrics[1].value, '33')
  assert.equal(rows[1].metrics[0].unit, '个时段')
  assert.equal(rows[2].metrics[0].value, '0.87')
  assert.match(rows[2].metrics[0].label, /已发生/)
  assert.match(rows[2].metrics[0].explanation, /不是.*节省/)
})

test('does not turn missing values into zero or present absent devices as opportunities', () => {
  const rows = format(baseline([
    { building: 'Building_1', category: '电池移峰', status: '未配置有效电池', maxUnitMargin: 0.1, candidateChargeSteps: 5 },
    { building: 'Building_1', category: '冷热负荷', unoccupiedCoolingSteps: null, occupiedOvercoolSteps: null, highPriceExposure: null },
    { building: 'Building_1', category: '热水负荷', highPriceExposure: null }
  ]))
  assert.equal(rows[0].metrics.length, 0)
  assert.match(rows[0].emptyText, /未配置/)
  assert.equal(rows[1].metrics.length, 0)
  assert.equal(rows[2].metrics.length, 0)
  assert.match(rows[1].emptyText, /数据不足/)
})

test('shows zero as no identified opportunity and uses the dataset currency', () => {
  const rows = format(baseline([
    { building: 'Building_1', category: '电池移峰', candidateChargeSteps: 0, maxUnitMargin: 0 },
    { building: 'Building_1', category: '热水负荷', highPriceExposure: 0 }
  ], 'CNY'))
  assert.equal(rows[0].metrics[0].value, '0')
  assert.equal(rows[0].metrics[0].unit, '¥/度')
  assert.match(rows[0].reason, /未发现/)
  assert.equal(rows[1].metrics[0].value, '0')
  assert.match(rows[1].reason, /未发现/)
})

test('keeps high-price HVAC spending when no idle or overcooling signal exists', () => {
  const [row] = format(baseline([
    { building: 'Building_2', category: '冷热负荷', unoccupiedCoolingSteps: 0, occupiedOvercoolSteps: 0, highPriceExposure: 1.25 }
  ], 'EUR'))
  assert.equal(row.metrics.length, 1)
  assert.equal(row.metrics[0].value, '1.25')
  assert.equal(row.metrics[0].unit, '€')
  assert.match(row.metrics[0].label, /已发生/)
})

test('preserves unknown currency and handles absent historical diagnostics', () => {
  assert.equal(format(null).length, 0)
  const [row] = format(baseline([{ category: '热水负荷', highPriceExposure: 2 }], '未知币种'))
  assert.equal(row.metrics[0].unit, '未知币种')
})
