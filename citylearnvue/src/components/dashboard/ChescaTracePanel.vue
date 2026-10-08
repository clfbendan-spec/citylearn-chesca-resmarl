<template>
  <div class="chesca-trace-panel">
    <div class="panel-header">
      <div>
        <h4 class="title">决策推演 (Decision Trace)</h4>
        <p v-if="activeSim" class="hint">
          当前分组：{{ activeSim }}
          <el-tag v-if="activeResmarlHint" size="mini" type="warning" style="margin-left: 8px">
            {{ activeResmarlHint }}
          </el-tag>
          · 关键步骤埋点与阶段推演
        </p>
      </div>
      <div v-if="hasData && showTraceFilters" class="controls">
        <el-select v-model="selectedEpisode" size="small" class="ctrl" placeholder="Episode">
          <el-option
            v-for="ep in episodes"
            :key="ep"
            :label="`Episode ${ep}`"
            :value="ep"
          />
        </el-select>
        <el-select v-model="selectedBuilding" size="small" class="ctrl" placeholder="建筑">
          <el-option
            v-for="b in buildings"
            :key="b"
            :label="buildingLabel(b)"
            :value="b"
          />
        </el-select>
        <el-select v-model="selectedMetric" size="small" class="ctrl" placeholder="预测指标">
          <el-option
            v-for="m in metrics"
            :key="m.key"
            :label="m.label"
            :value="m.key"
          />
        </el-select>
        <el-select v-model="logBuildingFilter" size="small" class="ctrl" clearable placeholder="日志建筑">
          <el-option label="全部建筑" :value="null" />
          <el-option
            v-for="b in buildings"
            :key="'log-' + b"
            :label="buildingLabel(b)"
            :value="b"
          />
        </el-select>
        <el-select
          v-model="actionBuildingScope"
          size="small"
          class="ctrl ctrl-wide"
          placeholder="动作建筑"
        >
          <el-option label="全部建筑（9 条线）" value="all" />
          <el-option
            v-for="b in buildings"
            :key="'act-' + b"
            :label="`${buildingLabel(b)}（3 条线）`"
            :value="b"
          />
        </el-select>
      </div>
    </div>

    <el-empty
      v-if="!hasData"
      description="暂无 Decision Trace 数据。请使用 CHESCA.py 或 Multi-agent.py 运行任务后重试。"
      class="empty-block"
    />

    <template v-else>
      <div v-if="stepRangeMax > 0" class="step-slider">
        <span class="slider-label">步数范围</span>
        <el-slider
          v-model="stepRange"
          range
          :min="0"
          :max="stepRangeMax"
          :format-tooltip="formatStepTooltip"
        />
      </div>

      <el-tabs v-model="activeChartTab" type="card" class="chart-tabs">
        <el-tab-pane label="决策推演日志" name="decisionLog">
          <decision-trace-log
            :decision-trace="decisionTrace"
            :selected-episode="selectedEpisode"
            :selected-building="logBuildingFilter"
            :step-range="stepRange"
          />
        </el-tab-pane>
        <el-tab-pane label="每步动作" name="stepActions">
          <p class="chart-desc">
            每时间步施加的最终动作：每栋建筑 3 维（DHW 储热、电池充放电、冷机）。
          </p>
          <div ref="stepActionChart" class="chart-box chart-box-tall" />
        </el-tab-pane>
        <el-tab-pane v-if="showAdvancedTraceTabs" label="预测对比" name="forecast">
          <div ref="forecastChart" class="chart-box" />
        </el-tab-pane>
        <el-tab-pane v-if="showAdvancedTraceTabs" label="动作 Refine" name="actions">
          <div ref="actionChart" class="chart-box" />
        </el-tab-pane>
        <el-tab-pane v-if="showAdvancedTraceTabs" label="负荷平衡" name="balance">
          <div ref="balanceChart" class="chart-box" />
          <div class="balance-legend">
            <el-tag size="mini" type="danger">减负荷触发 (B_high)</el-tag>
            <el-tag size="mini" type="success">增负荷触发 (B_low)</el-tag>
            <el-tag size="mini">Refine 已执行</el-tag>
          </div>
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<script>
import * as echarts from 'echarts'
import DecisionTraceLog from '@/components/dashboard/DecisionTraceLog.vue'
import {
  TRACE_METRICS,
  buildingLabel,
  buildStepActionSeries,
  filterTraceRows,
  formatPctError,
  listTraceBuildings,
  listTraceEpisodes
} from '@/utils/chescaTraceParse'
import { formatResmarlLabel } from '@/utils/resmarlLabels'

