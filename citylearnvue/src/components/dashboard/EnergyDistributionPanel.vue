<template>
  <el-card shadow="never" class="energy-dist-panel">
    <div class="panel-header">
      <div>
        <div class="panel-title">能源分配</div>
        <div class="panel-sub">
          <template v-if="simName">{{ simName }} · </template>
          {{ aggregateModeLabel }}（kWh）
        </div>
      </div>
      <div class="controls" v-if="showControls">
        <el-select
          v-if="showAggregateMode"
          v-model="aggregateMode"
          size="small"
          class="agg-select"
          placeholder="聚合方式"
        >
          <el-option label="按天" value="day" />
          <el-option label="按星期" value="week" />
          <el-option label="按月" value="month" />
          <el-option label="全部聚合" value="all" />
        </el-select>
        <el-select
          v-if="!hideScopeSelect"
          v-model="scope"
          size="small"
          class="scope-select"
          placeholder="范围"
        >
          <el-option label="社区合计" value="community" />
          <el-option
            v-for="b in buildings"
            :key="b"
            :label="formatBuilding(b)"
            :value="b"
          />
        </el-select>
        <template v-if="!hideDayControls && aggregateMode !== 'all'">
          <el-button size="small" icon="el-icon-arrow-left" :disabled="!canPrev" @click="shiftPeriod(-1)" />
          <el-select
            v-model="selectedPeriodKey"
            size="small"
            filterable
            :placeholder="periodPlaceholder"
            class="day-select"
          >
            <el-option
              v-for="p in periods"
              :key="p.key"
              :label="p.label"
              :value="p.key"
            />
          </el-select>
          <el-button size="small" icon="el-icon-arrow-right" :disabled="!canNext" @click="shiftPeriod(1)" />
        </template>
      </div>
    </div>

    <div v-if="!days.length" class="empty-tip">当前仿真暂无带 timestamp 的建筑导出数据</div>
    <div v-else class="ha-card-content">
      <div class="row row-top">
        <div class="spacer" />
        <div class="circle-container solar" :class="{ dim: flow.pv <= 0.001 }">
          <span class="label">太阳能</span>
          <button
            type="button"
            class="circle circle-detail node-circle-btn"
            :disabled="!canOpenDetail"
            aria-label="查看太阳能图表"
            @click="onNodeClick('solar')"
          >
            <svg viewBox="0 0 24 24" class="mdi"><path fill="currentColor" d="M4 5h16v2H4V5m0 4h4v10H4V9m6 0h4v10h-4V9m6 0h4v10h-4V9Z"/></svg>
            <span class="from">{{ formatKwh(flow.solarToHome+flow.solarToGrid+flow.solarToBattery)}} kWh</span>
            <svg viewBox="0 0 80 80" class="node-ring" aria-hidden="true">
              <circle class="ring solar" cx="40" cy="40" r="38" fill="none" />
            </svg>
          </button>
        </div>
        <div class="spacer" />
      </div>

      <div class="row row-mid">
        <div class="circle-container grid" :class="{ dim: flow.gridIn <= 0.001 && flow.gridOut <= 0.001 }">
          <button
            type="button"
            class="circle circle-detail node-circle-btn"
            :disabled="!canOpenDetail"
            aria-label="查看电网图表"
            @click="onNodeClick('grid')"
          >
            <svg viewBox="0 0 24 24" class="mdi"><path fill="currentColor" d="M9.5 2L7 7h3l-2.5 5H11l-4 8l1-6H5.5L9.5 2m5.5 0L12 7h3l-2.5 5H16l-4 8l1-6h-2.5L15 2Z"/></svg>
            <span class="return">← {{ formatKwh(flow.gridOut) }} kWh</span>
            <span class="consumption">→ {{ formatKwh(flow.gridIn) }} kWh</span>
            <svg viewBox="0 0 80 80" class="node-ring" aria-hidden="true">
              <circle class="ring grid" cx="40" cy="40" r="38" fill="none" />
            </svg>
          </button>
          <span class="label">电网</span>
        </div>

        <div class="circle-container home">
          <button
            type="button"
            class="circle circle-detail node-circle-btn home-circle-btn"
            :disabled="!canOpenDetail"
            aria-label="查看家庭耗电"
            @click="onNodeClick('home')"
          >
            <svg viewBox="0 0 24 24" class="mdi home-icon"><path fill="currentColor" d="M10 20v-6h4v6h5v-8h3L12 3L2 12h3v8h5Z"/></svg>
            <span class="from">{{ formatKwh(flow.home) }} kWh</span>
            <svg viewBox="0 0 80 80" class="node-ring home-ring" aria-hidden="true">
              <circle
                class="ring solar"
                cx="40" cy="40" r="38"
                fill="none"
                :stroke-dasharray="homeRing.solarDash"
                stroke-dashoffset="0"
                transform="rotate(-90 40 40)"
              />
              <circle
                class="ring grid"
                cx="40" cy="40" r="38"
                fill="none"
                :stroke-dasharray="homeRing.gridDash"
                :stroke-dashoffset="homeRing.gridOffset"
                transform="rotate(-90 40 40)"
              />
              <circle
                class="ring battery"
                cx="40" cy="40" r="38"
                fill="none"
                :stroke-dasharray="homeRing.batDash"
                :stroke-dashoffset="homeRing.batOffset"
                transform="rotate(-90 40 40)"
              />
            </svg>
          </button>
          <span class="label">家庭</span>
        </div>
      </div>

      <div class="row row-bot">
        <div class="spacer" />
        <div class="circle-container battery" :class="{ dim: flow.batIn <= 0.001 && flow.batOut <= 0.001 }">
          <button
            type="button"
            class="circle circle-detail node-circle-btn"
            :disabled="!canOpenDetail"
            aria-label="查看电池图表"
            @click="onNodeClick('battery')"
          >
            <svg viewBox="0 0 24 24" class="mdi"><path fill="currentColor" d="M16 4h-2V2H10v2H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2m0 16H8V6h8v14Z"/></svg>
            <span class="battery-in">↓ {{ formatKwh(flow.batIn) }} kWh</span>
            <span class="battery-out">↑ {{ formatKwh(flow.batOut) }} kWh</span>
            <svg viewBox="0 0 80 80" class="node-ring" aria-hidden="true">
              <circle class="ring battery" cx="40" cy="40" r="38" fill="none" />
            </svg>
          </button>
          <span class="label">电池</span>
        </div>
        <div class="spacer" />
      </div>

      <!-- HA：太阳能 / 电网 / 电池 / 家庭 两两相连，共 6 条电边 -->
      <div class="lines">
        <svg
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          xmlns="http://www.w3.org/2000/svg"
          xmlns:xlink="http://www.w3.org/1999/xlink"
        >
          <path :id="lineId('return')" class="return" d="M45,0 v15 c0,35 -10,30 -30,30 h-20" vector-effect="non-scaling-stroke" />
          <path :id="lineId('solar')" class="solar" d="M55,0 v15 c0,35 10,30 30,30 h20" vector-effect="non-scaling-stroke" />
          <path :id="lineId('battery-house')" class="battery-house" d="M55,100 v-15 c0,-35 10,-30 30,-30 h20" vector-effect="non-scaling-stroke" />
          <path
            :id="lineId('battery-grid')"
            :class="batteryGridClass"
            d="M45,100 v-15 c0,-35 -10,-30 -30,-30 h-20"
            vector-effect="non-scaling-stroke"
          />
          <path :id="lineId('battery-solar')" class="battery-solar" d="M50,0 V100" vector-effect="non-scaling-stroke" />
          <path :id="lineId('grid')" class="grid" d="M0,50 H100" vector-effect="non-scaling-stroke" />

          <circle v-if="flow.solarToGrid > 0.001" r="1" class="return" vector-effect="non-scaling-stroke">
            <animateMotion :dur="dotDur(flow.solarToGrid)" repeatCount="indefinite" calcMode="linear">
              <mpath :xlink:href="lineHref('return')" :href="lineHref('return')" />
            </animateMotion>
          </circle>
          <circle v-if="flow.solarToHome > 0.001" r="1" class="solar" vector-effect="non-scaling-stroke">
            <animateMotion :dur="dotDur(flow.solarToHome)" repeatCount="indefinite" calcMode="linear">
              <mpath :xlink:href="lineHref('solar')" :href="lineHref('solar')" />
            </animateMotion>
          </circle>
          <circle v-if="flow.gridToHome > 0.001" r="1" class="grid" vector-effect="non-scaling-stroke">
            <animateMotion :dur="dotDur(flow.gridToHome)" repeatCount="indefinite" calcMode="linear">
              <mpath :xlink:href="lineHref('grid')" :href="lineHref('grid')" />
            </animateMotion>
          </circle>
          <circle v-if="flow.solarToBattery > 0.001" r="1" class="battery-solar" vector-effect="non-scaling-stroke">
            <animateMotion :dur="dotDur(flow.solarToBattery)" repeatCount="indefinite" calcMode="linear">
              <mpath :xlink:href="lineHref('battery-solar')" :href="lineHref('battery-solar')" />
            </animateMotion>
          </circle>
          <circle v-if="flow.batteryToHome > 0.001" r="1" class="battery-house" vector-effect="non-scaling-stroke">
            <animateMotion :dur="dotDur(flow.batteryToHome)" repeatCount="indefinite" calcMode="linear">
              <mpath :xlink:href="lineHref('battery-house')" :href="lineHref('battery-house')" />
            </animateMotion>
          </circle>
          <circle v-if="flow.gridToBattery > 0.001" r="1" class="battery-from-grid" vector-effect="non-scaling-stroke">
            <animateMotion
              :dur="dotDur(flow.gridToBattery)"
              repeatCount="indefinite"
              keyPoints="1;0"
              keyTimes="0;1"
              calcMode="linear"
            >
              <mpath :xlink:href="lineHref('battery-grid')" :href="lineHref('battery-grid')" />
            </animateMotion>
          </circle>
          <circle v-if="flow.batteryToGrid > 0.001" r="1" class="battery-to-grid" vector-effect="non-scaling-stroke">
            <animateMotion :dur="dotDur(flow.batteryToGrid)" repeatCount="indefinite" calcMode="linear">
              <mpath :xlink:href="lineHref('battery-grid')" :href="lineHref('battery-grid')" />
            </animateMotion>
          </circle>
        </svg>
      </div>
    </div>

    <div v-if="days.length" class="breakdown">
      <button
        type="button"
        class="breakdown-btn"
        :disabled="!canOpenDetail"
        aria-label="查看不可调负荷与净用电量图表"
        @click="onNodeClick('load')"
      >
        <span>不可调负荷 {{ formatKwh(flow.nonShiftable) }} kWh</span>
        <span class="sep">·</span>
        <span>净用电量 {{ formatKwh(flow.net) }} kWh</span>
      </button>
    </div>
  </el-card>
