<template>
  <div class="lovelace-home ha-page">
    <evaluation-home v-if="homeSourceMode === 'evaluation'" :key="selectedEvaluationTaskId" />
    <template v-else>
    <header class="lovelace-header">
      <h1 class="lovelace-title"> </h1>
      <template v-if="isCommunitySource">
        <div class="realtime-source-name">{{ realtimeCommunityName }}</div>
        <p class="realtime-freshness" :class="{ 'is-stale': realtimeSnapshot && realtimeSnapshot.freshness && ['stale', 'future'].includes(realtimeSnapshot.freshness.status) }">{{ realtimeStatus }}</p>
      </template>
    </header>

    <div class="masonry">
      <!-- 能源分配（与模型优选同款，固定 task · 按日聚合至当前时刻） -->
      <article class="home-energy-card">
        <energy-distribution-panel
          v-if="!isCommunitySource && energyDays.length"
          :precomputed-flows="energyFlows"
          :external-days="energyDays"
          :external-buildings="energyBuildings"
          :external-scope="energyScope"
          :external-selected-day="selectedEnergyDay"
          hide-scope-select
          hide-day-controls
          :sim-name="energySimName"
          @node-click="openEnergyNodeMoreInfo"
        />
        <section v-else-if="isCommunitySource && realtimeSnapshot" class="realtime-energy">
          <h2>能源分配</h2>
          <p class="realtime-energy-caption">{{ selectedEnergyDay || '最新日期' }} · {{ realtimeSnapshot.dataMode === 'history' ? '历史测量累计（非实时）' : '已接入实时测量累计' }}（kWh）</p>
          <div class="realtime-energy-values">
            <div v-for="metric in realtimeEnergyMetrics" :key="metric.key">
              <span>{{ metric.label }}</span><strong>{{ realtimeEnergyDisplay(metric.key) }}</strong>
            </div>
          </div>
          <p class="realtime-energy-caption">未接入电网流量、实际光伏电量与电池状态，完整能源流向暂不可用。</p>
        </section>
        <p v-else-if="energyMessage" class="home-loading">{{ energyMessage }}</p>
        <p v-else-if="energyLoading" class="home-loading">正在加载能源分配…</p>
        <p v-if="energyBackfillLoading" class="home-loading energy-backfill-hint">
          当日已就绪，正在加载历史日期…
        </p>
      </article>

      <article v-if="communityTraceRows.length" class="home-trace-card">
        <div class="home-trace-header">
          <div>
            <h2>CHESCA运行时序</h2>
            <p>{{ communityTraceGroupName }} · Building_{{ buildingIndex + 1 }} · 数据集观测值</p>
          </div>
        </div>
        <div ref="communityTraceChart" class="home-trace-chart" />
      </article>

      <!-- HA 风格实体卡：温度 / 湿度 / 电价 -->
      <div class="entities-row entities-row-3">
        <button
          type="button"
          class="ha-entity-card"
          :disabled="!current"
          @click="openMoreInfo('temperature')"
        >
          <div class="entity-icon" :style="iconStyle('temperature')">
            <HaMdiIcon :name="HOME_SENSORS.temperature.icon" :size="22" />
          </div>
          <div class="entity-body">
            <div class="entity-name">{{ HOME_SENSORS.temperature.name }}</div>
            <div class="entity-state">{{ tempDisplay }} °C</div>
          </div>
        </button>

        <button
          type="button"
          class="ha-entity-card"
          :disabled="!current"
          @click="openMoreInfo('humidity')"
        >
          <div class="entity-icon" :style="iconStyle('humidity')">
            <HaMdiIcon :name="HOME_SENSORS.humidity.icon" :size="22" />
          </div>
          <div class="entity-body">
            <div class="entity-name">{{ HOME_SENSORS.humidity.name }}</div>
            <div class="entity-state">{{ humidityDisplay }} %</div>
          </div>
        </button>

        <button
          type="button"
          class="ha-entity-card"
          :disabled="!current"
          @click="openMoreInfo('pricing')"
        >
          <div class="entity-icon" :style="iconStyle('pricing')">
            <HaMdiIcon :name="HOME_SENSORS.pricing.icon" :size="22" />
          </div>
          <div class="entity-body">
            <div class="entity-name">{{ HOME_SENSORS.pricing.name }}</div>
            <div class="entity-state">{{ pricingDisplay }} {{ pricingCurrency }}/kWh</div>
          </div>
        </button>
      </div>

      <!-- 碳排放 / 散射 / 直射 -->
      <div class="entities-row entities-row-3">
        <button
          type="button"
          class="ha-entity-card"
          :disabled="!current"
          @click="openMoreInfo('carbon')"
        >
          <div class="entity-icon" :style="iconStyle('carbon')">
            <HaMdiIcon :name="HOME_SENSORS.carbon.icon" :size="22" />
          </div>
          <div class="entity-body">
            <div class="entity-name">{{ HOME_SENSORS.carbon.name }}</div>
            <div class="entity-state">{{ carbonDisplay }} kgCO₂/kWh</div>
          </div>
        </button>

        <button
          type="button"
          class="ha-entity-card"
          :disabled="!current"
          @click="openMoreInfo('diffuse')"
        >
          <div class="entity-icon" :style="iconStyle('diffuse')">
            <HaMdiIcon :name="HOME_SENSORS.diffuse.icon" :size="22" />
          </div>
          <div class="entity-body">
            <div class="entity-name">{{ HOME_SENSORS.diffuse.name }}</div>
            <div class="entity-state">{{ diffuseDisplay }} W/m²</div>
          </div>
        </button>

        <button
          type="button"
          class="ha-entity-card"
          :disabled="!current"
          @click="openMoreInfo('direct')"
        >
          <div class="entity-icon" :style="iconStyle('direct')">
            <HaMdiIcon :name="HOME_SENSORS.direct.icon" :size="22" />
          </div>
          <div class="entity-body">
            <div class="entity-name">{{ HOME_SENSORS.direct.name }}</div>
            <div class="entity-state">{{ directDisplay }} W/m²</div>
          </div>
        </button>
      </div>

      <!-- 建筑侧：室内温湿度 / 设定点 / 人数 / 光伏 -->
      <div class="section-label-row">
        <span class="section-label">室内与设备</span>
      </div>
      <div
        class="entities-row entities-row-indoor"
        :style="indoorEntitiesGridStyle"
      >
        <button
          v-for="key in buildingSensorKeysVisible"
          :key="key"
          type="button"
          class="ha-entity-card"
          :disabled="!current"
          @click="openMoreInfo(key)"
        >
          <div class="entity-icon" :style="iconStyle(key)">
            <HaMdiIcon :name="HOME_SENSORS[key].icon" :size="22" />
          </div>
          <div class="entity-body">
            <div class="entity-name">{{ HOME_SENSORS[key].name }}</div>
            <div class="entity-state">
              {{ sensorDisplay(key) }} {{ HOME_SENSORS[key].unit }}
            </div>
          </div>
        </button>
      </div>

      <!-- HVAC：模式 / 冷热负荷（数据集观测） -->
      <div class="section-label-row">
        <span class="section-label">暖通状态</span>
      </div>
      <div class="entities-row entities-row-3">
        <button
          v-for="key in HVAC_SENSOR_KEYS"
          :key="key"
          type="button"
          class="ha-entity-card"
          :disabled="!current"
          @click="openMoreInfo(key)"
        >
          <div class="entity-icon" :style="iconStyle(key)">
            <HaMdiIcon :name="hvacIcon(key)" :size="22" />
          </div>
          <div class="entity-body">
            <div class="entity-name">{{ HOME_SENSORS[key].name }}</div>
            <div class="entity-state">
              {{ sensorDisplay(key) }}
              <template v-if="HOME_SENSORS[key].unit">
                {{ HOME_SENSORS[key].unit }}
              </template>
            </div>
          </div>
        </button>
      </div>

      <!-- CHESCA 最终动作：随 B1/B2/B3 切换 -->
      <div class="section-label-row">
        <span class="section-label">控制动作</span>
        <!--<span class="section-hint" v-if="actionSourceLabel">{{ actionSourceLabel }}</span>-->
      </div>
      <div class="entities-row entities-row-3">
        <button
          v-for="key in ACTION_SENSOR_KEYS"
          :key="key"
          type="button"
          class="ha-entity-card"
          :disabled="!actionCurrent"
          @click="openMoreInfo(key)"
        >
          <div class="entity-icon" :style="iconStyle(key)">
            <HaMdiIcon :name="HOME_SENSORS[key].icon" :size="22" />
          </div>
          <div class="entity-body">
            <div class="entity-name">{{ HOME_SENSORS[key].name }}</div>
            <div class="entity-state">{{ actionDisplay(key) }}</div>
          </div>
        </button>
      </div>
      <p v-if="actionMessage" class="home-loading">{{ actionMessage }}</p>

      <p v-if="error" class="home-error">{{ error }}</p>
      <p v-else-if="loading" class="home-loading">正在加载…</p>
    </div>

    <!-- HA Energy Overview 风格：底部固定日期选择 -->
    <ha-energy-period-selector
      v-model="selectedEnergyDay"
      :days="energyDays"
      :building-index.sync="buildingIndex"
      :building-options="homeBuildingOptions"
      :scope-options="realtimeScopeOptions"
      :scope="String(buildingIndex)"
      @change="onPeriodDayChange"
      @building-change="onBuildingChange"
      @update:scope="onRealtimeScopeChange"
    />

    <WeatherMoreInfoDialog
      v-if="!isCommunitySource"
      :visible.sync="dialogVisible"
      :focus.sync="dialogFocus"
      :building-index="buildingIndex"
      :selected-day="selectedEnergyDay"
    />

    <EnergyHomeMoreInfoDialog
      v-if="!isCommunitySource"
      :visible.sync="energyHomeDialogVisible"
      :day="selectedEnergyDay"
      :scope="energyScope"
      :until-ts="energyUntilTs"
      :focus="energyDialogFocus"
    />
    <HomeRealtimeMoreInfo v-if="isCommunitySource" :visible.sync="dialogVisible" :sensor="realtimeDialogSensor" :samples="realtimeSnapshot ? realtimeSnapshot.samples : []" :day="selectedEnergyDay" :community-name="realtimeCommunityName" :timezone="realtimeSnapshot ? realtimeSnapshot.timezone : ''" :data-mode="realtimeSnapshot ? realtimeSnapshot.dataMode : 'realtime'" />
    </template>
  </div>