export default {
  name: 'ChescaTracePanel',
  components: { DecisionTraceLog },
  props: {
    activeSim: { type: String, default: '' },
    parsedTrace: { type: Object, default: () => ({}) },
    decisionTraceBySim: { type: Object, default: () => ({}) },
    resmarlBySim: { type: Object, default: () => ({}) }
  },
  data() {
    return {
      // 临时隐藏：顶部 Episode/建筑等筛选框，以及预测对比·动作 Refine·负荷平衡页签（步数范围滑条保留）
      showTraceFilters: false,
      showAdvancedTraceTabs: false,
      metrics: TRACE_METRICS,
      selectedEpisode: null,
      selectedBuilding: 0,
      selectedMetric: 'load',
      actionBuildingScope: 'all',
      logBuildingFilter: null,
      activeChartTab: 'decisionLog',
      stepRange: [0, 0],
      charts: {
        stepActions: null,
        forecast: null,
        action: null,
        balance: null
      },
      resizeObserver: null
    }
  },
  computed: {
    activeResmarlHint() {
      const label = formatResmarlLabel(this.resmarlBySim[this.activeSim])
      return label || ''
    },
    allRows() {
      if (!this.activeSim) return []
      const rows = this.parsedTrace[this.activeSim]
      return Array.isArray(rows) ? rows : []
    },
    hasData() {
      return this.allRows.length > 0 || !!this.decisionTrace
    },
    decisionTrace() {
      if (!this.activeSim) return null
      return this.decisionTraceBySim[this.activeSim] || null
    },
    /** 无 chesca_trace.csv 时（如 Multi-agent），从 decision_trace.steps 推导步数/建筑 */
    decisionSteps() {
      const steps = this.decisionTrace && this.decisionTrace.steps
      return Array.isArray(steps) ? steps : []
    },
    episodes() {
      const fromCsv = listTraceEpisodes(this.allRows)
      if (fromCsv.length) return fromCsv
      const eps = [...new Set(this.decisionSteps.map((s) => s.episode).filter((e) => e != null))]
      return eps.length ? eps.sort((a, b) => a - b) : []
    },
    buildings() {
      const fromCsv = listTraceBuildings(this.allRows)
      if (fromCsv.length) return fromCsv
      const set = new Set()
      this.decisionSteps.forEach((s) => {
        const buildings = s.buildings || []
        buildings.forEach((b) => {
          if (b && b.building != null) set.add(b.building)
        })
      })
      return [...set].sort((a, b) => a - b)
    },
    metricConfig() {
      return this.metrics.find((m) => m.key === this.selectedMetric) || this.metrics[0]
    },
    filteredRows() {
      let rows = filterTraceRows(this.allRows, {
        building: this.selectedBuilding,
        episode: this.selectedEpisode
      })
      rows = [...rows].sort((a, b) => (a.step ?? 0) - (b.step ?? 0))
      const [minStep, maxStep] = this.stepRange
      if (maxStep > minStep) {
        rows = rows.filter((r) => r.step >= minStep && r.step <= maxStep)
      }
      return rows
    },
    rowsForStepAction() {
      let rows = filterTraceRows(this.allRows, { episode: this.selectedEpisode })
      if (this.actionBuildingScope !== 'all') {
        rows = filterTraceRows(rows, { building: this.actionBuildingScope })
      }
      rows = [...rows].sort((a, b) => (a.step ?? 0) - (b.step ?? 0))
      // Multi-agent：无 CSV 时用 decision_trace 的动作终稿合成图数据
      if (!rows.length && this.decisionSteps.length) {
        rows = this.decisionStepsToActionRows()
      }
      const [minStep, maxStep] = this.stepRange
      if (maxStep > minStep) {
        rows = rows.filter((r) => r.step >= minStep && r.step <= maxStep)
      }
      return rows
    },
    stepActionChartData() {
      const allBuildings = this.actionBuildingScope === 'all'
      const building = allBuildings ? (this.buildings[0] ?? 0) : this.actionBuildingScope
      return buildStepActionSeries(this.rowsForStepAction, this.buildings, {
        allBuildings,
        building
      })
    },
    stepRangeMax() {
      const rows = filterTraceRows(this.allRows, {
        building: this.selectedBuilding,
        episode: this.selectedEpisode
      })
      const actionRows = filterTraceRows(this.allRows, { episode: this.selectedEpisode })
      const source = actionRows.length ? actionRows : rows
      if (source.length) {
        return Math.max(...source.map((r) => r.step ?? 0))
      }
      // Multi-agent 等仅有 decision_trace.json 的任务
      let steps = this.decisionSteps
      if (this.selectedEpisode != null) {
        steps = steps.filter((s) => s.episode === this.selectedEpisode)
      }
      if (!steps.length) return 0
      return Math.max(...steps.map((s) => s.step ?? 0))
    }
  },
  watch: {
    activeSim() {
      this.resetFilters()
      this.$nextTick(() => this.renderAllCharts())
    },
    allRows: {
      immediate: true,
      handler() {
        this.resetFilters()
      }
    },
    decisionTrace: {
      immediate: true,
      handler() {
        // 仅有 JSON、无 CSV 时也要刷新步数范围
        if (!this.allRows.length && this.decisionSteps.length) {
          this.resetFilters()
        }
      }
    },
    filteredRows() {
      this.renderAllCharts()
    },
    rowsForStepAction() {
      this.renderStepActionChart()
    },
    actionBuildingScope() {
      this.renderStepActionChart()
    },
    activeChartTab(tab) {
      const advanced = ['forecast', 'actions', 'balance']
      if (!this.showAdvancedTraceTabs && advanced.includes(tab)) {
        this.activeChartTab = 'decisionLog'
        return
      }
      this.$nextTick(() => {
        this.renderActiveChart()
        this.resizeCharts()
      })
    },
    stepRangeMax(val) {
      if (val > 0 && (this.stepRange[1] === 0 || this.stepRange[1] > val)) {
        this.stepRange = [0, val]
      }
    }
  },
  mounted() {
    this.initCharts()
    window.addEventListener('resize', this.resizeCharts)
    if (typeof ResizeObserver !== 'undefined') {
      this.resizeObserver = new ResizeObserver(() => this.resizeCharts())
      ;['stepActionChart', 'forecastChart', 'actionChart', 'balanceChart'].forEach((ref) => {
        if (this.$refs[ref]) {
          this.resizeObserver.observe(this.$refs[ref])
        }
      })
    }
    this.renderAllCharts()
  },
  beforeDestroy() {
    window.removeEventListener('resize', this.resizeCharts)
    if (this.resizeObserver) this.resizeObserver.disconnect()
    Object.values(this.charts).forEach((c) => c && c.dispose())
  },
  methods: {
    buildingLabel,
    /** 把 decision_trace.steps 展平为「每步动作」图可用的伪 CSV 行 */
    decisionStepsToActionRows() {
      const out = []
      let steps = this.decisionSteps
      if (this.selectedEpisode != null) {
        steps = steps.filter((s) => s.episode === this.selectedEpisode)
      }
      if (this.actionBuildingScope !== 'all') {
        const bid = this.actionBuildingScope
        steps.forEach((s) => {
          const buildings = s.buildings || []
          buildings.forEach((b) => {
            if (b.building !== bid) return
            const fin = (b.actions && b.actions.final) || {}
            out.push({
              episode: s.episode,
              step: s.step,
              hour: s.hour,
              building: b.building,
              action_dhw_final: fin.dhw,
              action_ele_final: fin.ele,
              action_tmp_final: fin.tmp
            })
          })
        })
        return out
      }
      steps.forEach((s) => {
        const buildings = s.buildings || []
        buildings.forEach((b) => {
          const fin = (b.actions && b.actions.final) || {}
          out.push({
            episode: s.episode,
            step: s.step,
            hour: s.hour,
            building: b.building,
            action_dhw_final: fin.dhw,
            action_ele_final: fin.ele,
            action_tmp_final: fin.tmp
          })
        })
      })
      return out
    },
    formatStepTooltip(val) {
      return `Step ${val}`
    },
    resetFilters() {
      const eps = this.episodes
      this.selectedEpisode = eps.length ? eps[0] : null
      const blds = this.buildings
      this.selectedBuilding = blds.length ? blds[0] : 0
      this.stepRange = [0, this.stepRangeMax]
    },
    initCharts() {
      if (this.$refs.stepActionChart && !this.charts.stepActions) {
        this.charts.stepActions = echarts.init(this.$refs.stepActionChart)
      }
      if (this.$refs.forecastChart && !this.charts.forecast) {
        this.charts.forecast = echarts.init(this.$refs.forecastChart)
      }
      if (this.$refs.actionChart && !this.charts.action) {
        this.charts.action = echarts.init(this.$refs.actionChart)
      }
      if (this.$refs.balanceChart && !this.charts.balance) {
        this.charts.balance = echarts.init(this.$refs.balanceChart)
      }
    },
    resizeCharts() {
      Object.values(this.charts).forEach((c) => c && c.resize())
    },
    renderAllCharts() {
      this.$nextTick(() => {
        this.initCharts()
        this.renderStepActionChart()
        this.renderForecastChart()
        this.renderActionChart()
        this.renderBalanceChart()
      })
    },
    renderActiveChart() {
      if (this.activeChartTab === 'decisionLog') return
      if (this.activeChartTab === 'stepActions') this.renderStepActionChart()
      else if (this.activeChartTab === 'forecast') this.renderForecastChart()
      else if (this.activeChartTab === 'actions') this.renderActionChart()
      else this.renderBalanceChart()
    },
    xAxisLabels(rows) {
      return rows.map((r) => `S${r.step}\nH${r.hour}`)
    },
    baseGrid() {
      return { left: 48, right: 24, top: 40, bottom: 56, containLabel: true }
    },
    stepLabelsFromRows(steps, rows) {
      const hourByStep = new Map()
      rows.forEach((r) => {
        if (r.step != null && !hourByStep.has(r.step)) {
          hourByStep.set(r.step, r.hour)
        }
      })
      return steps.map((s) => `S${s}\nH${hourByStep.get(s) ?? '-'}`)
    },
    renderStepActionChart() {
      const chart = this.charts.stepActions
      if (!chart || !this.rowsForStepAction.length) {
        chart?.clear()
        return
      }
      const { steps, series } = this.stepActionChartData
      const rows = this.rowsForStepAction
      const labels = this.stepLabelsFromRows(steps, rows)
      const allBuildings = this.actionBuildingScope === 'all'
      const title = allBuildings
        ? '全部建筑 · 每步动作（每栋 3 维）'
        : `${buildingLabel(this.actionBuildingScope)} · 每步动作`

      chart.setOption({
        title: { text: title, left: 'center', textStyle: { fontSize: 14 } },
        tooltip: {
          trigger: 'axis',
          formatter: (params) => {
            if (!params?.length) return ''
            const idx = params[0].dataIndex
            let html = `${labels[idx] || params[0].axisValue}<br/>`
            params.forEach((p) => {
              const val = p.value == null || Number.isNaN(p.value) ? '-' : Number(p.value).toFixed(4)
              html += `${p.marker}${p.seriesName}: ${val}<br/>`
            })
            return html
          }
        },
        legend: {
          type: 'scroll',
          bottom: 0,
          data: series.map((s) => s.name)
        },
        grid: { left: 48, right: 24, top: 48, bottom: allBuildings ? 72 : 56, containLabel: true },
        xAxis: {
          type: 'category',
          name: '仿真步',
          data: labels,
          axisLabel: { fontSize: 10, interval: Math.max(0, Math.floor(labels.length / 24) - 1) }
        },
        yAxis: { type: 'value', name: '动作值' },
        series: series.map((s) => ({
          name: s.name,
          type: 'line',
          showSymbol: false,
          connectNulls: true,
          data: s.data,
          itemStyle: { color: s.color },
          lineStyle: s.lineStyle || { color: s.color }
        }))
      }, true)
    },
    renderForecastChart() {
      const chart = this.charts.forecast
      if (!chart || !this.filteredRows.length) {
        chart?.clear()
        return
      }
      const rows = this.filteredRows
      const cfg = this.metricConfig
      const actual = rows.map((r) => r[cfg.actual])
      const forecast = rows.map((r) => r[cfg.forecast])
      const errorPct = rows.map((r) => formatPctError(r[cfg.error]))

      chart.setOption({
        title: { text: `${cfg.label}：实际 vs 预测`, left: 'center', textStyle: { fontSize: 14 } },
        tooltip: { trigger: 'axis' },
        legend: { bottom: 0, data: ['实际值', '上一步预测', '绝对百分比误差 (%)'] },
        grid: this.baseGrid(),
        xAxis: { type: 'category', data: this.xAxisLabels(rows), axisLabel: { fontSize: 10 } },
        yAxis: [
          { type: 'value', name: cfg.label },
          { type: 'value', name: '误差 %', position: 'right', axisLabel: { formatter: '{value}%' } }
        ],
        series: [
          { name: '实际值', type: 'line', showSymbol: false, data: actual, yAxisIndex: 0 },
          { name: '上一步预测', type: 'line', showSymbol: false, lineStyle: { type: 'dashed' }, data: forecast, yAxisIndex: 0 },
          {
            name: '绝对百分比误差 (%)',
            type: 'bar',
            data: errorPct,
            yAxisIndex: 1,
            itemStyle: { opacity: 0.35 }
          }
        ]
      }, true)
    },
    renderActionChart() {
      const chart = this.charts.action
      if (!chart || !this.filteredRows.length) {
        chart?.clear()
        return
      }
      const rows = this.filteredRows
      const labels = this.xAxisLabels(rows)

      chart.setOption({
        title: { text: '动作初稿 vs Refine 后', left: 'center', textStyle: { fontSize: 14 } },
        tooltip: { trigger: 'axis' },
        legend: {
          bottom: 0,
          data: ['DHW 初稿', 'DHW 终稿', '电池 初稿', '电池 终稿', '冷机 初稿', '冷机 终稿']
        },
        grid: this.baseGrid(),
        xAxis: { type: 'category', data: labels, axisLabel: { fontSize: 10 } },
        yAxis: { type: 'value', name: '动作值' },
        series: [
          { name: 'DHW 初稿', type: 'line', showSymbol: false, data: rows.map((r) => r.action_dhw_init) },
          { name: 'DHW 终稿', type: 'line', showSymbol: false, data: rows.map((r) => r.action_dhw_final) },
          { name: '电池 初稿', type: 'line', showSymbol: false, data: rows.map((r) => r.action_ele_init) },
          { name: '电池 终稿', type: 'line', showSymbol: false, data: rows.map((r) => r.action_ele_final) },
          { name: '冷机 初稿', type: 'line', showSymbol: false, data: rows.map((r) => r.action_tmp_init) },
          { name: '冷机 终稿', type: 'line', showSymbol: false, data: rows.map((r) => r.action_tmp_final) }
        ]
      }, true)
    },
    renderBalanceChart() {
      const chart = this.charts.balance
      if (!chart || !this.filteredRows.length) {
        chart?.clear()
        return
      }
      const rows = this.filteredRows
      const labels = this.xAxisLabels(rows)

      const netNext = rows.map((r) => r.net_load_next)
      const netMean = rows.map((r) => r.net_load_mean)
      const upperBand = rows.map((r) => {
        const mean = r.net_load_mean
        const std = r.net_load_std
        const bHigh = r.B_high
        if (mean == null || std == null || bHigh == null) return null
        return mean + bHigh * std
      })
      const lowerBand = rows.map((r) => {
        const mean = r.net_load_mean
        const std = r.net_load_std
        const bLow = r.B_low
        if (mean == null || std == null || bLow == null) return null
        return mean - bLow * std
      })

      const reduceMarks = rows
        .map((r, i) => (r.trigger_reduce_load ? { xAxis: i, yAxis: r.net_load_next, value: '减' } : null))
        .filter(Boolean)
      const increaseMarks = rows
        .map((r, i) => (r.trigger_increase_load ? { xAxis: i, yAxis: r.net_load_next, value: '增' } : null))
        .filter(Boolean)

      chart.setOption({
        title: { text: '净负荷与 B_high / B_low 阈值', left: 'center', textStyle: { fontSize: 14 } },
        tooltip: { trigger: 'axis' },
        legend: {
          bottom: 0,
          data: ['下一步净负荷', '历史均值', '均值+B_high×σ', '均值−B_low×σ']
        },
        grid: this.baseGrid(),
        xAxis: { type: 'category', data: labels, axisLabel: { fontSize: 10 } },
        yAxis: { type: 'value', name: 'kWh' },
        series: [
          {
            name: '下一步净负荷',
            type: 'line',
            showSymbol: true,
            symbolSize: 6,
            data: netNext,
            markPoint: {
              symbol: 'pin',
              symbolSize: 36,
              data: [
                ...reduceMarks.map((m) => ({ ...m, itemStyle: { color: '#f56c6c' } })),
                ...increaseMarks.map((m) => ({ ...m, itemStyle: { color: '#67c23a' } }))
              ]
            }
          },
          { name: '历史均值', type: 'line', showSymbol: false, lineStyle: { type: 'dotted' }, data: netMean },
          { name: '均值+B_high×σ', type: 'line', showSymbol: false, lineStyle: { type: 'dashed' }, data: upperBand },
          { name: '均值−B_low×σ', type: 'line', showSymbol: false, lineStyle: { type: 'dashed' }, data: lowerBand }
        ]
      }, true)
    }
  }
}
</script>

