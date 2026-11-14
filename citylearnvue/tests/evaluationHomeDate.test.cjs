const assert = require('node:assert/strict')
const { test } = require('node:test')
const fs = require('node:fs')
const vm = require('node:vm')
const dayjs = require('dayjs')
const compiler = require('vue-template-compiler')
const source = fs.readFileSync(require('node:path').join(__dirname, '../src/components/home/EvaluationHome.vue'), 'utf8')
const script = compiler.parseComponent(source).script.content.replace(/^import .*$/gm, '').replace('export default', 'module.exports =')
const context = { module: { exports: {} },
  dayjs: value => dayjs(value === undefined ? '2026-11-13T09:00:00' : value),
  getHomeEvaluation: async () => ({ ok: true, data: { dataFiles: {} } }),
  resolveDecisionTrace: () => null, HOME_SENSORS: {},
  EnergyDistributionPanel: {}, HaEnergyPeriodSelector: {}, EnergyHomeMoreInfoDialog: {}, HomeRealtimeMoreInfo: {}, HaMdiIcon: {} }
vm.runInNewContext(script, context)
const component = context.module.exports
function instance() {
  return Object.assign(component.data(), { meta: { days: ['2026-01-01'], buildings: ['building_1'] }, energyEpisodes: [], folderData: {}, ...component.methods })
}
test('opening a historical evaluation defaults to today rather than the last recorded day', async () => {
  const state = instance()
  await component.mounted.call(state)
  assert.equal(state.error, '')
  assert.equal(state.day, '2026-11-13')
})
test('switching an energy episode preserves the date the user is viewing', () => {
  const state = instance()
  state.day = '2026-11-13'
  component.watch.energyEpisode.call(state)
  assert.equal(state.day, '2026-11-13')
})
test('calendar allows today even when the evaluation has only January data', () => {
  const state = instance()
  assert.equal(typeof component.computed.calendarDays, 'function')
  const days = component.computed.calendarDays.call(state)
  assert.ok(days.includes('2026-11-13'))
  assert.ok(days.includes('2026-01-01'))
})