</template>

<script>
import { themeColor } from '@/utils/theme'

import HaMdiIcon from '@/components/home/HaMdiIcon.vue'
import EvaluationHome from '@/components/home/EvaluationHome.vue'
import HaEnergyPeriodSelector from '@/components/home/HaEnergyPeriodSelector.vue'
import WeatherMoreInfoDialog from '@/components/home/WeatherMoreInfoDialog.vue'
import EnergyHomeMoreInfoDialog from '@/components/home/EnergyHomeMoreInfoDialog.vue'
import EnergyDistributionPanel from '@/components/dashboard/EnergyDistributionPanel.vue'
import * as echarts from 'echarts'
import HomeRealtimeMoreInfo from '@/components/home/HomeRealtimeMoreInfo.vue'
import { getHomeSnapshot, realtimeDayBounds, realtimeFreshness } from '@/utils/homeSource'
import { getWeatherSnapshot, BUILDING_OPTIONS } from '@/utils/weather2026'
import { getActionSnapshot, HOME_ACTION_TASK_ID } from '@/utils/homeActions'
import { loadCommunityHomeTrace } from '@/utils/homeCommunityChesca'
import { loadHomeEnergyProgressive } from '@/utils/homeEnergyFlow'
import { metricsViewNow, todayKeyIn2026 } from '@/utils/dataset2026Clock'
import {
  HOME_SENSORS,
  BUILDING_SENSOR_KEYS,
  HVAC_SENSOR_KEYS,
  ACTION_SENSOR_KEYS,
  formatSensorValue
} from '@/utils/homeSensors'