<style scoped>
.chesca-trace-panel {
  margin: 0;
  padding: var(--space-4);
  border: 1px solid var(--divider-color);
  border-radius: var(--ha-card-border-radius);
  background: var(--card-background-color);
  box-shadow: var(--ha-card-box-shadow);
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--space-3);
  gap: var(--space-3);
  flex-wrap: wrap;
}
.title {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 500;
  color: var(--primary-text-color);
}
.hint {
  margin: 0;
  font-size: 13px;
  color: var(--secondary-text-color);
}
.controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.ctrl {
  width: 140px;
}
.ctrl-wide {
  width: 168px;
}
.chart-desc {
  margin: 0 0 8px;
  padding: 0 4px;
  font-size: 12px;
  color: var(--secondary-text-color);
}
.chart-box-tall {
  height: 480px;
}
.step-slider {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding: 0 8px;
}
.slider-label {
  flex-shrink: 0;
  font-size: 13px;
  color: var(--secondary-text-color);
  width: 72px;
}
.step-slider :deep(.el-slider) {
  flex: 1;
}
.chart-tabs {
  background: var(--card-background-color);
  border-radius: var(--ha-card-border-radius);
}
.chart-box {
  width: 100%;
  height: 420px;
  min-height: 360px;
}
.balance-legend {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding: 0 12px 12px;
}
.empty-block {
  padding: 24px 0;
}
</style>
