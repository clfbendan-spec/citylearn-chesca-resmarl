<template>
  <div class="lovelace-home ha-page">
    <header class="lovelace-header">
      <h1 class="lovelace-title"> </h1>
    </header>

    <div class="masonry">
      <!-- 能源分配（与模型优选同款，固定 task · 按日聚合至当前时刻） -->
      <article class="home-energy-card">
        <energy-distribution-panel
          v-if="energyDays.length"
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
        <p v-else-if="energyMessage" class="home-loading">{{ energyMessage }}</p>
        <p v-else-if="energyLoading" class="home-loading">正在加载能源分配…</p>
        <p v-if="energyBackfillLoading" class="home-loading energy-backfill-hint">
          当日已就绪，正在加载历史日期…
        </p>
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
            <div class="entity-state">{{ pricingDisplay }} $/kWh</div>
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
      :building-options="BUILDING_OPTIONS"
      @change="onPeriodDayChange"
      @building-change="onBuildingChange"
    />

    <WeatherMoreInfoDialog
      :visible.sync="dialogVisible"
      :focus.sync="dialogFocus"
      :building-index="buildingIndex"
      :selected-day="selectedEnergyDay"
    />

    <EnergyHomeMoreInfoDialog
      :visible.sync="energyHomeDialogVisible"
      :day="selectedEnergyDay"
      :scope="energyScope"
      :until-ts="energyUntilTs"
      :focus="energyDialogFocus"
    />
  </div>
</template>

<script>
import HaMdiIcon from '@/components/home/HaMdiIcon.vue'
import HaEnergyPeriodSelector from '@/components/home/HaEnergyPeriodSelector.vue'
import WeatherMoreInfoDialog from '@/components/home/WeatherMoreInfoDialog.vue'
import EnergyHomeMoreInfoDialog from '@/components/home/EnergyHomeMoreInfoDialog.vue'
import EnergyDistributionPanel from '@/components/dashboard/EnergyDistributionPanel.vue'
import { getWeatherSnapshot, BUILDING_OPTIONS } from '@/utils/weather2026'
import { getActionSnapshot, HOME_ACTION_TASK_ID } from '@/utils/homeActions'
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
    HaMdiIcon,
    HaEnergyPeriodSelector,
    WeatherMoreInfoDialog,
    EnergyHomeMoreInfoDialog,
    EnergyDistributionPanel
  },
  data() {
    const saved = Number(localStorage.getItem(BUILDING_STORAGE_KEY))
    return {
      HOME_SENSORS,
      BUILDING_SENSOR_KEYS,
      HVAC_SENSOR_KEYS,
      ACTION_SENSOR_KEYS,
      BUILDING_OPTIONS,
      buildingIndex: Number.isFinite(saved) && saved >= 0 && saved <= 2 ? saved : 0,
      selectedEnergyDay: '',
      loading: true,
      error: '',
      current: null,
      currentIndex: 0,
      actionCurrent: null,
      actionMessage: '',
      actionGroupName: '',
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
  beforeDestroy() {
    if (this.refreshTimer) clearInterval(this.refreshTimer)
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
      const viewNow = this.metricsNow
      try {
        const snap = await getWeatherSnapshot(viewNow, 'day', this.buildingIndex)
        this.current = snap.current
        this.currentIndex = snap.currentIndex
        this.error = ''
      } catch (e) {
        this.error = e.message || '加载失败'
        this.current = null
      }
      try {
        const act = await getActionSnapshot(viewNow, 'day', this.buildingIndex)
        this.actionCurrent = act.current
        this.actionMessage = act.message || ''
        this.actionGroupName = act.groupName || ''
      } catch (e) {
        this.actionCurrent = null
        this.actionMessage = e.message || '动作 trace 加载失败'
        this.actionGroupName = ''
      }
    },
    async refresh() {
      this.loading = true
      this.error = ''
      if (!this.energyFlows) this.energyLoading = true
      this.energyBackfillLoading = true

      const metricsP = this.refreshMetrics()

      const energyP = loadHomeEnergyProgressive(new Date(), {
        onToday: (energy) => {
          this.applyEnergyPayload(energy)
          this.energyLoading = false
          this.energyBackfillLoading = true
          this.refreshMetrics()
        },
        onComplete: (energy) => {
          this.applyEnergyPayload(energy)
          this.energyLoading = false
          this.energyBackfillLoading = false
        }
      }).catch((e) => {
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
      this.loading = false
      await energyP
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
      if (!this.selectedEnergyDay) return
      const focus = payload && payload.focus
      this.energyDialogFocus = ['home', 'solar', 'grid', 'battery', 'load'].includes(focus)
        ? focus
        : 'home'
      this.energyHomeDialogVisible = true
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
  font-size: 28px;
  font-weight: 400;
  letter-spacing: -0.01em;
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
  letter-spacing: 0.04em;
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
  .entities-row-2 {
    grid-template-columns: 1fr;
  }
}
</style>
