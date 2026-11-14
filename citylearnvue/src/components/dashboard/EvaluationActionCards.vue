<template>
  <section class="evaluation-action-cards" v-loading="loading">
    <el-button v-if="error" type="text" size="mini" @click="load">{{ error }}，重试</el-button>
    <div class="entities-row">
      <button v-for="key in keys" :key="key" type="button" class="ha-entity-card" @click="open(key)">
        <div class="entity-icon" :style="{ color: sensors[key].color, background: sensors[key].bg }">
          <ha-mdi-icon :name="sensors[key].icon" :size="22" />
        </div>
        <div class="entity-body">
          <div class="entity-name">{{ sensors[key].name }}</div>
          <div class="entity-state">{{ display(key) }}</div>
        </div>
      </button>
    </div>
    <weather-more-info-dialog :visible.sync="dialogVisible" :focus="focus" :building-index="buildingIndex"
      :selected-day="day" :local-samples="windowSamples" :source-name="`${simName} · ${buildingLabel(selectedBuilding)}`" />
  </section>
</template>

<script>
import dayjs from 'dayjs'
import { getDashboardTracePage } from '@/api/dashboard'
import { resolveDecisionTrace } from '@/utils/decisionTrace'
import { summarizeStep } from '@/utils/decisionTraceCompare'
import { HOME_SENSORS, formatSensorValue } from '@/utils/homeSensors'
import HaMdiIcon from '@/components/home/HaMdiIcon.vue'
import WeatherMoreInfoDialog from '@/components/home/WeatherMoreInfoDialog.vue'

