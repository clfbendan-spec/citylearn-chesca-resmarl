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
            差值对比：{{ compareLabel(compareFrom) }} vs {{ compareLabel(compareTo) }}
          </template>
          <template v-else>
            并排对比：{{ compareLabel(compareFrom) }} vs {{ compareLabel(compareTo) }}
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
        <el-button v-if="showComparison" size="small" @click="closeComparison">返回 KPI</el-button>
        <el-button
          v-else-if="canCompare"
          type="warning"
          size="small"
          @click="openCompare"
        >
          对比
        </el-button>
      </div>
    </div>

    <div v-if="!showComparison && currentRows.length" class="table-wrap">
      <table class="kpi-native-table">
        <thead>
          <tr>
            <th v-for="col in currentColumns" :key="col">{{ columnLabel(col) }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, rowIndex) in currentRows" :key="rowIndex">
            <td v-for="col in currentColumns" :key="col">
              <span v-if="isKpiColumn(col)">{{ kpiLabel(getRowCell(row, col)) }}</span>
              <span v-else>{{ formatCellValue(getRowCell(row, col)) }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div
      v-else-if="showComparison && comparisonViewMode === 'diff' && comparisonRows.length"
      class="table-wrap"
    >
      <table class="kpi-native-table">
        <thead>
          <tr>
            <th v-for="col in comparisonColumns" :key="col">{{ columnLabel(col) }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, rowIndex) in comparisonRows" :key="rowIndex">
            <td v-for="col in comparisonColumns" :key="col">
              <span v-if="isKpiColumn(col)">{{ kpiLabel(getRowCell(row, col)) }}</span>
              <span v-else :style="cellStyle(getRowCell(row, col))">{{ getRowCell(row, col) }}</span>
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
        <thead>
          <tr>
            <th rowspan="2" class="kpi-col-head">{{ columnLabel(mergedSideBySideTable.kpiKey) }}</th>
            <th :colspan="mergedSideBySideTable.valueColumns.length" class="algo-head algo-head-from">
              {{ compareLabel(compareFrom) }}
            </th>
            <th :colspan="mergedSideBySideTable.valueColumns.length" class="algo-head algo-head-to">
              {{ compareLabel(compareTo) }}
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
          <tr v-for="(row, rowIndex) in mergedSideBySideTable.rows" :key="rowIndex">
            <td class="kpi-col-cell">{{ kpiLabel(row.kpi) }}</td>
            <td
              v-for="col in mergedSideBySideTable.valueColumns"
              :key="'from-' + rowIndex + '-' + col"
              class="val-from"
            >
              {{ formatCellValue(getRowCell(row.from, col)) }}
            </td>
            <td
              v-for="col in mergedSideBySideTable.valueColumns"
              :key="'to-' + rowIndex + '-' + col"
              class="val-to"
            >
              {{ formatCellValue(getRowCell(row.to, col)) }}
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

    <select-simulation-compare-modal
      v-model="showCompareModal"
      :simulation-list="compareCandidates"
      @confirm="onCompareSelected"
    />
  </div>
</template>

<script>
import SelectSimulationCompareModal from '@/components/shared/SelectSimulationCompareModal.vue'
import { formatColumnName, formatKpiName } from '@/utils/kpiLabels'
import { collectKpiTableColumns, formatKpiCellValue } from '@/utils/kpiCsvParse'
import { formatResmarlLabel } from '@/utils/resmarlLabels'

export default {
  name: 'KpiAnalysisPanel',
  components: { SelectSimulationCompareModal },
  props: {
    activeSim: { type: String, default: '' },
    parsedKpis: { type: Object, default: () => ({}) },
    selectedSimulations: { type: Array, default: () => [] },
    resmarlBySim: { type: Object, default: () => ({}) }
  },
  data() {
    return {
      labelLocale: 'zh',
      showCompareModal: false,
      showComparison: false,
      compareFrom: null,
      compareTo: null,
      comparisonRows: [],
      /** diff=差值单表 | sideBySide=合并双算法单表 */
      comparisonViewMode: 'diff'
    }
  },
  computed: {
    activeResmarlLabel() {
      return formatResmarlLabel(this.resmarlBySim[this.activeSim])
    },
    currentRows() {
      if (!this.activeSim) return []
      const rows = this.parsedKpis[this.activeSim]
      return Array.isArray(rows) ? rows : []
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
      return { kpiKey, valueColumns, rows }
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
    activeSim() {
      this.closeComparison()
    }
  },
  methods: {
    compareLabel(sim) {
      if (!sim) return ''
      const tag = formatResmarlLabel(this.resmarlBySim[sim])
      return tag && tag !== '未标注' ? `${sim} (${tag})` : sim
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
    kpiLabel(key) {
      return formatKpiName(key, this.labelLocale)
    },
    columnLabel(key) {
      return formatColumnName(key, this.labelLocale)
    },
    openCompare() {
      this.compareFrom = this.activeSim
      this.showCompareModal = true
    },
    onCompareSelected(target) {
      this.compareTo = target
      const X = this.parsedKpis[target]
      const Y = this.parsedKpis[this.compareFrom]
      if (!X || !Y || X.length !== Y.length) {
        this.$message.warning('所选仿真 KPI 行数不一致，无法对比')
        return
      }
      const kpiKey = this.resolveKpiColumnKey(X[0])
      this.comparisonRows = X.map((xRow, i) => {
        const yRow = Y[i]
        if (this.getRowCell(xRow, kpiKey) !== this.getRowCell(yRow, kpiKey)) {
          return { [kpiKey]: this.getRowCell(xRow, kpiKey), error: 'KPI mismatch' }
        }
        const diff = { [kpiKey]: this.getRowCell(xRow, kpiKey) }
        collectKpiTableColumns(X).forEach((key) => {
          if (key === kpiKey) return
          const a = parseFloat(this.getRowCell(xRow, key))
          const b = parseFloat(this.getRowCell(yRow, key))
          diff[key] = !Number.isNaN(a) && !Number.isNaN(b) ? (a - b).toFixed(3) : ''
        })
        return diff
      })
      this.comparisonViewMode = 'diff'
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
      this.comparisonViewMode = 'diff'
    },
    cellStyle(val) {
      const n = parseFloat(val)
      if (Number.isNaN(n)) return {}
      if (n > 0) return { color: '#67c23a', fontWeight: 'bold' }
      if (n < 0) return { color: '#f56c6c', fontWeight: 'bold' }
      return {}
    }
  }
}
</script>

<style scoped>
.kpi-panel {
  margin-top: 16px;
  margin-bottom: 24px;
  padding: 12px 16px 16px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background: #fafafa;
  flex-shrink: 0;
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}
.title {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 600;
}
.hint {
  margin: 0;
  font-size: 13px;
  color: #909399;
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
}
.kpi-native-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  background: #fff;
}
.kpi-native-table th,
.kpi-native-table td {
  border: 1px solid #ebeef5;
  padding: 8px 12px;
  text-align: left;
  white-space: nowrap;
}
.kpi-native-table thead th {
  background: #f5f7fa;
  color: #606266;
  font-weight: 600;
}
.kpi-native-table tbody tr:nth-child(odd) td {
  background: #fff;
}
.kpi-native-table tbody tr:nth-child(even) td {
  background: #f0f2f5;
}
.kpi-native-table tbody tr:hover td {
  background: #e8f5e9;
}

.kpi-merged-compare-table .kpi-col-head,
.kpi-merged-compare-table .kpi-col-cell {
  position: sticky;
  left: 0;
  z-index: 2;
  box-shadow: 2px 0 4px rgba(0, 0, 0, 0.04);
}

.kpi-merged-compare-table .kpi-col-head {
  background: #f5f7fa;
  z-index: 3;
}

.kpi-merged-compare-table tbody tr:nth-child(odd) .kpi-col-cell {
  background: #fff;
}
.kpi-merged-compare-table tbody tr:nth-child(even) .kpi-col-cell {
  background: #f0f2f5;
}

.kpi-merged-compare-table .algo-head {
  text-align: center;
  font-size: 14px;
}

.kpi-merged-compare-table .algo-head-from {
  background: #ecf5ff;
  color: #409eff;
}

.kpi-merged-compare-table .algo-head-to {
  background: #fdf6ec;
  color: #e6a23c;
}

.kpi-merged-compare-table .sub-head {
  text-align: center;
  font-size: 12px;
  font-weight: 500;
}

.kpi-merged-compare-table .sub-head-from {
  background: #f5f9ff;
}

.kpi-merged-compare-table .sub-head-to {
  background: #fef9f3;
}

.kpi-merged-compare-table tbody tr:nth-child(odd) .val-from {
  background: #f8fbff;
}
.kpi-merged-compare-table tbody tr:nth-child(even) .val-from {
  background: #e8f2fc;
}
.kpi-merged-compare-table tbody tr:nth-child(odd) .val-to {
  background: #fffdf8;
}
.kpi-merged-compare-table tbody tr:nth-child(even) .val-to {
  background: #faf0e4;
}
.kpi-merged-compare-table tbody tr:hover .kpi-col-cell {
  background: #e8f5e9;
}
.kpi-merged-compare-table tbody tr:hover .val-from {
  background: #dff0e8;
}
.kpi-merged-compare-table tbody tr:hover .val-to {
  background: #dff0e8;
}
</style>