const BUILDING_STORAGE_KEY = 'citylearn-home-building-index'

export default {
  name: 'HomePage',
  components: {
    EvaluationHome,
    HaMdiIcon,
    HaEnergyPeriodSelector,
    WeatherMoreInfoDialog,
    EnergyHomeMoreInfoDialog,
    EnergyDistributionPanel,
    HomeRealtimeMoreInfo
  },
  data() {
    const saved = Number(localStorage.getItem(BUILDING_STORAGE_KEY))
    return {
      HOME_SENSORS,
      BUILDING_SENSOR_KEYS,
      HVAC_SENSOR_KEYS,
      ACTION_SENSOR_KEYS,
      BUILDING_OPTIONS,
      homeSourceMode: 'loading',
      selectedEvaluationTaskId: '',
      realtimeSnapshot: null,
      realtimeBuildings: [],
      refreshGeneration: 0,
      realtimeEnergyMetrics: [
        { key: 'nonShiftableKwh', label: '不可移峰用电' },
        { key: 'coolingDemandKwh', label: '制冷需求' },
        { key: 'heatingDemandKwh', label: '供热需求' },
        { key: 'dhwDemandKwh', label: '生活热水需求' }
      ],
      buildingIndex: Number.isFinite(saved) && saved >= 0 && saved <= 2 ? saved : 0,
      selectedEnergyDay: '',
      loading: true,
      error: '',
      current: null,
      currentIndex: 0,
      actionCurrent: null,
      actionMessage: '',
      actionGroupName: '',
      communityTraceRows: [],
      communityTraceGroupName: '',
      communityTraceChart: null,
      energyFlows: null,
      energyDays: [],
      energyBuildings: [],
      energyLoading: false,
      energyBackfillLoading: false,
      energyMessage: '',
      energyGroupName: '',
      energyUntilTs: '',
      dialogVisible: false,
      dialogFocus: 'temperature',
      energyHomeDialogVisible: false,
      energyDialogFocus: 'home',
      refreshTimer: null
    }
  },
  computed: {
    isCommunitySource() { return this.homeSourceMode === 'community' || this.homeSourceMode === 'invalid' },
    homeBuildingOptions() { return this.isCommunitySource ? this.realtimeBuildings.map((building, index) => ({ id: index, label: building.name, short: building.name })) : BUILDING_OPTIONS },
    realtimeScopeOptions() { return this.isCommunitySource ? this.homeBuildingOptions.map(option => ({ value: String(option.id), label: option.label })) : null },
    realtimeCommunityName() { return this.realtimeSnapshot && this.realtimeSnapshot.source && this.realtimeSnapshot.source.community ? this.realtimeSnapshot.source.community.name : '社区实时数据源' },
    realtimeStatus() { return this.homeSourceMode === 'invalid' ? this.error : realtimeFreshness(this.realtimeSnapshot) },
    pricingCurrency() { return this.isCommunitySource && this.realtimeSnapshot ? this.realtimeSnapshot.currency || '货币单位' : '$' },
    realtimeDialogSensor() { return { ...(HOME_SENSORS[this.dialogFocus] || {}), ...(this.dialogFocus === 'pricing' ? { unit: `${this.pricingCurrency}/kWh` } : {}) } },
    tempDisplay() {
      return formatSensorValue(
        HOME_SENSORS.temperature,
        this.current && this.current.outdoor_dry_bulb_temperature
      )
    },
    humidityDisplay() {
      return formatSensorValue(
        HOME_SENSORS.humidity,
        this.current && this.current.outdoor_relative_humidity
      )
    },
    pricingDisplay() {
      return formatSensorValue(
        HOME_SENSORS.pricing,
        this.current && this.current.electricity_pricing
      )
    },
    carbonDisplay() {
      return formatSensorValue(
        HOME_SENSORS.carbon,
        this.current && this.current.carbon_intensity
      )
    },
    diffuseDisplay() {
      return formatSensorValue(
        HOME_SENSORS.diffuse,
        this.current && this.current.diffuse_solar_irradiance
      )
    },
    directDisplay() {
      return formatSensorValue(
        HOME_SENSORS.direct,
        this.current && this.current.direct_solar_irradiance
      )
    },
    actionSourceLabel() {
      const shortId = HOME_ACTION_TASK_ID.slice(0, 8)
      return this.actionGroupName
        ? `trace · ${this.actionGroupName} · ${shortId}`
        : `trace · ${shortId}`
    },
    energySimName() {
      const shortId = HOME_ACTION_TASK_ID.slice(0, 8)
      const until = this.energyUntilTs ? ` · 至 ${this.energyUntilTs.slice(0, 16)}` : ''
      // 首页不展示算法名（如 CHESCA），只保留任务时间 + 截止时刻
      let name = this.energyGroupName || ''
      name = name.replace(/^[A-Za-z][\w.-]*\s+(?=\d{4}-\d{2}-\d{2})/, '').trim()
      if (!name) name = shortId
      return `${name}${until}`
    },
    energyScope() {
      if (this.isCommunitySource) return String(this.realtimeSnapshot && this.realtimeSnapshot.buildingId || '')
      return `building_${this.buildingIndex + 1}`
    },
    /** 制冷设定仅制冷模式显示，供暖设定仅供暖模式显示 */
    buildingSensorKeysVisible() {
      const mode = this.current && this.current.hvac_mode
      const m = mode == null || Number.isNaN(Number(mode)) ? null : Math.round(Number(mode))
      return BUILDING_SENSOR_KEYS.filter((key) => {
        if (key === 'coolSetpoint') return m === 1
        if (key === 'heatSetpoint') return m === 2
        return true
      })
    },
    /** 室内与设备：按可见卡数一行列出，避免 3 列折成两行 */
    indoorEntitiesGridStyle() {
      const n = this.buildingSensorKeysVisible.length || 1
      return { gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))` }
    },
    metricsNow() {
      return metricsViewNow(this.selectedEnergyDay, new Date())
    }
  },
  created() {
    this.refresh()
    this.refreshTimer = setInterval(() => this.refresh(), 60 * 1000)
  },
  mounted() {
    window.addEventListener('resize', this.resizeCommunityTraceChart)
  },
  beforeDestroy() {
    if (this.refreshTimer) clearInterval(this.refreshTimer)
    window.removeEventListener('resize', this.resizeCommunityTraceChart)
    if (this.communityTraceChart) this.communityTraceChart.dispose()
  },
  watch: {
    buildingIndex() { this.$nextTick(this.drawCommunityTraceChart) },
    communityTraceRows() { this.$nextTick(this.drawCommunityTraceChart) }
  },
  methods: {
    iconStyle(key) {
      const s = HOME_SENSORS[key]
      return { color: s.color, background: s.bg }
    },
    sensorDisplay(key) {
      const s = HOME_SENSORS[key]
      return formatSensorValue(s, this.current && this.current[s.field])
    },
    hvacIcon(key) {
      if (key !== 'hvacMode') return HOME_SENSORS[key].icon
      const mode = this.current && this.current.hvac_mode
      if (mode == null || Number.isNaN(Number(mode))) return 'airConditioner'
      const m = Math.round(Number(mode))
      if (m === 1) return 'snowflake'
      if (m === 2) return 'fire'
      return 'airConditioner'
    },
    actionDisplay(key) {
      const s = HOME_SENSORS[key]
      return formatSensorValue(s, this.actionCurrent && this.actionCurrent[s.field])
    },
    selectBuilding(id) {
      if (this.buildingIndex === id) return
      this.buildingIndex = id
      this.onBuildingChange(id)
    },
    onBuildingChange(id) {
      localStorage.setItem(BUILDING_STORAGE_KEY, String(id))
      this.refreshMetrics()
    },
    onRealtimeScopeChange(value) { this.buildingIndex = Number(value); this.onBuildingChange(this.buildingIndex) },
    realtimeEnergyDisplay(key) {
      const value = this.realtimeSnapshot && this.realtimeSnapshot.energy && this.realtimeSnapshot.energy[key]
      return value == null ? '—' : Number(value).toFixed(3)
    },
    async refreshRealtime(generation, initial) {
      const building = this.realtimeBuildings[this.buildingIndex]
      const params = { ...realtimeDayBounds(this.selectedEnergyDay) }
      if (building) params.buildingId = building.id
      const snapshot = initial || await getHomeSnapshot(params)
      if (generation !== this.refreshGeneration) return
      this.homeSourceMode = snapshot.mode
      this.realtimeSnapshot = snapshot
      this.realtimeBuildings = snapshot.buildings || []
      if (this.buildingIndex >= this.realtimeBuildings.length) this.buildingIndex = 0
      this.energyDays = snapshot.days || []
      if (!this.energyDays.includes(this.selectedEnergyDay)) this.selectedEnergyDay = this.energyDays[this.energyDays.length - 1] || ''
      this.current = snapshot.current || null
      this.currentIndex = (snapshot.samples || []).length - 1
      this.energyFlows = null; this.energyBuildings = []; this.energyMessage = ''
      this.actionCurrent = null; this.actionGroupName = ''; this.actionMessage = '未接入实时控制动作'
      if (snapshot.mode === 'invalid') {
        this.communityTraceRows = []; this.communityTraceGroupName = ''
        this.error = snapshot.source.message || '首页数据源不可用'
        this.actionMessage = ''
        this.dialogVisible = false; this.energyHomeDialogVisible = false
        this.energyLoading = false; this.energyBackfillLoading = false; this.loading = false
        return
      }
      try {
        const action = await getActionSnapshot(this.metricsNow, 'day', this.buildingIndex, Boolean(this.communityTraceRows.length))
        if (generation === this.refreshGeneration) {
          this.actionCurrent = action.current
          this.actionGroupName = action.groupName || ''
          this.actionMessage = action.message || ''
        }
      } catch (error) {
        if (generation === this.refreshGeneration) this.actionMessage = error.message || '动作 trace 加载失败'
      }
      this.error = snapshot.mode === 'invalid' ? snapshot.source.message : ''
      this.energyLoading = false; this.energyBackfillLoading = false; this.loading = false
    },
    syncSelectedDay(days) {
      const list = days || []
      if (!list.length) {
        this.selectedEnergyDay = ''
        return
      }
      if (this.selectedEnergyDay && list.includes(this.selectedEnergyDay)) return
      const today = todayKeyIn2026(new Date())
      this.selectedEnergyDay = list.includes(today) ? today : list[list.length - 1]
    },
    onPeriodDayChange() {
      this.refreshMetrics()
    },
    applyEnergyPayload(energy) {
      this.energyFlows = energy.flows || null
      this.energyDays = energy.days || []
      this.energyBuildings = energy.buildings || []
      this.energyMessage = energy.message || ''
      this.energyGroupName = energy.groupName || ''
      this.energyUntilTs = energy.untilTs || ''
      this.syncSelectedDay(this.energyDays)
    },
    async refreshMetrics() {
      const generation = this.refreshGeneration
      if (this.isCommunitySource) {
        const generation = ++this.refreshGeneration
        this.loading = true
        try { await this.refreshRealtime(generation) } catch (error) {
          if (generation !== this.refreshGeneration) return
          this.error = error.message || '实时测量加载失败'; this.current = null; this.realtimeSnapshot = null
        } finally { if (generation === this.refreshGeneration) this.loading = false }
        return
      }
      const viewNow = this.metricsNow
      try {
        const snap = await getWeatherSnapshot(viewNow, 'day', this.buildingIndex)
        if (generation !== this.refreshGeneration || this.homeSourceMode !== 'default') return
        this.current = snap.current
        this.currentIndex = snap.currentIndex
        this.error = ''
      } catch (e) {
        if (generation !== this.refreshGeneration || this.homeSourceMode !== 'default') return
        this.error = e.message || '加载失败'
        this.current = null
      }
      try {
        const act = await getActionSnapshot(viewNow, 'day', this.buildingIndex, Boolean(this.communityTraceRows.length))
        if (generation !== this.refreshGeneration || this.homeSourceMode !== 'default') return
        this.actionCurrent = act.current
        this.actionMessage = act.message || ''
        this.actionGroupName = act.groupName || ''
      } catch (e) {
        if (generation !== this.refreshGeneration || this.homeSourceMode !== 'default') return
        this.actionCurrent = null
        this.actionMessage = e.message || '动作 trace 加载失败'
        this.actionGroupName = ''
      }
    },
    async refresh() {
      const generation = ++this.refreshGeneration
      this.loading = true
      this.error = ''
      let snapshot
      try {
        snapshot = await getHomeSnapshot()
        if (generation !== this.refreshGeneration) return
        if (snapshot.mode === 'evaluation') {
          this.selectedEvaluationTaskId = snapshot.source.taskId
          this.homeSourceMode = 'evaluation'
          this.loading = false
          return
        }
        if (snapshot.mode === 'invalid') {
          await this.refreshRealtime(generation, snapshot)
          return
        }
      } catch (error) {
        if (generation !== this.refreshGeneration) return
        this.homeSourceMode = 'invalid'
        this.current = null
        this.realtimeSnapshot = null
        this.error = error.message || '首页数据源不可用'
        this.loading = false
        return
      }
      try {
        const trace = await loadCommunityHomeTrace()
        if (generation === this.refreshGeneration) {
          this.communityTraceRows = trace.rows
          this.communityTraceGroupName = trace.groupName || 'CHESCA 社区评估'
          this.$nextTick(this.drawCommunityTraceChart)
        }
      } catch (error) {
        if (generation === this.refreshGeneration) this.communityTraceRows = []
      }
      try {
        if (generation !== this.refreshGeneration) return
        const previousMode = this.homeSourceMode
        const previousId = this.realtimeSnapshot && this.realtimeSnapshot.source && this.realtimeSnapshot.source.communityId
        const sourceChanged = previousMode !== snapshot.mode || String(previousId) !== String(snapshot.source && snapshot.source.communityId)
        this.homeSourceMode = snapshot.mode
        if (snapshot.mode !== 'default') {
          if (sourceChanged) { this.selectedEnergyDay = ''; this.buildingIndex = 0; this.realtimeBuildings = []; this.dialogVisible = false; this.energyHomeDialogVisible = false }
          if (this.selectedEnergyDay || this.realtimeBuildings[this.buildingIndex]) await this.refreshRealtime(generation)
          else await this.refreshRealtime(generation, snapshot)
          return
        }
        if (previousMode !== 'default') { this.selectedEnergyDay = ''; this.buildingIndex = 0; this.energyFlows = null; this.realtimeSnapshot = null }
      } catch (error) {
        if (generation !== this.refreshGeneration) return
        this.homeSourceMode = 'invalid'; this.error = error.message || '首页数据源不可用'; this.current = null; this.realtimeSnapshot = null
        this.energyFlows = null; this.energyDays = []; this.actionCurrent = null; this.loading = false; this.energyLoading = false; this.energyBackfillLoading = false
        return
      }
      if (!this.energyFlows) this.energyLoading = true
      this.energyBackfillLoading = true

      const metricsP = this.refreshMetrics()

      const energyP = loadHomeEnergyProgressive(new Date(), {
        onToday: (energy) => {
          if (generation !== this.refreshGeneration || this.homeSourceMode !== 'default') return
          this.applyEnergyPayload(energy)
          this.energyLoading = false
          this.energyBackfillLoading = true
          this.refreshMetrics()
        },
        onComplete: (energy) => {
          if (generation !== this.refreshGeneration || this.homeSourceMode !== 'default') return
          this.applyEnergyPayload(energy)
          this.energyLoading = false
          this.energyBackfillLoading = false
        }
      }).catch((e) => {
        if (generation !== this.refreshGeneration || this.homeSourceMode !== 'default') return
        this.energyFlows = null
        this.energyDays = []
        this.energyBuildings = []
        this.energyMessage = e.message || '能源分配加载失败'
        this.energyGroupName = ''
        this.energyUntilTs = ''
        this.energyLoading = false
        this.energyBackfillLoading = false
      })

      await metricsP
      if (generation !== this.refreshGeneration || this.homeSourceMode !== 'default') return
      this.loading = false
      await energyP
      if (generation !== this.refreshGeneration || this.homeSourceMode !== 'default') return
      this.energyLoading = false
      this.energyBackfillLoading = false
    },
    openMoreInfo(focus) {
      const isAction = ACTION_SENSOR_KEYS.includes(focus)
      if (isAction) {
        if (!this.actionCurrent) return
      } else if (!this.current) {
        return
      }
      this.dialogFocus = focus || 'temperature'
      this.dialogVisible = true
    },
    openEnergyNodeMoreInfo(payload) {
      if (this.isCommunitySource) return
      if (!this.selectedEnergyDay) return
      const focus = payload && payload.focus
      this.energyDialogFocus = ['home', 'solar', 'grid', 'battery', 'load'].includes(focus)
        ? focus
        : 'home'
      this.energyHomeDialogVisible = true
    },
    drawCommunityTraceChart() {
      const element = this.$refs.communityTraceChart
      if (!element || !this.communityTraceRows.length) return
      if (!this.communityTraceChart || this.communityTraceChart.getDom() !== element) {
        if (this.communityTraceChart) this.communityTraceChart.dispose()
        this.communityTraceChart = echarts.init(element)
      }
      const rows = this.communityTraceRows
        .filter(row => row.building === this.buildingIndex)
        .sort((a, b) => a.step - b.step)
      const stride = Math.max(1, Math.ceil(rows.length / 1000))
      const sampled = rows.filter((row, index) => index % stride === 0 || index === rows.length - 1)
      this.communityTraceChart.setOption({
        color: [themeColor('secondary-text-color'), themeColor('energy-solar-color'), themeColor('energy-water-color')],
        tooltip: { trigger: 'axis' },
        legend: { top: 4, data: ['不可调负荷', '光伏发电', '热水需求'] },
        grid: { left: 46, right: 16, top: 42, bottom: 30 },
        xAxis: { type: 'category', boundaryGap: false, data: sampled.map(row => row.step), name: '仿真步' },
        yAxis: { type: 'value', scale: true, name: '观测值' },
        series: [
          { name: '不可调负荷', type: 'line', showSymbol: false, data: sampled.map(row => row.actual_load) },
          { name: '光伏发电', type: 'line', showSymbol: false, data: sampled.map(row => row.actual_solar) },
          { name: '热水需求', type: 'line', showSymbol: false, data: sampled.map(row => row.actual_dhw) }
        ]
      }, true)
      this.communityTraceChart.resize()
    },
    resizeCommunityTraceChart() {
      if (this.communityTraceChart) this.communityTraceChart.resize()
    }
  }
}
</script>

<style scoped>
/* Lovelace Home 布局 — 对齐 demo.home-assistant.io/#/lovelace/home */
.lovelace-home {
  min-height: 100%;
  padding: 0 0 72px;
  background: var(--primary-background-color);
  box-sizing: border-box;
}

.lovelace-header {
  padding: 16px 16px 8px;
  max-width: 1000px;
  margin: 0 auto;
}

.lovelace-title {
  margin: 0;
  font-size: var(--ha-font-size-page-title);
  font-weight: var(--ha-font-weight-page-title);
  letter-spacing: 0;
  color: var(--primary-text-color);
}

.masonry {
  max-width: 1000px;
  margin: 0 auto;
  padding: 4px 8px 24px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* —— energy distribution（模型优选同款） —— */
.home-energy-card {
  background: transparent;
}
.home-trace-card { background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: var(--ha-card-border-radius); padding: 16px; }
.home-trace-header h2 { margin: 0; font-size: 16px; font-weight: 500; }
.home-trace-header p { margin: 6px 0 0; color: var(--secondary-text-color); font-size: 12px; }
.home-trace-chart { width: 100%; height: 280px; }

.realtime-source-name { font-size: 20px; font-weight: 500; color: var(--primary-text-color); }
.realtime-freshness { font-size: 12px; color: var(--secondary-text-color); overflow-wrap: anywhere; }
.realtime-freshness.is-stale { color: var(--warning-color); }
.realtime-energy { background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: var(--ha-card-border-radius); padding: 16px; }
.realtime-energy h2 { margin: 0; font-size: 16px; font-weight: 500; }
.realtime-energy-caption { color: var(--secondary-text-color); font-size: 12px; margin: 8px 0; }
.realtime-energy-values { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; padding: 12px 0; }
.realtime-energy-values span { display: block; font-size: 12px; color: var(--secondary-text-color); }
.realtime-energy-values strong { display: block; font-size: 20px; font-weight: 500; font-variant-numeric: tabular-nums; }

.home-energy-card >>> .energy-dist-panel {
  border: 1px solid var(--divider-color);
  border-radius: var(--ha-card-border-radius);
}

/* —— entities —— */
.entities-row {
  display: grid;
  gap: 8px;
}

.entities-row-2 {
  grid-template-columns: 1fr 1fr;
}

.entities-row-3 {
  grid-template-columns: repeat(3, 1fr);
}

.entities-row-indoor .ha-entity-card {
  min-width: 0;
}

.entities-row-indoor .entity-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.section-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 4px 4px 0;
}

.section-label {
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0;
  text-transform: uppercase;
  color: var(--secondary-text-color);
}

.section-hint {
  font-size: 11px;
  color: var(--secondary-text-color);
  max-width: 55%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ha-entity-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  margin: 0;
  border: 1px solid var(--divider-color);
  border-radius: var(--ha-card-border-radius);
  background: var(--card-background-color);
  text-align: left;
  cursor: pointer;
  font: inherit;
  color: inherit;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}

.ha-entity-card:hover:not(:disabled) {
  border-color: var(--outline-hover-color);
  background: rgba(var(--rgb-primary-color), 0.04);
}

.ha-entity-card:disabled {
  opacity: 0.65;
  cursor: default;
}

.entity-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.entity-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--primary-text-color);
}

.entity-state {
  margin-top: 2px;
  font-size: 13px;
  color: var(--secondary-text-color);
  font-variant-numeric: tabular-nums;
}

.home-error {
  margin: 8px;
  color: var(--error-color);
  font-size: 13px;
}

.home-loading {
  margin: 8px;
  color: var(--secondary-text-color);
  font-size: 13px;
}

.energy-backfill-hint {
  margin-top: 0;
  font-size: 12px;
  opacity: 0.85;
}

@media (max-width: 720px) {
  .entities-row-3 {
    grid-template-columns: 1fr;
  }

  .entities-row-indoor .ha-entity-card {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
    padding: 10px;
  }

  .entities-row-indoor .entity-icon {
    width: 32px;
    height: 32px;
  }
}

@media (max-width: 560px) {
  .realtime-energy-values { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .home-trace-chart { height: 230px; }
  .entities-row-2 {
    grid-template-columns: 1fr;
  }
}
</style>