export default {
  name: 'EvaluationActionCards',
  components: { HaMdiIcon, WeatherMoreInfoDialog },
  props: {
    folderData: { type: Object, default: () => ({}) },
    taskId: String, simName: String, episode: String, selectedDay: String,
    scope: { type: String, default: 'community' },
    trace: { type: Object, default: null },
    active: Boolean
  },
  data: () => ({
    keys: ['actionDhw', 'actionTmp', 'actionEle'], sensors: HOME_SENSORS,
    focus: 'actionDhw', dialogVisible: false,
    cachedSteps: [], loading: false, error: '', requestVersion: 0
  }),
  computed: {
    buildings() {
      return [...new Set(Object.keys(this.folderData).map(key => (key.match(/^building_\d+/) || [])[0]).filter(Boolean))]
        .sort((a, b) => Number(a.slice(9)) - Number(b.slice(9)))
    },
    selectedBuilding() { return this.scope === 'community' ? this.buildings[0] || '' : this.scope },
    buildingIndex() { return Number((this.selectedBuilding.match(/\d+/) || ['1'])[0]) - 1 },
    rows() {
      const key = Object.keys(this.folderData).find(key => key === this.selectedBuilding || key === `${this.selectedBuilding}_${this.episode}`)
      return (this.folderData[key] || []).filter(row => row.timestamp).slice().sort((a, b) => String(a.timestamp).localeCompare(String(b.timestamp)))
    },
    day() { return this.selectedDay || String((this.rows[this.rows.length - 1] || {}).timestamp || '').slice(0, 10) },
    windowRows() {
      const rows = this.rows.filter(row => String(row.timestamp).startsWith(this.day))
      if (!rows.length) return []
      const end = dayjs(rows[rows.length - 1].timestamp).valueOf()
      const start = Math.min(dayjs(`${this.day}T00:00:00`).valueOf(), end - 24 * 3600000 + 1)
      return this.rows.filter(row => {
        const time = dayjs(row.timestamp).valueOf()
        return time >= start && time <= end
      })
    },
    traceEpisode() {
      const episodes = [...new Set(((this.trace && this.trace.steps) || []).map(step => Number(step.episode)))]
      const expected = Number(String(this.episode || 'ep0').replace('ep', '')) + 1
      return episodes.includes(expected) ? expected : episodes.length === 1 ? episodes[0] : expected
    },
    windowSamples() {
      const steps = new Map([...(this.trace && this.trace.steps || []).filter(step => !step.pending), ...this.cachedSteps]
        .filter(step => Number(step.episode) === this.traceEpisode).map(step => [Number(step.step), step]))
      return this.windowRows.map(row => {
        const step = row.source_step != null && row.source_step !== '' ? steps.get(Number(row.source_step)) : null
        const frame = step && summarizeStep(step, this.trace)
        const building = frame && frame.buildings.find(building => Number(building.id) === this.buildingIndex)
        const sample = { time: row.timestamp }
        this.keys.forEach(key => {
          const dim = key === 'actionDhw' ? 'dhw' : key === 'actionTmp' ? 'tmp' : 'ele'
          const recorded = building && building.dims[frame.dimNames.indexOf(dim)]
          const exported = row[this.sensors[key].field]
          sample[this.sensors[key].field] = recorded != null ? recorded
            : exported != null && exported !== '' && Number.isFinite(Number(exported)) ? Number(exported) : null
        })
        sample.automaticCooling = !!(building && building.automaticCooling)
        return sample
      })
    },
    samples() { return this.windowSamples.filter(row => String(row.time).startsWith(this.day)) },
    loadKey() {
      return [this.active, this.taskId, this.episode, this.day, this.selectedBuilding, this.windowRows.length].join('|')
    }
  },
  watch: {
    loadKey: { immediate: true, handler() { this.load() } }
  },
  beforeDestroy() { this.requestVersion++ },
  methods: {
    buildingLabel(value) { return `建筑 ${(String(value).match(/\d+/) || ['—'])[0]}` },
    display(key) {
      const current = this.samples[this.samples.length - 1]
      if (key === 'actionTmp' && current && current.automaticCooling) return '自动（无动作）'
      return formatSensorValue(this.sensors[key], current && current[this.sensors[key].field])
    },
    open(key) { this.focus = key; this.dialogVisible = true },
    async load() {
      const request = ++this.requestVersion
      this.loading = false
      this.error = ''
      if (!this.active || !this.taskId || !this.trace || !this.windowRows.length) return
      const existing = new Set([...(this.trace.steps || []).filter(step => !step.pending), ...this.cachedSteps]
        .map(step => `${step.episode}:${step.step}`))
      const wanted = new Set(this.windowRows.filter(row => row.source_step != null && row.source_step !== '')
        .map(row => `${this.traceEpisode}:${Number(row.source_step)}`))
      const offsets = new Set()
      ;(this.trace.steps || []).forEach((step, index) => {
        const key = `${step.episode}:${step.step}`
        if (wanted.has(key) && !existing.has(key)) offsets.add(Math.floor(index / 48) * 48)
      })
      if (!offsets.size) return
      this.loading = true
      const loaded = []
      try {
        for (const offset of offsets) {
          const response = await getDashboardTracePage({ taskId: this.taskId, offset, limit: 48 }, { silent: true })
          if (request !== this.requestVersion) return
          if (!response.ok || !response.data) throw new Error('动作加载失败')
          const trace = resolveDecisionTrace(response.data)
          if (trace) loaded.push(...trace.steps)
        }
        if (request === this.requestVersion) this.cachedSteps = [...this.cachedSteps.filter(step => wanted.has(`${step.episode}:${step.step}`)), ...loaded]
      } catch (error) {
        if (request === this.requestVersion) this.error = error.message || '动作加载失败'
      } finally {
        if (request === this.requestVersion) this.loading = false
      }
    }
  }
}
</script>

<style scoped>
.evaluation-action-cards { margin: 16px 0; }
.entities-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.ha-entity-card { display: flex; align-items: center; gap: 12px; min-width: 0; padding: 12px 14px; margin: 0; border: 1px solid var(--divider-color); border-radius: var(--ha-card-border-radius); background: var(--card-background-color); text-align: left; cursor: pointer; font: inherit; color: inherit; }
.ha-entity-card:hover { border-color: var(--outline-hover-color); background: rgba(var(--rgb-primary-color), 0.04); }
.entity-icon { width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.entity-body { min-width: 0; overflow-wrap: anywhere; }
.entity-name { font-size: 14px; font-weight: 500; color: var(--primary-text-color); }
.entity-state { margin-top: 2px; font-size: 13px; color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
@media (max-width: 650px) { .entities-row { grid-template-columns: 1fr; } }
</style>