</template>

<script>
import {
  listEnergyFlowMeta,
  listEnergyFlowPeriods,
  aggregateEnergyFlowDay,
  aggregateEnergyFlowPeriod
} from '@/utils/energyFlowAggregate'

const EMPTY_FLOW = {
  pv: 0, gridIn: 0, gridOut: 0, batIn: 0, batOut: 0,
  home: 0, nonShiftable: 0, otherLoad: 0, net: 0,
  solarToHome: 0, solarToGrid: 0, solarToBattery: 0,
  gridToHome: 0, gridToBattery: 0,
  batteryToHome: 0, batteryToGrid: 0
}

const RING_C = 2 * Math.PI * 38

const AGG_LABELS = {
  day: '按天聚合',
  week: '按星期聚合',
  month: '按月聚合',
  all: '全部聚合'
}

export default {
  name: 'EnergyDistributionPanel',
  props: {
    folderData: { type: Object, default: () => ({}) },
    /** 服务端预聚合：day -> scope -> flow；优先于 folderData（仅按天） */
    precomputedFlows: { type: Object, default: null },
    externalDays: { type: Array, default: null },
    externalBuildings: { type: Array, default: null },
    /** 外部指定范围（如 building_1）；有值时覆盖内部 scope */
    externalScope: { type: String, default: null },
    /** 隐藏社区/建筑下拉（由页面其它控件同步） */
    hideScopeSelect: { type: Boolean, default: false },
    /** 隐藏日期切换（由页面外部日期卡控制） */
    hideDayControls: { type: Boolean, default: false },
    /** 外部选中日 YYYY-MM-DD；有值时覆盖内部 selectedDay */
    externalSelectedDay: { type: String, default: null },
    /** 外部聚合方式 day|week|month|all；有值时覆盖内部 */
    externalAggregateMode: { type: String, default: null },
    /** 外部周期 key（与 listEnergyFlowPeriods 一致） */
    externalPeriodKey: { type: String, default: null },
    simName: { type: String, default: '' },
    /** 为 true 时默认选中可选日期中的最后一天（首页：当前日） */
    preferLatestDay: { type: Boolean, default: false },
    /** 显示聚合方式切换（内部控件；底栏接管时勿开） */
    showAggregateMode: { type: Boolean, default: false }
  },
  data() {
    return {
      days: [],
      buildings: [],
      periods: [],
      selectedDay: '',
      selectedPeriodKey: '',
      aggregateMode: 'day',
      scope: 'community',
      flow: { ...EMPTY_FLOW }
    }
  },
  computed: {
    showControls() {
      return this.showAggregateMode || !this.hideScopeSelect || !this.hideDayControls
    },
    activeScope() {
      return this.externalScope || this.scope
    },
    effectiveAggregateMode() {
      if (this.externalAggregateMode) return this.externalAggregateMode
      if (this.usePrecomputed) return 'day'
      return this.aggregateMode || 'day'
    },
    activeSelectedDay() {
      return this.externalSelectedDay || this.selectedDay
    },
    activePeriodKey() {
      return this.externalPeriodKey || this.selectedPeriodKey
    },
    activePeriod() {
      const mode = this.effectiveAggregateMode
      const key = this.activePeriodKey
      if (key) {
        const hit = this.periods.find((p) => p.key === key)
        if (hit) return hit
      }
      if (mode === 'day' && this.activeSelectedDay) {
        const hit = this.periods.find((p) => p.key === this.activeSelectedDay)
        if (hit) return hit
        return {
          key: this.activeSelectedDay,
          label: this.activeSelectedDay,
          days: [this.activeSelectedDay]
        }
      }
      return this.periods.find((p) => p.key === this.selectedPeriodKey) || null
    },
    activePeriodDays() {
      return (this.activePeriod && this.activePeriod.days) || []
    },
    canOpenDetail() {
      return this.activePeriodDays.length > 0
    },
    periodPlaceholder() {
      if (this.effectiveAggregateMode === 'week') return '选择星期'
      if (this.effectiveAggregateMode === 'month') return '选择月份'
      return '选择日期'
    },
    aggregateModeLabel() {
      return AGG_LABELS[this.effectiveAggregateMode] || AGG_LABELS.day
    },
    periodIndex() {
      return this.periods.findIndex((p) => p.key === this.activePeriodKey)
    },
    canPrev() {
      return this.periodIndex > 0
    },
    canNext() {
      return this.periodIndex >= 0 && this.periodIndex < this.periods.length - 1
    },
    batteryGridClass() {
      const fromGrid = this.flow.gridToBattery > 0.001
      const toGrid = this.flow.batteryToGrid > 0.001
      return {
        'battery-from-grid': fromGrid && !toGrid,
        'battery-to-grid': toGrid
      }
    },
    homeRing() {
      const solar = Math.max(this.flow.solarToHome || 0, 0)
      const grid = Math.max(this.flow.gridToHome || 0, 0)
      const bat = Math.max(this.flow.batteryToHome || 0, 0)
      const total = solar + grid + bat
      if (total < 0.001) {
        return {
          solarDash: `0 ${RING_C}`,
          gridDash: `0 ${RING_C}`,
          gridOffset: 0,
          batDash: `0 ${RING_C}`,
          batOffset: 0
        }
      }
      const sLen = (solar / total) * RING_C
      const gLen = (grid / total) * RING_C
      const bLen = (bat / total) * RING_C
      return {
        solarDash: `${sLen} ${RING_C - sLen}`,
        gridDash: `${gLen} ${RING_C - gLen}`,
        gridOffset: -sLen,
        batDash: `${bLen} ${RING_C - bLen}`,
        batOffset: -(sLen + gLen)
      }
    },
    usePrecomputed() {
      return !!(this.precomputedFlows && Object.keys(this.precomputedFlows).length)
    }
  },
  watch: {
    folderData: { immediate: true, handler() { this.bootstrap() } },
    precomputedFlows: { deep: true, handler() { this.bootstrap() } },
    externalDays() { this.bootstrap() },
    externalBuildings() { this.bootstrap() },
    externalScope() { this.recompute() },
    externalSelectedDay() { this.rebuildPeriodsAndRecompute() },
    externalAggregateMode() { this.rebuildPeriodsAndRecompute(true) },
    externalPeriodKey() { this.recompute() },
    simName() { this.bootstrap() },
    preferLatestDay() { this.bootstrap() },
    selectedDay() {
      if (this.effectiveAggregateMode === 'day' && !this.externalSelectedDay) {
        this.selectedPeriodKey = this.selectedDay
      }
      this.recompute()
    },
    selectedPeriodKey() { this.recompute() },
    aggregateMode() { this.rebuildPeriodsAndRecompute(true) },
    scope() { this.recompute() }
  },
  methods: {
    lineId(name) {
      return `ed-${this._uid}-${name}`
    },
    lineHref(name) {
      return `#${this.lineId(name)}`
    },
    formatBuilding(b) {
      const n = b.match(/\d+/)?.[0]
      return n ? `建筑 ${n}` : b
    },
    formatKwh(v) {
      const n = Number(v) || 0
      if (n >= 100) return n.toFixed(1)
      if (n >= 10) return n.toFixed(2)
      if (n >= 1) return n.toFixed(2)
      return n.toFixed(3)
    },
    dotDur(v) {
      const n = Math.max(Number(v) || 0, 0.01)
      return `${Math.max(1.2, Math.min(6, 18 / Math.sqrt(n)))}s`
    },
    bootstrap() {
      const prevPeriod = this.selectedPeriodKey
      const prevSelected = this.activeSelectedDay
      if (this.usePrecomputed) {
        this.days = (this.externalDays && this.externalDays.length)
          ? [...this.externalDays]
          : Object.keys(this.precomputedFlows).sort()
        this.buildings = (this.externalBuildings && this.externalBuildings.length)
          ? [...this.externalBuildings]
          : this.inferBuildingsFromFlows()
      } else {
        const meta = listEnergyFlowMeta(this.folderData)
        this.days = (this.externalDays && this.externalDays.length)
          ? [...this.externalDays]
          : meta.days
        this.buildings = (this.externalBuildings && this.externalBuildings.length)
          ? [...this.externalBuildings]
          : meta.buildings
      }
      if (!this.days.length) {
        this.selectedDay = ''
        this.selectedPeriodKey = ''
        this.periods = []
        this.flow = { ...EMPTY_FLOW }
        return
      }
      if (!this.externalSelectedDay) {
        if (prevSelected && this.days.includes(prevSelected)) {
          this.selectedDay = prevSelected
        } else if (!this.days.includes(this.selectedDay)) {
          this.selectedDay = this.preferLatestDay
            ? this.days[this.days.length - 1]
            : this.days[0]
        }
      }
      if (!this.externalScope && this.scope !== 'community' && !this.buildings.includes(this.scope)) {
        this.scope = 'community'
      }
      this.rebuildPeriods(prevPeriod)
      this.recompute()
    },
    rebuildPeriodsAndRecompute(resetSelection) {
      this.rebuildPeriods(resetSelection ? '' : this.selectedPeriodKey)
      this.recompute()
    },
    rebuildPeriods(preferKey) {
      const mode = this.effectiveAggregateMode
      this.periods = listEnergyFlowPeriods(this.days, mode)
      if (!this.periods.length) {
        this.selectedPeriodKey = ''
        return
      }
      if (mode === 'day') {
        const day = this.activeSelectedDay || this.selectedDay || this.periods[0].key
        this.selectedPeriodKey = this.periods.some((p) => p.key === day)
          ? day
          : this.periods[0].key
        if (!this.externalSelectedDay) this.selectedDay = this.selectedPeriodKey
        return
      }
      if (preferKey && this.periods.some((p) => p.key === preferKey)) {
        this.selectedPeriodKey = preferKey
        return
      }
      if (this.periods.some((p) => p.key === this.selectedPeriodKey)) return
      // 尽量落到包含当前日的周期
      const day = this.activeSelectedDay || this.selectedDay
      const containing = day
        ? this.periods.find((p) => (p.days || []).includes(day))
        : null
      this.selectedPeriodKey = containing
        ? containing.key
        : (this.preferLatestDay
          ? this.periods[this.periods.length - 1].key
          : this.periods[0].key)
    },
    inferBuildingsFromFlows() {
      const set = new Set()
      Object.values(this.precomputedFlows || {}).forEach((scopeMap) => {
        Object.keys(scopeMap || {}).forEach((k) => {
          if (k !== 'community') set.add(k)
        })
      })
      return [...set].sort((a, b) => {
        const na = parseInt(a.match(/\d+/)?.[0] || '0', 10)
        const nb = parseInt(b.match(/\d+/)?.[0] || '0', 10)
        return na - nb
      })
    },
    shiftPeriod(delta) {
      const i = this.periodIndex + delta
      if (i < 0 || i >= this.periods.length) return
      const key = this.periods[i].key
      this.selectedPeriodKey = key
      if (this.effectiveAggregateMode === 'day' && !this.externalSelectedDay) {
        this.selectedDay = key
      }
    },
    recompute() {
      const periodDays = this.activePeriodDays
      if (!periodDays.length) {
        this.flow = { ...EMPTY_FLOW }
        return
      }
      const scope = this.activeScope
      const mode = this.effectiveAggregateMode
      if (this.usePrecomputed && mode === 'day') {
        const day = periodDays[0]
        const scopeMap = this.precomputedFlows[day] || {}
        const raw = scopeMap[scope] || scopeMap.community
        if (!raw) {
          this.flow = { ...EMPTY_FLOW }
          return
        }
        const merged = { ...EMPTY_FLOW, ...raw }
        if (merged.net == null || Number.isNaN(Number(merged.net))) {
          merged.net = (Number(merged.gridIn) || 0) - (Number(merged.gridOut) || 0)
        }
        this.flow = merged
        return
      }
      if (mode === 'day' || periodDays.length === 1) {
        this.flow = aggregateEnergyFlowDay(this.folderData, periodDays[0], scope)
        return
      }
      this.flow = aggregateEnergyFlowPeriod(this.folderData, periodDays, scope)
    },
    onNodeClick(focus) {
      if (!this.canOpenDetail) return
      const period = this.activePeriod
      this.$emit('node-click', {
        focus: focus || 'home',
        day: periodDaysFirst(period),
        periodKey: period && period.key,
        periodLabel: period && period.label,
        periodDays: [...(period && period.days) || []],
        aggregateMode: this.effectiveAggregateMode,
        scope: this.activeScope
      })
    }
  }
}

