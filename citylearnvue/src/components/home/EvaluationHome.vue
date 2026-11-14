<template>
  <div class="evaluation-home ha-page" v-loading="loading">
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert v-for="(warning, index) in homeWarnings" :key="index" :title="warning" type="warning" :closable="false" />
    <div v-if="energyEpisodes.length > 1" class="evaluation-controls">
      <el-select v-model="energyEpisode" size="small" placeholder="能源 Episode"><el-option v-for="episode in energyEpisodes" :key="episode" :label="`能源 ${episode}`" :value="episode" /></el-select>
    </div>
    <energy-distribution-panel v-if="sensorRows.length" :folder-data="folderData" :external-days="meta.days" :external-buildings="meta.buildings" :external-scope="scope" :external-selected-day="day" hide-scope-select hide-day-controls @node-click="openEnergy" />
    <el-empty v-else :description="meta.days.length ? `${day} 暂无评估数据，可在底栏选择历史日期查看` : '该评估记录未保存能源时序'" :image-size="64" />
    <div class="evaluation-sensors">
      <button v-for="sensor in sensors" :key="sensor.field" type="button" class="evaluation-sensor" @click="activeSensor = sensor; sensorVisible = true">
        <span class="sensor-icon" :style="{ color: sensor.color, background: sensor.bg }"><ha-mdi-icon :name="sensor.icon || 'battery'" :size="20" /></span>
        <span class="sensor-body"><span class="sensor-name">{{ sensor.name }}</span><span class="sensor-value">{{ display(sensor) }} <small>{{ sensor.unit }}</small></span></span>
      </button>
    </div>
    <ha-energy-period-selector class="home-period-selector" v-model="day" :days="calendarDays" :building-options="buildingOptions" :building-index="selectedBuilding" @update:buildingIndex="selectBuilding" />
    <energy-home-more-info-dialog :visible.sync="energyVisible" :focus="energyFocus" :day="day" :scope="scope" :local-points="energyPoints" :pricing-points="[]" />
    <home-realtime-more-info :visible.sync="sensorVisible" :sensor="activeSensor" :samples="sensorSamples" :day="day" timezone="仿真时间" data-mode="simulation" />
  </div>
</template>

<script>
import Papa from 'papaparse'
import dayjs from 'dayjs'
import { getHomeEvaluation } from '@/api/dashboard'
import { listEnergyFlowMeta, buildEnergyFlowSeriesPoints } from '@/utils/energyFlowAggregate'
import { resolveDecisionTrace } from '@/utils/decisionTrace'
import EnergyDistributionPanel from '@/components/dashboard/EnergyDistributionPanel.vue'
import HaEnergyPeriodSelector from './HaEnergyPeriodSelector.vue'
import EnergyHomeMoreInfoDialog from './EnergyHomeMoreInfoDialog.vue'
import HomeRealtimeMoreInfo from './HomeRealtimeMoreInfo.vue'
import HaMdiIcon from './HaMdiIcon.vue'
import { HOME_SENSORS, formatSensorValue } from '@/utils/homeSensors'

