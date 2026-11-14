<template>
  <el-dialog
    title="选择比较模型"
    :visible.sync="visible"
    width="min(1180px, 96vw)"
    custom-class="select-compare-model-dialog"
    @close="onDialogClosed"
  >
    <el-table
      v-loading="loading"
      :data="visibleRecords"
      row-key="taskId"
      :row-class-name="rowClassName"
      max-height="480"
      empty-text="暂无可选模型"
      @row-click="toggleRow"
    >
      <el-table-column label="选择" width="66" align="center">
        <template slot-scope="scope">
          <button
            type="button"
            class="selection-button"
            :class="{ selected: selectionIndex(scope.row) >= 0 }"
            :disabled="loading"
            :aria-pressed="selectionIndex(scope.row) >= 0 ? 'true' : 'false'"
            :aria-label="selectionLabel(scope.row)"
            :title="selectionLabel(scope.row)"
            @click.stop="toggleRow(scope.row)"
          >
            <span v-if="selectionIndex(scope.row) >= 0">{{ selectionIndex(scope.row) === 0 ? '①' : '②' }}</span>
            <span v-else class="empty-selection" aria-hidden="true" />
          </button>
        </template>
      </el-table-column>
      <el-table-column label="记录名" min-width="220" show-overflow-tooltip>
        <template slot-scope="scope">{{ recordName(scope.row) }}</template>
      </el-table-column>
      <el-table-column label="评估数据集" min-width="230" show-overflow-tooltip>
        <template slot-scope="scope">{{ scope.row.evaluationDataset || '—' }}</template>
      </el-table-column>
      <el-table-column label="时间" width="166">
        <template slot-scope="scope">{{ formatTime(scope.row.taskCreateTime) }}</template>
      </el-table-column>
      <el-table-column label="总不适比例" width="120" align="right">
        <template slot-scope="scope">{{ formatNumber(scope.row.discomfortProportion, true) }}</template>
      </el-table-column>
      <el-table-column label="成本" width="110" align="right">
        <template slot-scope="scope">{{ formatNumber(scope.row.costTotal) }}</template>
      </el-table-column>
    </el-table>
    <span slot="footer">
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :disabled="loading || !canConfirm" @click="confirm">确认</el-button>
    </span>
  </el-dialog>
</template>

<script>
import dayjs from 'dayjs'

export default {
  name: 'SelectCompareModelModal',
  props: {
    value: { type: Boolean, default: false },
    loading: { type: Boolean, default: false },
    simulationList: { type: Array, default: () => [] }
  },
  data() {
    return { selectedIds: [], confirmed: false }
  },
  computed: {
    visibleRecords() {
      return this.simulationList.filter(row => !/^(2026|2023)/.test((this.recordName(row) || '').trim()))
    },
    visible: {
      get() { return this.value },
      set(v) { this.$emit('input', v) }
    },
    canConfirm() {
      return this.selectedIds.length === 2 && this.selectedIds.every(id =>
        this.visibleRecords.some(row => row.taskId === id))
    }
  },
  watch: {
    value(open) {
      if (open) {
        this.selectedIds = []
        this.confirmed = false
      }
    },
    visibleRecords(rows) {
      this.selectedIds = this.selectedIds.filter(id => rows.some(row => row.taskId === id))
    }
  },
  methods: {
    recordName(row) { return row.recordName || row.groupName },
    selectionIndex(row) { return this.selectedIds.indexOf(row.taskId) },
    selectionLabel(row) {
      const index = this.selectionIndex(row)
      return index >= 0 ? `取消选择${index === 0 ? '评估模型' : '对照组'}：${this.recordName(row)}` : `选择：${this.recordName(row)}`
    },
    rowClassName({ row }) { return this.selectionIndex(row) >= 0 ? 'selected-model-row' : '' },
    toggleRow(row) {
      if (this.loading || !this.visibleRecords.some(item => item.taskId === row.taskId)) return
      const index = this.selectionIndex(row)
      if (index >= 0) this.selectedIds.splice(index, 1)
      else if (this.selectedIds.length < 2) this.selectedIds.push(row.taskId)
      else this.$message.info('最多选择两条记录，请先取消一条已选记录')
    },
    formatTime(value) {
      return value && dayjs(value).isValid() ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '—'
    },
    formatNumber(value, proportion = false) {
      if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) return '—'
      return proportion ? `${(Number(value) * 100).toFixed(2)}%` : Number(value).toFixed(4)
    },
    onDialogClosed() {
      if (this.confirmed) {
        this.confirmed = false
        return
      }
      this.$emit('cancel')
    },
    confirm() {
      if (this.loading || !this.canConfirm) return
      this.confirmed = true
      this.$emit('confirm', this.selectedIds.map(id => this.simulationList.find(row => row.taskId === id).groupName))
      this.visible = false
    }
  }
}
</script>

<style scoped>
.selection-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--secondary-text-color);
  font-size: 22px;
  cursor: pointer;
}
.selection-button.selected { color: var(--el-color-primary, #409eff); }
.empty-selection { width: 17px; height: 17px; border: 1px solid currentColor; border-radius: 50%; }
.selection-button:focus-visible {
  outline: 2px solid var(--el-color-primary, #409eff);
  border-radius: 4px;
}
:deep(.el-table__body tr) { cursor: pointer; }
:deep(.selected-model-row > td) { background: var(--primary-background-color); }
</style>