function periodDaysFirst(period) {
  if (!period || !period.days || !period.days.length) return ''
  return period.days[0]
}
</script>

<style scoped>
.energy-dist-panel {
  margin-top: 0;
  --energy-solar: var(--energy-solar-color);
  --energy-grid: var(--energy-grid-consumption-color);
  --energy-return: var(--energy-grid-return-color);
  --energy-battery-out: var(--energy-battery-out-color);
  --energy-battery-in: var(--energy-battery-in-color);
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
  flex-wrap: wrap;
}
.panel-title {
  font-size: 16px;
  font-weight: 500;
  color: var(--primary-text-color);
}
.panel-sub {
  margin-top: 4px;
  font-size: 12px;
  color: var(--secondary-text-color);
}
.controls {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.scope-select { width: 120px; }
.agg-select { width: 118px; }
.day-select { width: 200px; }
.empty-tip {
  padding: var(--space-5);
  text-align: center;
  color: var(--secondary-text-color);
  font-size: 13px;
}

.ha-card-content {
  position: relative;
  max-width: 500px;
  margin: 0 auto;
  direction: ltr;
}
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.spacer {
  width: 110px;
  flex-shrink: 0;
}
.circle-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 110px;
  flex-shrink: 0;
  z-index: 2;
}
.circle-container.dim { opacity: 0.55; }
.circle-container.solar { height: 136px; }
.circle-container.battery {
  height: 136px;
  justify-content: flex-start;
}
.circle-container.home,
.circle-container.grid {
  min-height: 136px;
}