export default {
  name: 'EvaluationHome',
  components: { EnergyDistributionPanel, HaEnergyPeriodSelector, EnergyHomeMoreInfoDialog, HomeRealtimeMoreInfo, HaMdiIcon },
  data: () => ({ loading: false, error: '', detail: {}, allFiles: {}, energyEpisode: '', decisionTraces: {},
    scope: 'building_1', day: dayjs().format('YYYY-MM-DD'), energyVisible: false, energyFocus: 'home', energyPoints: [],
    activeSensor: {}, sensorVisible: false,
    sensors: [...Object.values(HOME_SENSORS), { field: 'electrical_storage_soc', name: '电池 SOC', unit: '', digits: 3 }] }),
  computed: {
    calendarDays() { return [...new Set([...this.meta.days, dayjs().format('YYYY-MM-DD')])].sort() },
    homeWarnings() { return (this.detail.artifactWarnings || []).filter(warning => !/决策推演|decision.?trace|chesca.?trace/i.test(warning)) },
    buildingOptions() { return this.meta.buildings.map(building => ({ id: Number((building.match(/\d+/) || ['1'])[0]) - 1 })) },
    energyEpisodes() { return [...new Set(Object.keys(this.allFiles).map(key => (key.match(/_ep\d+$/) || [])[0]).filter(Boolean))].map(value => value.slice(1)).sort((a, b) => Number(a.slice(2)) - Number(b.slice(2))) },
    folderData() { return Object.fromEntries(Object.entries(this.allFiles).filter(([key]) => !/_ep\d+$/.test(key) || key.endsWith('_' + this.energyEpisode))) },
    meta() { return listEnergyFlowMeta(this.folderData) },
    selectedBuilding() { return this.scope === 'community' ? 0 : Number((this.scope.match(/\d+/) || ['1'])[0]) - 1 },
    sensorRows() {
      const prefix = `building_${this.selectedBuilding + 1}`
      const keys = Object.keys(this.folderData).filter(key => new RegExp(`^${prefix}(_ep\\d+)?$`).test(key))
      keys.sort((a, b) => Number((a.match(/_ep(\d+)/) || [0, 0])[1]) - Number((b.match(/_ep(\d+)/) || [0, 0])[1]))
      const rows = this.folderData[keys[keys.length - 1]] || []
      return this.day ? rows.filter(row => String(row.timestamp).startsWith(this.day)) : rows
    },
    current() { return this.sensorRows[this.sensorRows.length - 1] || {} },
    sensorSamples() { return this.sensorRows.map(row => ({ ...row, localTime: row.timestamp, [this.activeSensor.field]: this.sensorValue(row, this.activeSensor.field) })) }
  },
  watch: { energyEpisode() { if (!this.meta.buildings.includes(this.scope)) this.scope = this.meta.buildings[0] || 'building_1' } },
  async mounted() {
    this.loading = true
    try {
      const response = await getHomeEvaluation({ silent: true })
      if (!response.ok || !response.data) throw new Error(response.message || '所选评估记录不可用')
      this.detail = response.data
      const files = {}
      Object.entries(this.detail.dataFiles || {}).forEach(([name, csv]) => {
        files[name.replace(/^exported_data_/, '').replace(/\.csv$/i, '')] = Papa.parse(csv, { header: true, skipEmptyLines: true }).data || []
      })
      this.allFiles = files
      this.energyEpisode = this.energyEpisodes[this.energyEpisodes.length - 1] || ''
      this.scope = this.meta.buildings[0] || 'building_1'
      const key = this.detail.taskId
      const trace = resolveDecisionTrace(this.detail)
      this.decisionTraces = trace ? { [key]: trace } : {}
    } catch (error) { this.error = error.message } finally { this.loading = false }
  },
  methods: {
    selectBuilding(index) { this.scope = `building_${index + 1}` },
    sensorValue(row, field) {
      if (!field) return null
      let value = row[field]
      if (field.startsWith('action_')) {
        const log = this.decisionTraces[this.detail.taskId]
        const steps = log && log.steps || []
        const episodes = [...new Set(steps.map(item => item.episode))]
        const expected = Number(this.energyEpisode.replace('ep', '')) + 1
        const episode = episodes.includes(expected) ? expected : episodes.length === 1 ? episodes[0] : null
        const step = row.source_step != null ? steps.find(item => item.episode === episode && Number(item.step) === Number(row.source_step)) : null
        const building = step && (step.buildings || []).find(item => item.building === this.selectedBuilding)
        const action = building && building.actions && building.actions.final
        if (action) value = action[field.replace('action_', '').replace('_final', '')]
      }
      return value
    },
    display(sensor) { return formatSensorValue(sensor, this.sensorValue(this.current, sensor.field)) },
    openEnergy(payload) {
      this.energyFocus = payload.focus || 'home'
      this.energyPoints = buildEnergyFlowSeriesPoints(this.folderData, [this.day], 'day', this.scope).points
      this.energyVisible = true
    }
  }
}
</script>

<style scoped>
.evaluation-home { max-width: 1000px; margin: 0 auto; padding: 20px 16px 100px; box-sizing: border-box; }
.evaluation-controls { display: flex; gap: 12px; flex-wrap: wrap; margin: 16px 0; }
.evaluation-sensors { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; margin: 24px 0; }
.evaluation-sensor { display: flex; align-items: center; gap: 10px; border: 1px solid var(--divider-color); border-radius: var(--ha-card-border-radius); padding: 10px 12px; min-height: 64px; min-width: 0; text-align: left; background: var(--card-background-color); color: inherit; font: inherit; cursor: pointer; }
.evaluation-sensor:hover { border-color: var(--outline-hover-color); background: rgba(var(--rgb-primary-color), 0.04); }
.sensor-icon { display: flex; align-items: center; justify-content: center; width: 36px; height: 36px; border-radius: 50%; flex-shrink: 0; }
.sensor-body { display: block; min-width: 0; }
.sensor-name { display: block; font-size: 13px; line-height: 1.4; }
.sensor-value { display: block; margin-top: 3px; font-size: 13px; color: var(--secondary-text-color); overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
.sensor-value small { font-size: 12px; }
.home-period-selector >>> .period-center { border-radius: 24px; }
.home-period-selector >>> .period-building-btn { border-radius: 20px; }
.home-period-selector >>> .period-now-btn { border-radius: 20px; }
@media (max-width: 720px) { .evaluation-sensors { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; } }
@media (max-width: 420px) { .evaluation-home { padding: 16px 8px 100px; } .evaluation-sensors { grid-template-columns: 1fr; } }
</style>
