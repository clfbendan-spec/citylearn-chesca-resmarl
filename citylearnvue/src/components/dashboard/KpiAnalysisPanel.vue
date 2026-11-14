<template>
  <div class="kpi-panel">
    <div class="panel-header">
      <div>
        <h4 class="title">KPI 指标</h4>
        <p v-if="activeSim && !showComparison" class="hint">
          当前分组：{{ activeSim }}
          <el-tag v-if="activeResmarlLabel" size="mini" type="info" class="resmarl-tag">
            {{ activeResmarlLabel }}
          </el-tag>
        </p>
        <p v-else-if="showComparison" class="hint">
          <template v-if="comparisonViewMode === 'diff'">
            差值对比：{{ sideLabel(compareFrom, '评估模型') }} − {{ sideLabel(compareTo, '对照组') }}
          </template>
          <template v-else>
            并排对比：左 {{ sideLabel(compareFrom, '评估模型') }} · 右 {{ sideLabel(compareTo, '对照组') }}
          </template>
        </p>
      </div>
      <div class="actions">
        <el-select
          v-model="labelLocale"
          size="small"
          class="locale-select"
          placeholder="显示语言"
        >
          <el-option label="中文" value="zh" />
          <el-option label="英文" value="en" />
          <el-option label="中文（英文）" value="zh-en" />
        </el-select>
        <el-button
          v-if="showComparison"
          size="small"
          type="primary"
          plain
          @click="toggleComparisonView"
        >
          {{ comparisonViewMode === 'diff' ? '并排对比' : '差值对比' }}
        </el-button>
        <el-button
          v-if="showComparison && !isPairCompare"
          size="small"
          @click="closeComparison"
        >
          返回 KPI
        </el-button>
        <el-button
          v-else-if="!showComparison && canCompare"
          type="warning"
          size="small"
          @click="openCompare"
        >
          对比
        </el-button>
      </div>
    </div>

    <div v-if="!showComparison && currentRows.length" class="table-wrap">
      <div class="kpi-help">
        竖线左侧为实际指标值，右侧为原始 KPI 基准百分比；不适比例直接显示实际占比。悬浮指标名称可查看定义。
      </div>
      <table class="kpi-native-table">
        <thead>
          <tr>
            <th v-for="col in currentColumns" :key="col">{{ columnLabel(col) }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, rowIndex) in beginnerRows" :key="rowIndex">
            <td v-for="col in currentColumns" :key="col">
              <span v-if="isKpiColumn(col)" :title="kpiHelp(getRowCell(row, col))">{{ kpiLabel(getRowCell(row, col)) }}</span>
              <span v-else>{{ formatKpiDisplayValue(getRowCell(row, col), getRowCell(row, kpiColumnKey), activeSim, col) }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div
      v-else-if="showComparison && comparisonViewMode === 'diff' && comparisonRows.length"
      class="table-wrap"
    >
      <div class="kpi-help">
        悬浮指标名称可查看定义；差值模式显示评估模型减去对照方案的原始 KPI 差。
      </div>
      <table class="kpi-native-table">
        <thead>
          <tr>
            <th v-for="col in comparisonColumns" :key="col">{{ columnLabel(col) }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, rowIndex) in visibleComparisonRows" :key="rowIndex">
            <td v-for="col in comparisonColumns" :key="col">
              <span v-if="isKpiColumn(col)" :title="kpiHelp(getRowCell(row, col))">{{ kpiLabel(getRowCell(row, col)) }}</span>
              <span v-else :style="cellStyle(getRowCell(row, col))">{{ formatDiffValue(getRowCell(row, col), getRowCell(row, this.kpiColumnKey)) }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div
      v-else-if="showComparison && comparisonViewMode === 'sideBySide' && mergedSideBySideTable"
      class="table-wrap"
    >
      <table class="kpi-native-table kpi-merged-compare-table">
        <colgroup>
          <col class="kpi-fixed-col" />
          <col
            v-for="col in mergedSideBySideTable.valueColumns"
            :key="'col-from-' + col"
            :style="{ width: mergedSideBySideTable.valueColWidth }"
          />
          <col
            v-for="col in mergedSideBySideTable.valueColumns"
            :key="'col-to-' + col"
            :style="{ width: mergedSideBySideTable.valueColWidth }"
          />
        </colgroup>
        <thead>
          <tr>
            <th rowspan="2" class="kpi-col-head">{{ columnLabel(mergedSideBySideTable.kpiKey) }}</th>
            <th :colspan="mergedSideBySideTable.valueColumns.length" class="algo-head algo-head-from">
              <template v-if="isPairCompare">
                <div class="algo-role">评估模型</div>
                <div class="algo-name">{{ compareLabel(compareFrom) }}</div>
              </template>
              <template v-else>{{ compareLabel(compareFrom) }}</template>
            </th>
            <th :colspan="mergedSideBySideTable.valueColumns.length" class="algo-head algo-head-to">
              <template v-if="isPairCompare">
                <div class="algo-role">对照组</div>
                <div class="algo-name">{{ compareLabel(compareTo) }}</div>
              </template>
              <template v-else>{{ compareLabel(compareTo) }}</template>
            </th>
          </tr>
          <tr>
            <th
              v-for="col in mergedSideBySideTable.valueColumns"
              :key="'from-h-' + col"
              class="sub-head sub-head-from"
            >
              {{ columnLabel(col) }}
            </th>
            <th
              v-for="col in mergedSideBySideTable.valueColumns"
              :key="'to-h-' + col"
              class="sub-head sub-head-to"
            >
              {{ columnLabel(col) }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, rowIndex) in visibleMergedRows" :key="rowIndex">
            <td class="kpi-col-cell">
              <span class="kpi-col-text" :title="kpiHelp(row.kpi)">{{ kpiLabel(row.kpi) }}</span>
            </td>
            <td
              v-for="col in mergedSideBySideTable.valueColumns"
              :key="'from-' + rowIndex + '-' + col"
              class="val-from"
            >
              <span class="val-with-icon">
                <span class="val-text">{{ formatKpiDisplayValue(getRowCell(row.from, col), row.kpi, compareFrom, col) }}</span>
                <i
                  v-if="kpiAdvantage(row.kpi, row.from, row.to, col) === 'better'"
                  class="ri-thumb-up-fill adv-icon adv-better"
                  title="评估模型优于对照组"
                />
                <i
                  v-else-if="kpiAdvantage(row.kpi, row.from, row.to, col) === 'worse'"
                  class="ri-thumb-down-fill adv-icon adv-worse"
                  title="评估模型劣于对照组"
                />
                <i
                  v-else-if="kpiAdvantage(row.kpi, row.from, row.to, col) === 'equal'"
                  class="ri-scales-3-fill adv-icon adv-equal"
                  title="评估模型与对照组持平"
                />
              </span>
            </td>
            <td
              v-for="col in mergedSideBySideTable.valueColumns"
              :key="'to-' + rowIndex + '-' + col"
              class="val-to"
            >
              {{ formatKpiDisplayValue(getRowCell(row.to, col), row.kpi, compareTo, col) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <el-empty
      v-else
      :description="emptyDescription"
      class="empty-block"
    />

    <div class="evaluation-score-grid" :class="{ 'is-comparison': analysisSimulations.length === 2, 'align-algorithms': showComparison && comparisonViewMode === 'sideBySide' && mergedSideBySideTable }">
      <evaluation-analysis-panel v-for="sim in analysisSimulations" :key="'analysis-' + sim" :sim-name="sim" :analysis="analysisBySim[sim] || {}" />
    </div>

    <select-simulation-compare-modal
      v-model="showCompareModal"
      :simulation-list="compareCandidates"
      @confirm="onCompareSelected"
    />
  </div>
</template>

<script>
import SelectSimulationCompareModal from '@/components/shared/SelectSimulationCompareModal.vue'
import { formatColumnName, formatKpiName, compareKpiAdvantage } from '@/utils/kpiLabels'
import { collectKpiTableColumns, formatKpiCellValue } from '@/utils/kpiCsvParse'
import { formatResmarlLabel } from '@/utils/resmarlLabels'
import { actualKpiTotal, actualKpiLoadMetric } from '@/utils/kpiActualTotals'
import EvaluationAnalysisPanel from './EvaluationAnalysisPanel.vue'

export default {
  name: 'KpiAnalysisPanel',
  components: { SelectSimulationCompareModal, EvaluationAnalysisPanel },
  props: {
    activeSim: { type: String, default: '' },
    parsedKpis: { type: Object, default: () => ({}) },
    simulationSeries: { type: Object, default: () => ({}) },
    selectedSimulations: { type: Array, default: () => [] },
    resmarlBySim: { type: Object, default: () => ({}) },
    analysisBySim: { type: Object, default: () => ({}) },
    currencyBySim: { type: Object, default: () => ({}) }
  },
  data() {
    return {
      labelLocale: 'zh',
      showCompareModal: false,
      showComparison: false,
      compareFrom: null,
      compareTo: null,
      comparisonRows: [],
      /** diff=差值单表 | sideBySide=合并双算法单表；默认并排 */
      comparisonViewMode: 'sideBySide'
    }
  },
  computed: {
    analysisSimulations() {
      return this.showComparison ? [this.compareFrom, this.compareTo].filter(Boolean) : [this.activeSim].filter(Boolean)
    },
    activeResmarlLabel() {
      return formatResmarlLabel(this.resmarlBySim[this.activeSim])
    },
    /** 模型优选双模型：selected[0]=评估 selected[1]=对照 */
    isPairCompare() {
      return Array.isArray(this.selectedSimulations) && this.selectedSimulations.length === 2
    },
    currentRows() {
      if (!this.activeSim) return []
      const rows = this.parsedKpis[this.activeSim]
      return Array.isArray(rows) ? this.orderComfortRows(rows, this.resolveKpiColumnKey(rows[0])) : []
    },
    beginnerRows() {
      return this.filterCoreRows(this.currentRows, this.kpiColumnKey)
    },
    visibleComparisonRows() {
      return this.filterCoreRows(this.comparisonRows, this.kpiColumnKey)
    },
    visibleMergedRows() {
      if (!this.mergedSideBySideTable) return []
      return this.filterCoreRows(this.mergedSideBySideTable.rows, 'kpi')
    },
    currentColumns() {
      if (!this.currentRows.length) return []
      return collectKpiTableColumns(this.currentRows)
    },
    canCompare() {
      return this.activeSim && this.selectedSimulations.length > 1 && this.currentRows.length > 0
    },
    compareCandidates() {
      return this.selectedSimulations.filter((s) => s !== this.compareFrom)
    },
    comparisonColumns() {
      if (!this.comparisonRows.length) return []
      return collectKpiTableColumns(this.comparisonRows)
    },
    compareFromRows() {
      if (!this.compareFrom) return []
      const rows = this.parsedKpis[this.compareFrom]
      return Array.isArray(rows) ? rows : []
    },
    compareToRows() {
      if (!this.compareTo) return []
      const rows = this.parsedKpis[this.compareTo]
      return Array.isArray(rows) ? rows : []
    },
    sideBySideReady() {
      return this.compareFromRows.length > 0 && this.compareToRows.length > 0
    },
    mergedSideBySideTable() {
      if (!this.sideBySideReady) return null
      const fromRows = this.compareFromRows
      const toRows = this.compareToRows
      const kpiKey = this.resolveKpiColumnKey(fromRows[0] || toRows[0])
      const valueColumns = collectKpiTableColumns([...fromRows, ...toRows]).filter(
        (c) => c !== kpiKey
      )
      const n = Math.max(valueColumns.length, 1)
      // 左右各占剩余宽度的一半，故每侧列宽相同 → 两组总宽一致
      const valueColWidth = `calc((100% - 220px) / ${n * 2})`
      const toByKpi = new Map(
        toRows.map((row) => [this.getRowCell(row, kpiKey), row]).filter(([k]) => k)
      )
      const rows = []
      fromRows.forEach((fromRow) => {
        const kpi = this.getRowCell(fromRow, kpiKey)
        if (!kpi) return
        rows.push({
          kpi,
          from: fromRow,
          to: toByKpi.get(kpi) || {}
        })
      })
      return { kpiKey, valueColumns, valueColWidth, rows }
    },
    emptyDescription() {
      if (this.showComparison && this.comparisonViewMode === 'sideBySide' && !this.sideBySideReady) {
        return '无法加载左右对比数据'
      }
      if (this.showComparison) return '无法生成对比数据'
      if (!this.activeSim) return '请先选择分组'
      return '未找到 KPI 数据'
    },
    kpiColumnKey() {
      const row = this.currentRows[0] || this.comparisonRows[0]
      return this.resolveKpiColumnKey(row)
    }
  },
  watch: {
    selectedSimulations: {
      immediate: true,
      handler() {
        this.tryAutoSideBySide()
      }
    },
    parsedKpis: {
      deep: true,
      handler() {
        this.tryAutoSideBySide()
      }
    },
    activeSim() {
      if (!this.isPairCompare) {
        this.closeComparison()
      }
    }
  },
  methods: {
    compareLabel(sim) {
      if (!sim) return ''
      const tag = formatResmarlLabel(this.resmarlBySim[sim])
      return tag ? `${sim} (${tag})` : sim
    },
    roleCompareLabel(sim, role) {
      const name = this.compareLabel(sim)
      return name ? `${role} · ${name}` : role
    },
    sideLabel(sim, role) {
      if (this.isPairCompare) {
        return this.roleCompareLabel(sim, role)
      }
      return this.compareLabel(sim)
    },
    resolveKpiColumnKey(row) {
      if (!row || typeof row !== 'object') return 'KPI'
      const keys = Object.keys(row)
      const bomKpi = keys.find((k) => String(k).replace(/^\ufeff/, '') === 'KPI')
      if (bomKpi) return bomKpi
      if (Object.prototype.hasOwnProperty.call(row, 'KPI')) return 'KPI'
      if (Object.prototype.hasOwnProperty.call(row, 'cost_function')) return 'cost_function'
      return keys[0] || 'KPI'
    },
    normalizeKpiKey(value) {
      return String(value || '').replace(/^\ufeff/, '').trim().toLowerCase()
    },
    filterCoreRows(rows, key) {
      const core = new Set([
        'electricity_consumption_total', 'zero_net_energy', 'all_time_peak_average',
        'daily_peak_average', 'daily_one_minus_load_factor_average',
        'monthly_one_minus_load_factor_average', 'ramping_average', 'cost_total',
        'carbon_emissions_total', 'discomfort_hot_proportion', 'discomfort_cold_proportion', 'discomfort_proportion',
        'annual_normalized_unserved_energy_total'
      ])
      return this.orderComfortRows(rows.filter(row => core.has(this.normalizeKpiKey(this.getRowCell(row, key)))), key)
    },
    orderComfortRows(rows, key) {
      const comfortKeys = ['discomfort_hot_proportion', 'discomfort_cold_proportion', 'discomfort_proportion']
      const metric = row => this.normalizeKpiKey(this.getRowCell(row, key))
      const comfort = comfortKeys.flatMap(name => rows.filter(row => metric(row) === name))
      const remaining = rows.filter(row => !comfortKeys.includes(metric(row)))
      const firstComfort = rows.findIndex(row => comfortKeys.includes(metric(row)))
      if (firstComfort < 0) return remaining
      remaining.splice(firstComfort, 0, ...comfort)
      return remaining
    },
    getRowCell(row, col) {
      if (!row || col == null) return ''
      if (Object.prototype.hasOwnProperty.call(row, col)) {
        const v = row[col]
        return v === null || v === undefined ? '' : String(v)
      }
      const alt = Object.keys(row).find((k) => String(k).replace(/^\ufeff/, '') === String(col).replace(/^\ufeff/, ''))
      if (alt != null) {
        const v = row[alt]
        return v === null || v === undefined ? '' : String(v)
      }
      return ''
    },
    isKpiColumn(col) {
      return col === this.kpiColumnKey
    },
    formatCellValue(val) {
      return formatKpiCellValue(val)
    },
    formatKpiDisplayValue(value, key, sim, column) {
      if (value == null || String(value).trim() === '') return '—'
      const raw = Number(value)
      if (!Number.isFinite(raw)) return formatKpiCellValue(value)
      const normalized = this.normalizeKpiKey(key)
      const ratioKeys = new Set([
        'electricity_consumption_total', 'zero_net_energy', 'carbon_emissions_total', 'cost_total',
        'all_time_peak_average', 'daily_peak_average', 'daily_one_minus_load_factor_average',
        'monthly_one_minus_load_factor_average', 'ramping_average'
      ])
      const percentKeys = new Set([
        'discomfort_proportion', 'discomfort_cold_proportion', 'discomfort_hot_proportion',
        'one_minus_thermal_resilience_proportion', 'power_outage_normalized_unserved_energy_total',
        'annual_normalized_unserved_energy_total'
      ])
      if (ratioKeys.has(normalized)) {
        const change = `${formatKpiCellValue(raw * 100)}%`
        if (['cost_total', 'carbon_emissions_total', 'electricity_consumption_total'].includes(normalized)) {
          const analysis = this.analysisBySim[sim] || {}
          const total = actualKpiTotal(this.simulationSeries[sim], analysis.result, column, normalized)
          return `${total == null ? '实际数值缺失' : formatKpiCellValue(total)} | ${change}`
        }
        const actual = actualKpiLoadMetric(this.simulationSeries[sim], column, normalized)
        return `${actual == null ? '实际数值缺失' : formatKpiCellValue(actual)} | ${change}`
      }
      if (percentKeys.has(normalized)) return `${formatKpiCellValue(raw * 100)}%`
      return formatKpiCellValue(value)
    },
    formatDiffValue(value, key) {
      if (value == null || String(value).trim() === '') return '—'
      const raw = Number(value)
      if (!Number.isFinite(raw)) return formatKpiCellValue(value)
      const normalized = this.normalizeKpiKey(key)
      const proportionKeys = new Set([
        'discomfort_proportion', 'discomfort_cold_proportion', 'discomfort_hot_proportion',
        'one_minus_thermal_resilience_proportion', 'power_outage_normalized_unserved_energy_total',
        'annual_normalized_unserved_energy_total'
      ])
      return proportionKeys.has(normalized) ? `${(raw * 100).toFixed(1)} 个百分点` : formatKpiCellValue(value)
    },
    kpiAdvantage(kpiKey, fromRow, toRow, col) {
      return compareKpiAdvantage(
        kpiKey,
        this.getRowCell(fromRow, col),
        this.getRowCell(toRow, col)
      )
    },
    kpiLabel(key) {
      const label = formatKpiName(key, this.labelLocale)
      // The difference view still shows native KPI differences, not physical totals.
      if (this.showComparison && this.comparisonViewMode === 'diff') return label
      const units = {
        electricity_consumption_total: 'kWh',
        zero_net_energy: 'kWh',
        all_time_peak_average: 'kW',
        daily_peak_average: 'kW',
        ramping_average: 'kWh',
        annual_normalized_unserved_energy_total: '%',
        carbon_emissions_total: 'kg CO₂',
        cost_total: this.costCurrencyLabel()
      }
      const unit = units[this.normalizeKpiKey(key)]
      const actualLabel = this.normalizeKpiKey(key) === 'zero_net_energy'
        ? (this.labelLocale === 'en' ? 'Net grid energy' : this.labelLocale === 'zh-en' ? '净购电量（Net grid energy）' : '净购电量') : label
      return unit ? `${actualLabel}（${unit}）` : actualLabel
    },
    currencyLabel(sim) {
      const code = String(this.currencyBySim[sim] || '').trim().toUpperCase()
      const symbols = { USD: '$', CNY: '¥', EUR: '€', GBP: '£', JPY: 'JP¥', HKD: 'HK$', CAD: 'CA$', AUD: 'A$', SGD: 'S$' }
      return symbols[code] || code || (this.labelLocale === 'en' ? 'Unknown currency' : '未知币种')
    },
    costCurrencyLabel() {
      const sims = this.showComparison ? [this.compareFrom, this.compareTo] : [this.activeSim]
      const codes = sims.map(sim => String(this.currencyBySim[sim] || '').trim().toUpperCase())
      if (codes.every(code => code === codes[0])) return this.currencyLabel(sims[0])
      return this.labelLocale === 'en'
        ? `Left: ${this.currencyLabel(sims[0])}; Right: ${this.currencyLabel(sims[1])}`
        : `左：${this.currencyLabel(sims[0])}；右：${this.currencyLabel(sims[1])}`
    },
    kpiHelp(key) {
      const descriptions = {
        electricity_consumption_total: '实际电网购电量 | 原始 KPI 基准百分比。左侧为评估期逐栋累计的 max(净购电量, 0)，单位 kWh，向电网送电不抵扣购电量；社区为各栋建筑购电量之和。右侧为该记录原始 KPI × 100%，100% 表示与该记录内置基准持平。社区原始 KPI 为各栋比值的平均，并非社区总购电量相除。旧导出时序可能缺少末尾评估状态。',
        zero_net_energy: '实际净购电量 | 原始 KPI 基准百分比。实际值为评估时序净用电量之和，单位 kWh，计入向电网送电的抵扣。',
        all_time_peak_average: '实际峰值功率 | 占该记录评估基准的百分比。例如 17.16 kW | 97.1%，其中 97.1% = 原始 KPI 0.971 × 100%，100% 表示持平。不是与右侧所选模型的功率互除。实际功率从建筑时序逐时汇总后除以时间步长并取最大值。旧记录可能缺少部分评估状态，因此时序与原始 KPI 覆盖范围可能不同。',
        daily_peak_average: '实际日峰值平均功率 | 原始 KPI 基准百分比。按 CityLearn 的每 24 个时间步分组，取组内净用电功率峰值后求平均，单位 kW；末尾不足一组也计入。',
        daily_one_minus_load_factor_average: '实际日负荷不均衡值 | 原始 KPI 基准百分比。每 24 个时间步计算“1 − 平均负荷/峰值负荷”再求平均，无量纲；峰值为零的分组不参与平均。',
        monthly_one_minus_load_factor_average: '实际月负荷不均衡值 | 原始 KPI 基准百分比。每 730 个时间步计算“1 − 平均负荷/峰值负荷”再求平均，无量纲；短评估期不代表完整月份。',
        ramping_average: '实际累计向上爬坡电量 | 原始 KPI 基准百分比。按当前 CityLearn 默认口径，累计相邻时间步净用电量的正增量，单位 kWh，不累计下降幅度。',
        cost_total: `实际购电费用 | 原始 KPI 基准百分比。货币单位：${this.costCurrencyLabel()}，按评估数据集发布快照或所属社区读取，不进行汇率换算。未知币种表示该记录缺少可追溯的币种配置。优先读取评估产物的完整原始正费用账单；旧记录缺少账单时，按导出时序逐栋累计 max(净购电量×电价, 0)。100% 表示与该记录内置评估基准持平。社区费用为各楼账单之和；原始社区 KPI 是各楼比值的平均，并非社区总账单相除。旧时序可能缺少末尾评估状态。不同币种的实际费用不能直接比较。`,
        carbon_emissions_total: '实际购电碳排放 | 原始 KPI 基准百分比。实际值按导出时序逐栋累计 max(净购电量×碳强度, 0)，单位 kg CO₂，再汇总社区。向电网送电不抵扣排放。百分比是该记录原始 KPI × 100%，相对其内置评估基准；社区原始 KPI 是各楼比值平均。旧时序可能缺少末尾状态，累计值与完整 KPI 的覆盖范围可能不同。',
        discomfort_hot_proportion: '高温不适比例：有人使用的时间步中，室温高于制冷设定温度加容许温差的时间步占比。例如 2.0% 表示每 100 个有人使用的时间步中，约 2 个偏热。越低越好；这里显示实际占比，不是相对基准的百分比。',
        discomfort_cold_proportion: '低温不适比例：有人使用的时间步中，室温低于供暖设定温度减容许温差的时间步占比。例如 3.0% 表示每 100 个有人使用的时间步中，约 3 个偏冷。越低越好；这里显示实际占比，不是相对基准的百分比。',
        discomfort_proportion: '有人时温度超标比例：有人使用的时间步中，室温超出供暖/制冷设定值及容许温差的比例，包含偏热和偏冷两种情况。0.02 显示为 2.0%；越低越好。这是温度代理指标，不等于完整热舒适标准评价。',
        annual_normalized_unserved_energy_total: '评估期未满足能源比例：未被设备供给的能源 ÷ 预期能源需求。“年度”是 KPI 名称，短时评估并不代表覆盖全年。'
      }
      return descriptions[this.normalizeKpiKey(key)] || `专业指标：${this.kpiLabel(key)}。`
    },
    columnLabel(key) {
      return formatColumnName(key, this.labelLocale)
    },
    tryAutoSideBySide() {
      if (!this.isPairCompare) {
        return
      }
      const evalSim = this.selectedSimulations[0]
      const controlSim = this.selectedSimulations[1]
      const fromRows = this.parsedKpis[evalSim]
      const toRows = this.parsedKpis[controlSim]
      if (!Array.isArray(fromRows) || !fromRows.length || !Array.isArray(toRows) || !toRows.length) {
        return
      }
      this.compareFrom = evalSim
      this.compareTo = controlSim
      this.buildDiffRows(evalSim, controlSim)
      this.comparisonViewMode = 'sideBySide'
      this.showComparison = true
    },
    buildDiffRows(fromSim, toSim) {
      const Y = this.parsedKpis[fromSim]
      const X = this.parsedKpis[toSim]
      if (!X || !Y || X.length !== Y.length) {
        this.comparisonRows = []
        return false
      }
      const kpiKey = this.resolveKpiColumnKey(X[0])
      // 差值 = 评估(左) − 对照(右) 便于解读
      this.comparisonRows = Y.map((yRow, i) => {
        const xRow = X[i]
        if (this.getRowCell(xRow, kpiKey) !== this.getRowCell(yRow, kpiKey)) {
          return { [kpiKey]: this.getRowCell(yRow, kpiKey), error: 'KPI mismatch' }
        }
        const diff = { [kpiKey]: this.getRowCell(yRow, kpiKey) }
        collectKpiTableColumns(Y).forEach((key) => {
          if (key === kpiKey) return
          const a = parseFloat(this.getRowCell(yRow, key))
          const b = parseFloat(this.getRowCell(xRow, key))
          diff[key] = !Number.isNaN(a) && !Number.isNaN(b) ? a - b : ''
        })
        return diff
      })
      return true
    },
    openCompare() {
      if (this.isPairCompare) {
        this.tryAutoSideBySide()
        return
      }
      this.compareFrom = this.activeSim
      this.showCompareModal = true
    },
    onCompareSelected(target) {
      this.compareTo = target
      if (!this.buildDiffRows(this.compareFrom, target)) {
        this.$message.warning('所选仿真 KPI 行数不一致，无法对比')
        return
      }
      this.comparisonViewMode = 'sideBySide'
      this.showComparison = true
    },
    toggleComparisonView() {
      if (this.comparisonViewMode === 'diff') {
        if (!this.sideBySideReady) {
          this.$message.warning('缺少对比分组数据，无法切换为并排对比')
          return
        }
        this.comparisonViewMode = 'sideBySide'
      } else {
        this.comparisonViewMode = 'diff'
      }
    },
    closeComparison() {
      this.showComparison = false
      this.compareFrom = null
      this.compareTo = null
      this.comparisonRows = []
      this.comparisonViewMode = 'sideBySide'
    },
    cellStyle(val) {
      const n = parseFloat(val)
      if (Number.isNaN(n)) return {}
      if (n > 0) return { color: 'var(--success-color)', fontWeight: 'bold' }
      if (n < 0) return { color: 'var(--error-color)', fontWeight: 'bold' }
      return {}
    }
  }
}
</script>

<style scoped>
.evaluation-score-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 20px; }
.evaluation-score-grid.is-comparison { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.evaluation-score-grid > * { min-width: 0; }
.evaluation-score-grid.align-algorithms { grid-template-columns: 220px repeat(2, minmax(0, 1fr)); gap: 0; padding: 0 1px; }
.evaluation-score-grid.align-algorithms > :first-child { grid-column: 2; }
.evaluation-score-grid.align-algorithms > * { padding-left: 12px; padding-right: 12px; }
.kpi-panel {
  margin: 0;
  padding: 16px;
  border: 1px solid var(--el-border-color-lighter, var(--divider-color));
  border-radius: 4px;
  background: var(--card-background-color);
  flex-shrink: 0;
  box-shadow: none;
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
  font-weight: 600;
  color: var(--primary-text-color);
}
.hint {
  margin: 0;
  font-size: 13px;
  color: var(--secondary-text-color);
}
.resmarl-tag {
  margin-left: 8px;
  vertical-align: middle;
}
.actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.locale-select {
  width: 140px;
}
.empty-block {
  padding: 24px 0;
}
.table-wrap {
  overflow-x: auto;
  max-width: 100%;
  border: 1px solid var(--el-border-color-lighter, var(--divider-color));
  border-radius: 4px;
  background: var(--card-background-color);
}
.kpi-native-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
  background: var(--card-background-color);
}
.kpi-native-table th,
.kpi-native-table td {
  border-bottom: 1px solid var(--el-border-color-lighter, var(--divider-color));
  padding: 10px 12px;
  text-align: left;
  white-space: normal;
}
.kpi-native-table thead th {
  background: var(--el-fill-color-light, var(--input-fill-color));
  color: var(--el-text-color-regular, var(--secondary-text-color));
  font-weight: 600;
}
.kpi-native-table tbody tr:nth-child(odd) td {
  background: var(--card-background-color);
}
.kpi-native-table tbody tr:nth-child(even) td {
  background: var(--el-fill-color-lighter, var(--card-background-color));
}
.kpi-native-table tbody tr:hover td {
  background: var(--el-fill-color-light, var(--ha-hover-background));
}
.kpi-help {
  padding: 10px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter, var(--divider-color));
  color: var(--el-text-color-secondary, var(--secondary-text-color));
  font-size: 13px;
  line-height: 1.5;
}
.kpi-merged-compare-table {
  table-layout: fixed;
  width: 100%;
}

.kpi-merged-compare-table .kpi-fixed-col {
  width: 220px;
}

.kpi-merged-compare-table .kpi-col-head,
.kpi-merged-compare-table .kpi-col-cell {
  position: sticky;
  left: 0;
  z-index: 2;
  width: 220px;
  min-width: 220px;
  max-width: 220px;
  overflow: hidden;
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
  vertical-align: middle;
  box-shadow: 2px 0 4px rgba(0, 0, 0, 0.04);
}

.kpi-merged-compare-table .kpi-col-text {
  display: block;
  max-width: 100%;
  overflow: hidden;
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
  line-height: 1.35;
}

.kpi-merged-compare-table .kpi-col-head {
  background: var(--input-fill-color);
  z-index: 3;
}

.kpi-merged-compare-table tbody tr:nth-child(odd) .kpi-col-cell {
  background: var(--card-background-color);
}
.kpi-merged-compare-table tbody tr:nth-child(even) .kpi-col-cell {
  background: rgba(0, 0, 0, 0.02);
}

.kpi-merged-compare-table .algo-head {
  text-align: center;
  font-size: 14px;
  white-space: normal;
}

.kpi-merged-compare-table .algo-role {
  font-weight: 600;
  line-height: 1.3;
}

.kpi-merged-compare-table .algo-name {
  margin-top: 2px;
  font-size: 12px;
  font-weight: 400;
  opacity: 0.85;
  white-space: normal;
  word-break: break-all;
}

.kpi-merged-compare-table .algo-head-from {
  background: rgba(var(--rgb-primary-color), 0.1);
  color: var(--primary-color);
}

.kpi-merged-compare-table .algo-head-to {
  background: rgba(255, 152, 0, 0.12);
  color: var(--accent-color);
}

.kpi-merged-compare-table .sub-head {
  text-align: center;
  font-size: 12px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
}

.kpi-merged-compare-table .sub-head-from {
  background: var(--ha-hover-background);
}

.kpi-merged-compare-table .sub-head-to {
  background: var(--ha-warning-background);
}

.kpi-merged-compare-table tbody tr:nth-child(odd) .val-from {
  background: var(--card-background-color);
}
.kpi-merged-compare-table tbody tr:nth-child(even) .val-from {
  background: var(--ha-hover-background);
}
.kpi-merged-compare-table tbody tr:nth-child(odd) .val-to {
  background: var(--card-background-color);
}
.kpi-merged-compare-table tbody tr:nth-child(even) .val-to {
  background: var(--ha-warning-background);
}
.kpi-merged-compare-table .val-from {
  position: relative;
}
.kpi-merged-compare-table .val-with-icon {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  width: 100%;
  min-width: 0;
}
.kpi-merged-compare-table .val-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
.kpi-merged-compare-table .adv-icon {
  flex-shrink: 0;
  margin-left: auto;
  font-size: 15px;
  line-height: 1;
}
.kpi-merged-compare-table .adv-better {
  color: var(--el-color-success);
}
.kpi-merged-compare-table .adv-worse {
  color: var(--el-color-danger);
}
.kpi-merged-compare-table .adv-equal {
  color: var(--el-text-color-secondary);
}
.kpi-merged-compare-table tbody tr:hover .kpi-col-cell {
  background: var(--ha-hover-background);
}
.kpi-merged-compare-table tbody tr:hover .val-from {
  background: var(--ha-hover-background);
}
.kpi-merged-compare-table tbody tr:hover .val-to {
  background: var(--ha-hover-background);
}
</style>