.circle {
  width: 100px;
  height: 100px;
  border-radius: 50%;
  box-sizing: border-box;
  border: none;
  background: var(--card-background-color, #fff);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  font-size: 11px;
  line-height: 1.15;
  position: relative;
  color: var(--primary-text-color);
  box-shadow: 0 0 0 4px var(--card-background-color);
}
.circle.circle-detail {
  width: 100px;
  height: 100px;
  padding: 4px 2px;
  line-height: 1.2;
}
.node-circle-btn {
  margin: 0;
  padding: 4px 2px;
  font: inherit;
  cursor: pointer;
  appearance: none;
  -webkit-appearance: none;
  background: var(--card-background-color, #fff);
  border: none;
  color: var(--primary-text-color);
}
.node-circle-btn:hover:not(:disabled) {
  filter: brightness(0.97);
}
.node-circle-btn:disabled {
  cursor: default;
  opacity: 0.7;
}
.mdi {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  color: var(--secondary-text-color);
}
.circle-detail .mdi {
  width: 18px;
  height: 18px;
}
.home-icon { width: 24px; height: 24px; color: var(--secondary-text-color); }
.circle-detail .home-icon { width: 18px; height: 18px; }
.val {
  margin-top: 2px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  font-size: 11px;
}
.label {
  color: var(--secondary-text-color);
  font-size: 12px;
  height: 20px;
  line-height: 20px;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 110px;
  white-space: nowrap;
  text-align: center;
}
.return,
.consumption,
.battery-in,
.battery-out,
.from,
.to-home,
.to-grid,
.to-bat,
.from-solar,
.from-grid,
.from-bat {
  font-weight: 600;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.from { color: var(--primary-text-color); }
.return { color: var(--energy-return); }
.consumption { color: var(--energy-grid); }
.battery-in { color: var(--energy-battery-in); }
.battery-out { color: var(--energy-battery-out); }
.to-home,
.from-solar { color: var(--energy-solar); }
.to-grid { color: var(--energy-return); }
.from-grid { color: var(--energy-grid); }
.to-bat { color: var(--energy-battery-in); }
.from-bat { color: var(--energy-battery-out); }
.circle-detail .to-home,
.circle-detail .to-grid,
.circle-detail .to-bat,
.circle-detail .from-solar,
.circle-detail .from-grid,
.circle-detail .from-bat {
  font-size: 9px;
}

.node-ring {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
.node-ring .ring {
  stroke-width: 4;
  fill: none;
}
.node-ring .ring.solar { stroke: var(--energy-solar); }
.node-ring .ring.grid { stroke: var(--energy-grid); }
.node-ring .ring.battery { stroke: var(--energy-battery-out); }

.lines {
  position: absolute;
  left: 0;
  right: 0;
  top: 88px;
  bottom: 88px;
  display: flex;
  justify-content: center;
  pointer-events: none;
  z-index: 1;
}
.lines svg {
  width: calc(100% - 220px);
  height: 100%;
  max-width: 340px;
  overflow: visible;
}
.lines path {
  fill: none;
  stroke-width: 1;
}
.lines path.solar { stroke: var(--energy-solar); }
.lines path.return { stroke: var(--energy-return); }
.lines path.grid { stroke: var(--energy-grid); }
.lines path.battery-house { stroke: var(--energy-battery-out); }
.lines path.battery-solar { stroke: var(--energy-battery-in); }
.lines path.battery-from-grid { stroke: var(--energy-grid); }
.lines path.battery-to-grid { stroke: var(--energy-return); }
.lines circle {
  stroke-width: 4;
}
.lines circle.solar {
  stroke: var(--energy-solar);
  fill: var(--energy-solar);
}
.lines circle.return,
.lines circle.battery-to-grid {
  stroke: var(--energy-return);
  fill: var(--energy-return);
}
.lines circle.grid,
.lines circle.battery-from-grid {
  stroke: var(--energy-grid);
  fill: var(--energy-grid);
}
.lines circle.battery-house {
  stroke: var(--energy-battery-out);
  fill: var(--energy-battery-out);
}
.lines circle.battery-solar {
  stroke: var(--energy-battery-in);
  fill: var(--energy-battery-in);
}

.breakdown {
  margin-top: 8px;
  text-align: center;
  font-size: 12px;
  color: var(--secondary-text-color);
}
.breakdown-btn {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: center;
  margin: 0;
  padding: 2px 6px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}
.breakdown-btn:hover:not(:disabled) {
  background: rgba(68, 115, 158, 0.08);
  color: var(--primary-text-color);
}
.breakdown-btn:disabled {
  cursor: default;
  opacity: 0.7;
}
.breakdown .sep { margin: 0 6px; color: var(--disabled-text-color); }
.breakdown .muted { color: var(--secondary-text-color); }
</style>
